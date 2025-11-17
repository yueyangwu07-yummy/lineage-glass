"""
INSERT INTO ... SELECT analyzer for lineage analysis.

This module defines the InsertIntoAnalyzer class, which analyzes INSERT INTO
SELECT statements and merges new lineage into existing table definitions.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from lineage_analyzer.models.table_definition import TableDefinition

import sqlglot
from sqlglot import expressions

from lineage_analyzer.analyzer.cte_extractor import CTEExtractor
from lineage_analyzer.analyzer.dependency_extractor import DependencyExtractor
from lineage_analyzer.analyzer.scope_builder import ScopeBuilder
from lineage_analyzer.analyzer.symbol_resolver import SymbolResolver
from lineage_analyzer.exceptions import LineageError
from lineage_analyzer.models.classified_statement import ClassifiedStatement
from lineage_analyzer.models.column_lineage import ColumnLineage
from lineage_analyzer.models.config import LineageConfig
from lineage_analyzer.models.dependency import ColumnDependency
from lineage_analyzer.models.statement_type import StatementType
from lineage_analyzer.models.table_definition import TableDefinition
from lineage_analyzer.registry.table_registry import TableRegistry
from lineage_analyzer.schema.provider import SchemaProvider


class InsertIntoAnalyzer:
    """INSERT INTO ... SELECT statement analyzer.

    Responsibilities:
    1. Analyze INSERT INTO target_table SELECT ... statements
    2. Extract field dependencies from SELECT part
    3. Merge new lineage into existing table definition
    4. Handle column name mismatches

    Key scenarios:
        # Scenario 1: Column names match
        INSERT INTO t1 SELECT amount, tax FROM orders
        → t1.amount adds source orders.amount
        → t1.tax adds source orders.tax

        # Scenario 2: Different column order
        INSERT INTO t1 (col2, col1) SELECT a, b FROM orders
        → t1.col2 adds source orders.a
        → t1.col1 adds source orders.b

        # Scenario 3: Column count mismatch
        INSERT INTO t1 SELECT a FROM orders  -- t1 has 2 columns
        → Error: column count mismatch

    Usage:
        analyzer = InsertIntoAnalyzer(registry, config)
        analyzer.analyze(classified_statement)
    """

    def __init__(
        self,
        registry: TableRegistry,
        config: LineageConfig,
        schema_provider: Optional[SchemaProvider] = None,
    ) -> None:
        """Initialize an InsertIntoAnalyzer.

        Args:
            registry: TableRegistry to update table definitions.
            config: LineageConfig for analysis configuration.
            schema_provider: Optional SchemaProvider for schema information.
        """
        self.registry = registry
        self.config = config
        self.schema_provider = schema_provider

        # Create CTE extractor (reuse Step 1 code)
        self.cte_extractor = CTEExtractor(
            registry=registry, config=config, schema_provider=schema_provider
        )

    def analyze(
        self, statement: ClassifiedStatement
    ) -> Dict[str, ColumnLineage]:
        """Analyze an INSERT INTO SELECT statement.

        Args:
            statement: Classified statement (must be INSERT_INTO_SELECT).

        Returns:
            Dict[str, ColumnLineage]: Updated column lineage dictionary.

        Raises:
            LineageError: If target table doesn't exist or column count mismatch.
        """
        # 1. Validate statement type
        if statement.statement_type != StatementType.INSERT_INTO_SELECT:
            raise LineageError(
                f"InsertIntoAnalyzer only handles INSERT INTO SELECT, "
                f"got: {statement.statement_type}"
            )

        # 2. Extract target table
        target_table = statement.target_table
        if not target_table:
            raise LineageError("Cannot extract target table from INSERT INTO")

        # 3. Check if target table exists
        table_def = self.registry.get_table(target_table)
        if not table_def:
            raise LineageError(
                f"INSERT INTO target table '{target_table}' does not exist. "
                f"Table must be created before INSERT INTO."
            )

        # 4. Analyze SELECT part
        query_ast = statement.query_ast
        if query_ast is None:
            raise LineageError("Query AST is None in INSERT INTO statement")

        # Check if INSERT statement has WITH clause (CTE)
        # Extract and register CTEs before analyzing main query
        cte_tables = {}

        # Check INSERT AST for WITH clause first (for INSERT INTO WITH ... SELECT)
        insert_ast = statement.ast
        if isinstance(insert_ast, expressions.Insert):
            insert_with = insert_ast.args.get("with")
            if insert_with:
                # Extract CTEs from INSERT's WITH clause
                if hasattr(insert_with, "expressions"):
                    ctes = []
                    for cte_expr in insert_with.expressions:
                        if isinstance(cte_expr, expressions.CTE):
                            cte_name = cte_expr.alias
                            cte_select = cte_expr.this
                            if cte_name and isinstance(cte_select, expressions.Select):
                                from lineage_analyzer.analyzer.cte_extractor import (
                                    CTEDefinition,
                                )

                                ctes.append(CTEDefinition(cte_name, cte_select))

                    if ctes:
                        # Analyze and register CTEs (before analyzing main query)
                        cte_tables = self.cte_extractor.analyze_and_register_ctes(
                            ctes, statement_index=statement.statement_index
                        )

                        # Record log (optional)
                        if cte_tables:
                            pass

        # Also check query_ast for WITH clause (for cases where WITH is in SELECT)
        if not cte_tables and isinstance(query_ast, expressions.Select):
            if self.cte_extractor.has_ctes(query_ast):
                # Extract CTE definitions
                ctes = self.cte_extractor.extract_ctes(query_ast)

                # Analyze and register CTEs (before analyzing main query)
                if ctes:
                    cte_tables = self.cte_extractor.analyze_and_register_ctes(
                        ctes, statement_index=statement.statement_index
                    )

                    # Record log (optional)
                    if cte_tables:
                        pass

        try:
            # Analyze main query (CTEs are now in Registry)
            new_column_lineages = self._analyze_query(query_ast)
        except Exception as e:
            # Ensure CTEs are cleaned up even on error
            self._cleanup_ctes(cte_tables)
            raise e

        # 5. Extract INSERT target columns (if explicitly specified)
        target_columns = self._extract_insert_columns(statement.ast)

        # 6. Match column names (handle column order and explicit column names)
        matched_lineages = self._match_columns(
            table_def, new_column_lineages, target_columns
        )

        # 7. Merge into existing table (before CTE cleanup so expansion can work)
        self.registry.update_table_columns(target_table, matched_lineages)

        # 8. Expand CTE lineage into target table (after merging so we have the latest data)
        if cte_tables:
            self._expand_cte_lineage(target_table, cte_tables)

        # 9. Clean up CTEs after analysis (CTEs are only valid within this statement)
        self._cleanup_ctes(cte_tables)

        return matched_lineages

    def _analyze_query(
        self, query_ast: sqlglot.Expression
    ) -> List[ColumnLineage]:
        """Analyze SELECT query (reuse CreateTableAnalyzer logic).

        Args:
            query_ast: SELECT statement AST.

        Returns:
            List[ColumnLineage]: Column lineage from SELECT.
        """
        # Build Scope
        scope_builder = ScopeBuilder(
            self.config, self.schema_provider, self.registry
        )
        scope = scope_builder.build_scope(query_ast)

        # Auto-register source tables from scope to registry
        # This ensures source tables are available for transitive resolution
        for table_ref in scope.tables.values():
            table_name = table_ref.table
            # Only register if not already in registry
            if not self.registry.has_table(table_name):
                # Try to get columns from schema provider
                if self.schema_provider:
                    try:
                        columns = self.schema_provider.get_table_columns(
                            table_ref.to_qualified_name()
                        )
                        self.registry.register_source_table(
                            table_name, columns
                        )
                    except Exception:
                        # Schema doesn't have this table, register without columns
                        self.registry.register_source_table(table_name)
                else:
                    # No schema provider, register without columns
                    self.registry.register_source_table(table_name)

        # Create Resolver
        resolver = SymbolResolver(scope, self.config, self.schema_provider)

        # Extract dependencies
        extractor = DependencyExtractor(scope, resolver, self.config)
        dependencies = extractor.extract(query_ast)

        # Convert to ColumnLineage
        return self._convert_dependencies_to_lineages(dependencies)

    def _convert_dependencies_to_lineages(
        self, dependencies: List[ColumnDependency]
    ) -> List[ColumnLineage]:
        """Convert dependencies to lineage (same as CreateTableAnalyzer).

        Args:
            dependencies: List of ColumnDependency objects.

        Returns:
            List[ColumnLineage]: Converted column lineages.
        """
        # Group by target column
        grouped: Dict[str, List[ColumnDependency]] = defaultdict(list)
        for dep in dependencies:
            target_name = dep.target.column
            grouped[target_name].append(dep)

        lineages = []
        for target_name, deps in grouped.items():
            sources = [dep.source for dep in deps]
            expression = deps[0].expression if deps else None
            expression_type = deps[0].expression_type if deps else None
            confidence = deps[0].confidence if deps else 1.0

            # Extract aggregate attributes
            is_aggregate = deps[0].is_aggregate if deps else False
            aggregate_function = deps[0].aggregate_function if deps else None
            is_group_by = deps[0].is_group_by if deps else False

            lineage = ColumnLineage(
                name=target_name,
                sources=sources,
                expression=expression,
                expression_type=expression_type,
                confidence=confidence,
                is_aggregate=is_aggregate,
                aggregate_function=aggregate_function,
                is_group_by=is_group_by,
            )
            lineages.append(lineage)

        return lineages

    def _extract_insert_columns(
        self, insert_ast: sqlglot.Expression
    ) -> List[str]:
        """Extract explicitly specified column names from INSERT statement.

        Example:
            INSERT INTO t1 (col2, col1) SELECT ...
            Returns: ["col2", "col1"]

            INSERT INTO t1 SELECT ...
            Returns: [] (empty list, means match by position)

        Args:
            insert_ast: INSERT statement AST.

        Returns:
            List of column names (empty if not explicitly specified).
        """
        # In sqlglot, explicit columns are in this.expressions
        table_expr = insert_ast.this

        # Check if it's a Schema (with explicit columns) or Table (without)
        if isinstance(table_expr, expressions.Schema):
            # Has explicit columns
            if hasattr(table_expr, "expressions") and table_expr.expressions:
                return [
                    col.name if hasattr(col, "name") else str(col)
                    for col in table_expr.expressions
                ]
        elif isinstance(table_expr, expressions.Table):
            # No explicit columns, check if it has expressions (should be empty)
            if hasattr(table_expr, "expressions") and table_expr.expressions:
                return [
                    col.name if hasattr(col, "name") else str(col)
                    for col in table_expr.expressions
                ]

        return []

    def _match_columns(
        self,
        table_def: TableDefinition,
        new_lineages: List[ColumnLineage],
        target_columns: List[str],
    ) -> Dict[str, ColumnLineage]:
        """Match SELECT output columns with INSERT target columns.

        Rules:
        1. If explicit column names (target_columns non-empty):
           - Match by explicit column names
           - Example: INSERT INTO t1 (col2, col1) SELECT a, b
             → a corresponds to col2, b corresponds to col1

        2. If no explicit column names:
           - Match by position (table column order)
           - Example: INSERT INTO t1 SELECT a, b
             → a corresponds to t1's 1st column, b to 2nd column

        3. Validate column count match

        Args:
            table_def: Target table definition.
            new_lineages: Column lineage from SELECT output.
            target_columns: Explicitly specified columns in INSERT (may be empty).

        Returns:
            Dict[str, ColumnLineage]: Matched column lineage dictionary.

        Raises:
            LineageError: If column count mismatch or column doesn't exist.
        """
        # Get target table columns (in definition order)
        table_columns = list(table_def.columns.keys())

        # Case 1: Has explicit column names
        if target_columns:
            if len(target_columns) != len(new_lineages):
                raise LineageError(
                    f"Column count mismatch in INSERT INTO: "
                    f"specified {len(target_columns)} columns but SELECT returns {len(new_lineages)}"
                )

            # Validate all specified columns exist
            for col in target_columns:
                if col not in table_columns:
                    raise LineageError(
                        f"Column '{col}' specified in INSERT INTO does not exist in table '{table_def.name}'"
                    )

            # Match by explicit column names
            matched = {}
            for i, target_col in enumerate(target_columns):
                lineage = new_lineages[i]
                # Create a copy and rename to target column name
                matched_lineage = ColumnLineage(
                    name=target_col,
                    sources=lineage.sources.copy(),
                    expression=lineage.expression,
                    expression_type=lineage.expression_type,
                    confidence=lineage.confidence,
                    data_type=lineage.data_type,
                    metadata=lineage.metadata.copy(),
                    is_aggregate=lineage.is_aggregate,
                    aggregate_function=lineage.aggregate_function,
                    is_group_by=lineage.is_group_by,
                )
                matched[target_col] = matched_lineage

            return matched

        # Case 2: No explicit column names, match by position
        else:
            if len(new_lineages) != len(table_columns):
                raise LineageError(
                    f"Column count mismatch in INSERT INTO: "
                    f"table '{table_def.name}' has {len(table_columns)} columns "
                    f"but SELECT returns {len(new_lineages)}"
                )

            # Match by position
            matched = {}
            for i, table_col in enumerate(table_columns):
                lineage = new_lineages[i]
                # Create a copy and rename to target column name
                matched_lineage = ColumnLineage(
                    name=table_col,
                    sources=lineage.sources.copy(),
                    expression=lineage.expression,
                    expression_type=lineage.expression_type,
                    confidence=lineage.confidence,
                    data_type=lineage.data_type,
                    metadata=lineage.metadata.copy(),
                    is_aggregate=lineage.is_aggregate,
                    aggregate_function=lineage.aggregate_function,
                    is_group_by=lineage.is_group_by,
                )
                matched[table_col] = matched_lineage

            return matched

    def _expand_cte_lineage(
        self, target_table_name: str, cte_tables: Dict[str, "TableDefinition"]
    ) -> None:
        """
        Expand CTE column lineage into target table (reuse CreateTableAnalyzer logic).

        Before removing CTEs, expand CTE column lineage into dependent tables.
        This ensures that tables updated from CTEs can trace back to source tables
        even after CTEs are removed.

        Args:
            target_table_name: Target table name
            cte_tables: Dictionary of registered CTE tables
        """
        # Get target table definition
        target_table = self.registry.get_table(target_table_name)
        if not target_table:
            return

        # Before removing CTEs, expand CTE column lineage into dependent tables
        # This ensures transitive tracing works even after CTEs are removed
        # We need to recursively expand because CTEs may reference other CTEs
        changed = True
        while changed:
            changed = False
            for col_name, col_lineage in target_table.columns.items():
                # Check if this column references any CTE
                expanded_sources = []
                needs_expansion = False
                for source in col_lineage.sources:
                    if source.table in cte_tables:
                        # This source is a CTE column, expand it
                        needs_expansion = True
                        cte_table = cte_tables[source.table]
                        if cte_table.has_column(source.column):
                            cte_col_lineage = cte_table.get_column(source.column)
                            # Add CTE column's sources (may include other CTEs)
                            expanded_sources.extend(cte_col_lineage.sources)
                    else:
                        # Not a CTE column, keep it as is
                        expanded_sources.append(source)

                # Update column lineage with expanded sources (if changed)
                if needs_expansion and expanded_sources != col_lineage.sources:
                    col_lineage.sources = expanded_sources
                    changed = True  # Mark that we changed something, need another pass

    def _cleanup_ctes(self, cte_tables: Dict[str, "TableDefinition"]) -> None:
        """
        Clean up CTE tables (remove from Registry).

        CTEs are only valid within the current statement, so they should
        be removed after analysis to avoid polluting subsequent statements.

        Args:
            cte_tables: Dictionary of registered CTE tables
        """
        for cte_name in cte_tables.keys():
            # Remove from Registry
            if self.registry.has_table(cte_name):
                self.registry.remove_table(cte_name)

