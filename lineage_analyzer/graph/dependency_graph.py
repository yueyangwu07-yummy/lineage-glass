"""
Dependency graph for lineage analysis.

This module defines the DependencyGraph class, which uses networkx to
build and analyze dependency graphs for lineage relationships.
"""

from __future__ import annotations

from typing import Any, Optional

import networkx as nx

from lineage_analyzer.models.dependency import ColumnDependency


class DependencyGraph:
    """Dependency graph for lineage relationships.

    This class uses networkx to build a directed graph representing
    field-level dependencies. It provides methods for querying upstream
    and downstream dependencies, and supports graph visualization.

    Attributes:
        graph: networkx DiGraph object representing the dependencies.

    Example:
        >>> graph = DependencyGraph()
        >>> graph.add_dependency(dep)
        >>> upstream = graph.get_upstream_columns("total")
        >>> len(upstream) > 0
        True
    """

    def __init__(self) -> None:
        """Initialize a DependencyGraph."""
        self.graph = nx.DiGraph()

    def add_dependency(self, dep: ColumnDependency) -> None:
        """Add a dependency relationship to the graph.

        This method adds a dependency relationship to the graph. Nodes
        represent columns (table.column), and edges represent dependencies
        with attributes (expression_type, expression).

        Args:
            dep: ColumnDependency object to add to the graph.

        Example:
            >>> graph = DependencyGraph()
            >>> dep = ColumnDependency(...)
            >>> graph.add_dependency(dep)
            >>> graph.graph.number_of_nodes() > 0
            True
        """
        source_id = f"{dep.source.table}.{dep.source.column}"
        target_id = f"__OUTPUT__.{dep.target.column}"

        # Add source node
        self.graph.add_node(
            source_id,
            table=dep.source.table,
            column=dep.source.column,
            node_type="source",
        )

        # Add target node
        self.graph.add_node(
            target_id,
            table=None,
            column=dep.target.column,
            node_type="target",
        )

        # Add edge
        self.graph.add_edge(
            source_id,
            target_id,
            expression_type=dep.expression_type.value,
            expression=dep.expression,
        )

    def get_upstream_columns(self, column: str) -> set[str]:
        """Get all upstream dependencies for a column (recursive).

        This method returns all upstream columns that the specified
        column depends on, recursively traversing the dependency graph.

        Args:
            column: Target column name (without table prefix).

        Returns:
            Set of upstream column qualified names.

        Example:
            >>> graph = DependencyGraph()
            >>> graph.add_dependency(dep)
            >>> upstream = graph.get_upstream_columns("total")
            >>> len(upstream) > 0
            True
        """
        target_id = f"__OUTPUT__.{column}"
        if target_id not in self.graph:
            return set()

        # Use networkx ancestors query
        ancestors = nx.ancestors(self.graph, target_id)
        return {
            node
            for node in ancestors
            if self.graph.nodes[node].get("node_type") == "source"
        }

    def get_downstream_columns(self, table: str, column: str) -> set[str]:
        """Get all downstream columns affected by a source column.

        This method returns all downstream columns that are affected
        by the specified source column, recursively traversing the
        dependency graph.

        Args:
            table: Source table name.
            column: Source column name.

        Returns:
            Set of downstream column names.

        Example:
            >>> graph = DependencyGraph()
            >>> graph.add_dependency(dep)
            >>> downstream = graph.get_downstream_columns("orders", "amount")
            >>> len(downstream) > 0
            True
        """
        source_id = f"{table}.{column}"
        if source_id not in self.graph:
            return set()

        # Use networkx descendants query
        descendants = nx.descendants(self.graph, source_id)
        return {
            self.graph.nodes[node].get("column")
            for node in descendants
            if self.graph.nodes[node].get("node_type") == "target"
            and self.graph.nodes[node].get("column")
        }

    def to_dict(self) -> dict[str, list[dict[str, Any]]]:
        """Export graph to dictionary format.

        This method exports the graph to a dictionary format suitable
        for JSON serialization.

        Returns:
            Dictionary containing nodes and edges.

        Example:
            >>> graph = DependencyGraph()
            >>> graph.add_dependency(dep)
            >>> data = graph.to_dict()
            >>> "nodes" in data
            True
            >>> "edges" in data
            True
        """
        return {
            "nodes": [
                {
                    "id": node,
                    "table": data.get("table"),
                    "column": data.get("column"),
                    "type": data.get("node_type"),
                }
                for node, data in self.graph.nodes(data=True)
            ],
            "edges": [
                {
                    "source": u,
                    "target": v,
                    "expression_type": data.get("expression_type"),
                    "expression": data.get("expression"),
                }
                for u, v, data in self.graph.edges(data=True)
            ],
        }

    def get_statistics(self) -> dict[str, int]:
        """Get graph statistics.

        This method returns statistics about the graph, including
        number of nodes, edges, and maximum depth.

        Returns:
            Dictionary containing graph statistics.

        Example:
            >>> graph = DependencyGraph()
            >>> graph.add_dependency(dep)
            >>> stats = graph.get_statistics()
            >>> "total_nodes" in stats
            True
        """
        source_nodes = [
            n
            for n, d in self.graph.nodes(data=True)
            if d.get("node_type") == "source"
        ]
        target_nodes = [
            n
            for n, d in self.graph.nodes(data=True)
            if d.get("node_type") == "target"
        ]

        # Calculate maximum depth
        max_depth = 0
        for target in target_nodes:
            for source in source_nodes:
                if nx.has_path(self.graph, source, target):
                    try:
                        path_length = nx.shortest_path_length(
                            self.graph, source, target
                        )
                        max_depth = max(max_depth, path_length)
                    except nx.NetworkXNoPath:
                        pass

        return {
            "total_nodes": self.graph.number_of_nodes(),
            "source_nodes": len(source_nodes),
            "target_nodes": len(target_nodes),
            "total_edges": self.graph.number_of_edges(),
            "max_depth": max_depth,
        }

    def to_dot(self) -> str:
        """Export graph to Graphviz DOT format.

        This method exports the graph to Graphviz DOT format for
        visualization.

        Returns:
            DOT format string.

        Example:
            >>> graph = DependencyGraph()
            >>> graph.add_dependency(dep)
            >>> dot = graph.to_dot()
            >>> "digraph" in dot
            True
        """
        try:
            from networkx.drawing.nx_pydot import to_pydot

            pydot_graph = to_pydot(self.graph)
            return pydot_graph.to_string()
        except ImportError:
            # pydot not available, return simple DOT format
            lines = ["digraph G {"]
            for u, v, data in self.graph.edges(data=True):
                lines.append(f'  "{u}" -> "{v}";')
            lines.append("}")
            return "\n".join(lines)

