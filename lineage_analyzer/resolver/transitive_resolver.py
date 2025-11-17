"""
Transitive lineage resolver for dependency tracing.

This module defines the TransitiveLineageResolver class, which provides
functionality to trace lineage paths, perform impact analysis, and explain
calculation chains.
"""

from typing import List, Optional, Set

from lineage_analyzer.exceptions import LineageError
from lineage_analyzer.models.column import ColumnRef
from lineage_analyzer.models.lineage_path import LineageNode, LineagePath
from lineage_analyzer.models.table_definition import TableType
from lineage_analyzer.registry.table_registry import TableRegistry


class TransitiveLineageResolver:
    """Transitive dependency resolver.

    Responsibilities:
    1. Trace fields to source (trace_to_source)
    2. Impact analysis (find_impact)
    3. Explain calculation chains (explain_calculation)

    Core algorithm: Depth-First Search (DFS) + cycle detection

    Usage:
        resolver = TransitiveLineageResolver(registry)

        # Trace to source
        paths = resolver.trace_to_source("t3", "final")
        for path in paths:
            print(path.to_string())

        # Impact analysis
        impacts = resolver.find_impact("orders", "amount")
        print(f"Affects {len(impacts)} downstream columns")

        # Explain calculation
        explanation = resolver.explain_calculation("t3", "final")
        print(explanation)
    """

    def __init__(self, registry: TableRegistry) -> None:
        """Initialize a TransitiveLineageResolver.

        Args:
            registry: TableRegistry containing all table definitions.
        """
        self.registry = registry

    def trace_to_source(
        self, table_name: str, column_name: str, max_depth: int = 100
    ) -> List[LineagePath]:
        """Trace field to all sources.

        Algorithm: Depth-First Search (DFS)
        1. Start from target field
        2. Find all direct upstream sources
        3. For each upstream, recursively find its upstream
        4. Until reaching source tables (EXTERNAL type)
        5. Return all paths

        Args:
            table_name: Table name.
            column_name: Column name.
            max_depth: Maximum depth (prevent infinite recursion).

        Returns:
            List[LineagePath]: All paths from target to sources.

        Raises:
            LineageError: If table or column doesn't exist.
        """
        # Validate target table and column exist
        table_def = self.registry.get_table(table_name)
        if not table_def:
            raise LineageError(
                f"Table '{table_name}' not found in registry"
            )

        if not table_def.has_column(column_name):
            raise LineageError(
                f"Column '{column_name}' not found in table '{table_name}'"
            )

        # Start DFS
        all_paths: List[LineagePath] = []
        visited: Set[str] = set()  # Cycle detection

        self._dfs_trace(
            table_name,
            column_name,
            current_path=LineagePath(),
            all_paths=all_paths,
            visited=visited,
            depth=0,
            max_depth=max_depth,
        )

        return all_paths

    def _dfs_trace(
        self,
        table_name: str,
        column_name: str,
        current_path: LineagePath,
        all_paths: List[LineagePath],
        visited: Set[str],
        depth: int,
        max_depth: int,
    ) -> None:
        """DFS recursive implementation.

        Args:
            table_name: Current table name.
            column_name: Current column name.
            current_path: Current path being built.
            all_paths: Accumulated list of all complete paths.
            visited: Set of visited nodes (for cycle detection).
            depth: Current depth.
            max_depth: Maximum depth.
        """
        # 1. Prevent infinite recursion
        if depth > max_depth:
            return

        # 2. Build current node identifier (for cycle detection)
        node_key = f"{table_name}.{column_name}"

        # 3. Cycle detection - prevent revisiting the same node in the same path
        if node_key in visited:
            return  # Already visited in this path, avoid infinite loop

        visited.add(node_key)

        # 4. Get current column definition
        table_def = self.registry.get_table(table_name)
        if not table_def:
            visited.remove(node_key)
            return

        column_lineage = table_def.get_column(column_name)
        if not column_lineage:
            visited.remove(node_key)
            return

        # 5. Create current node
        current_node = LineageNode(
            column=ColumnRef(table=table_name, column=column_name),
            expression=column_lineage.expression,
            expression_type=column_lineage.expression_type,
            table_type=(
                table_def.table_type.value
                if table_def.table_type
                else "UNKNOWN"
            ),
        )

        # 6. Add to current path
        current_path.add_node(current_node)

        # 7. Check if reached source
        if table_def.is_source_table:
            # Reached source table, save path
            all_paths.append(LineagePath(nodes=current_path.nodes.copy()))
            # Backtrack and return (don't continue)
            current_path.nodes.pop()
            visited.remove(node_key)
            return
        elif not column_lineage.sources:
            # No sources (shouldn't happen, but handle gracefully)
            # This might be a source table column that wasn't properly registered
            # Save path anyway
            all_paths.append(LineagePath(nodes=current_path.nodes.copy()))
            # Backtrack and return
            current_path.nodes.pop()
            visited.remove(node_key)
            return
        else:
            # Continue tracing upstream - each source creates a separate path
            # Save current path state before branching
            base_path_nodes = current_path.nodes.copy()
            for source in column_lineage.sources:
                # Create a fresh path copy for each branch
                # This ensures each source gets its own independent path
                branch_path = LineagePath(nodes=base_path_nodes.copy())
                self._dfs_trace(
                    source.table,
                    source.column,
                    branch_path,  # Use copy of path for each branch
                    all_paths,
                    visited.copy(),  # Copy visited set for each branch
                    depth + 1,
                    max_depth,
                )

        # 8. Backtrack (remove current node)
        current_path.nodes.pop()
        visited.remove(node_key)

    def find_impact(
        self, table_name: str, column_name: str, max_depth: int = 100
    ) -> List[ColumnRef]:
        """Impact analysis: find all downstream fields that depend on this field.

        Algorithm: Reverse DFS
        1. Start from source field
        2. Traverse all tables, find columns that reference this field
        3. Recursively find downstream of these columns
        4. Return all affected fields

        Args:
            table_name: Source table name.
            column_name: Source column name.
            max_depth: Maximum depth.

        Returns:
            List[ColumnRef]: All affected downstream fields.
        """
        # Validate source table and column exist
        table_def = self.registry.get_table(table_name)
        if not table_def:
            raise LineageError(
                f"Table '{table_name}' not found in registry"
            )

        # If it's a derived table, also validate column exists
        if not table_def.is_source_table and not table_def.has_column(
            column_name
        ):
            raise LineageError(
                f"Column '{column_name}' not found in table '{table_name}'"
            )

        # Start reverse DFS
        impacted: List[ColumnRef] = []
        visited: Set[str] = set()

        self._dfs_impact(
            table_name,
            column_name,
            impacted=impacted,
            visited=visited,
            depth=0,
            max_depth=max_depth,
        )

        return impacted

    def _dfs_impact(
        self,
        table_name: str,
        column_name: str,
        impacted: List[ColumnRef],
        visited: Set[str],
        depth: int,
        max_depth: int,
    ) -> None:
        """Reverse DFS: find downstream.

        Args:
            table_name: Current table name.
            column_name: Current column name.
            impacted: List of impacted columns (accumulated).
            visited: Set of visited nodes.
            depth: Current depth.
            max_depth: Maximum depth.
        """
        if depth > max_depth:
            return

        node_key = f"{table_name}.{column_name}"

        if node_key in visited:
            return

        visited.add(node_key)

        # Traverse all tables, find columns that reference this field
        for table_def in self.registry.get_all_tables():
            for col_name, col_lineage in table_def.columns.items():
                # Check if this column depends on our source field
                for source in col_lineage.sources:
                    if (
                        source.table == table_name
                        and source.column == column_name
                    ):
                        # Found a downstream field
                        downstream = ColumnRef(
                            table=table_def.name, column=col_name
                        )
                        impacted.append(downstream)

                        # Recursively find downstream of this downstream field
                        self._dfs_impact(
                            table_def.name,
                            col_name,
                            impacted,
                            visited,
                            depth + 1,
                            max_depth,
                        )

    def explain_calculation(
        self, table_name: str, column_name: str
    ) -> str:
        """Explain complete calculation chain for a field (human-readable format).

        Args:
            table_name: Table name.
            column_name: Column name.

        Returns:
            Multi-line string showing complete calculation chain.

        Example output:
            t3.final = t2.doubled + 100 (computed)
              ← t2.doubled = t1.amount * 2 (computed)
                ← t1.amount = orders.amount (direct)
                  ← orders.amount (source)
        """
        paths = self.trace_to_source(table_name, column_name)

        if not paths:
            return (
                f"{table_name}.{column_name} has no lineage information"
            )

        # Generate explanation (select first path, can show all if multiple)
        lines = []
        lines.append(
            f"Calculation chain for {table_name}.{column_name}:"
        )
        lines.append("=" * 60)

        for i, path in enumerate(paths, 1):
            if len(paths) > 1:
                lines.append(f"\nPath {i}:")

            # Show with hierarchical indentation
            for depth, node in enumerate(path.nodes):
                indent = "  " * depth

                if node.expression:
                    lines.append(
                        f"{indent}{node.column.table}.{node.column.column} = "
                        f"{node.expression} ({node.expression_type.value})"
                    )
                else:
                    marker = "(source)" if node.is_source() else "(direct)"
                    lines.append(
                        f"{indent}{node.column.table}.{node.column.column} {marker}"
                    )

                # Add arrow (except for last node)
                if depth < len(path.nodes) - 1:
                    lines.append(f"{indent}  ↓")

        return "\n".join(lines)

    def get_all_source_tables(
        self, table_name: str, column_name: str
    ) -> Set[str]:
        """Get all source tables that a field depends on (deduplicated).

        Args:
            table_name: Table name.
            column_name: Column name.

        Returns:
            Set[str]: Set of source table names.
        """
        paths = self.trace_to_source(table_name, column_name)

        source_tables: Set[str] = set()
        for path in paths:
            if path.source and path.source.is_source():
                source_tables.add(path.source.column.table)

        return source_tables

