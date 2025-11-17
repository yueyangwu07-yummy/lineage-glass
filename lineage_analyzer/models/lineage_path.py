"""
Lineage path model for transitive dependency resolution.

This module defines the LineagePath and LineageNode classes, which represent
complete lineage paths from target fields to source fields.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from lineage_analyzer.models.column import ColumnRef
from lineage_analyzer.models.dependency import ExpressionType


@dataclass
class LineageNode:
    """A node in a lineage path.

    Attributes:
        column: Column reference.
        expression: Computation expression for this node (if any).
        expression_type: Expression type.
        table_type: Table type (TABLE/VIEW/TEMP_TABLE/EXTERNAL).
    """

    column: ColumnRef
    expression: Optional[str] = None
    expression_type: ExpressionType = ExpressionType.DIRECT
    table_type: str = "UNKNOWN"

    def is_source(self) -> bool:
        """Check if this is a source node (external table).

        Returns:
            True if this is a source node, False otherwise.
        """
        return self.table_type.upper() == "EXTERNAL"

    def __repr__(self) -> str:
        """Return string representation."""
        return f"{self.column.table}.{self.column.column}"


@dataclass
class LineagePath:
    """A complete lineage path.

    Complete chain from target field to source field.

    Attributes:
        nodes: All nodes in the path (in order: target → source).

    Example:
        t3.final → t2.doubled → t1.amount → orders.amount
        nodes = [
            LineageNode(t3.final, "doubled + 100", COMPUTED),
            LineageNode(t2.doubled, "amount * 2", COMPUTED),
            LineageNode(t1.amount, "amount", DIRECT),
            LineageNode(orders.amount, None, DIRECT)
        ]
        hops = 3
    """

    nodes: List[LineageNode] = field(default_factory=list)

    @property
    def hops(self) -> int:
        """Path length (number of hops).

        Returns:
            Number of hops in the path.
        """
        return len(self.nodes) - 1 if self.nodes else 0

    @property
    def target(self) -> Optional[LineageNode]:
        """Target node (path start).

        Returns:
            First node in the path, or None if empty.
        """
        return self.nodes[0] if self.nodes else None

    @property
    def source(self) -> Optional[LineageNode]:
        """Source node (path end).

        Returns:
            Last node in the path, or None if empty.
        """
        return self.nodes[-1] if self.nodes else None

    def add_node(self, node: LineageNode) -> None:
        """Add a node to the path.

        Args:
            node: LineageNode to add.
        """
        self.nodes.append(node)

    def to_string(self, use_ascii: bool = False) -> str:
        """Generate human-readable path string.

        Args:
            use_ascii: If True, use ASCII characters (<-) instead of Unicode arrow (←)

        Returns:
            String representation, e.g., "t3.final ← t2.doubled ← t1.amount ← orders.amount"
            or (use_ascii=True): "t3.final <- t2.doubled <- t1.amount <- orders.amount"
        """
        if not self.nodes:
            return "(empty path)"

        parts = []
        for node in self.nodes:
            parts.append(f"{node.column.table}.{node.column.column}")

        separator = " <- " if use_ascii else " ← "
        return separator.join(parts)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation of the path.
        """
        return {
            "path": self.to_string(),
            "hops": self.hops,
            "target": str(self.target) if self.target else None,
            "source": str(self.source) if self.source else None,
            "nodes": [
                {
                    "table": node.column.table,
                    "column": node.column.column,
                    "expression": node.expression,
                    "expression_type": node.expression_type.value,
                    "is_source": node.is_source(),
                }
                for node in self.nodes
            ],
        }

