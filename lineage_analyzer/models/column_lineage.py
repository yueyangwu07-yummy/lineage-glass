"""
Column lineage model.

This module defines the ColumnLineage class, which represents the lineage
information for a single column, including its sources, expression, and metadata.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from lineage_analyzer.models.column import ColumnRef
from lineage_analyzer.models.dependency import ExpressionType


@dataclass
class ColumnLineage:
    """Single column lineage information.

    Used to record the complete lineage of a column in a table: which source
    columns it comes from and how it is computed.

    Attributes:
        name: Column name.
        data_type: Data type (optional, from DDL or inferred).
        sources: List of source columns (which upstream columns this column depends on).
        expression: Computation expression (e.g., "amount + tax").
        expression_type: Expression type (direct/computed/function/aggregation).
        confidence: Confidence score (0.0-1.0).
        metadata: Additional metadata (e.g., comments, tags).

    Example:
        # Direct mapping
        ColumnLineage(
            name="user_id",
            sources=[ColumnRef(table="orders", column="user_id")],
            expression_type=ExpressionType.DIRECT
        )

        # Computed column
        ColumnLineage(
            name="total",
            sources=[
                ColumnRef(table="orders", column="amount"),
                ColumnRef(table="orders", column="tax")
            ],
            expression="amount + tax",
            expression_type=ExpressionType.COMPUTED
        )
    """

    name: str
    data_type: Optional[str] = None
    sources: List[ColumnRef] = field(default_factory=list)
    expression: Optional[str] = None
    expression_type: ExpressionType = ExpressionType.DIRECT
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Aggregate-related attributes
    is_aggregate: bool = False
    aggregate_function: Optional[str] = None  # SUM/AVG/MIN/MAX/COUNT
    is_group_by: bool = False

    def __post_init__(self) -> None:
        """Validate that confidence is in the valid range."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"confidence must be between 0.0 and 1.0, got {self.confidence}"
            )

    def add_source(self, source: ColumnRef) -> None:
        """Add a source column (supports multiple sources, e.g., multiple INSERTs).

        Args:
            source: Source column reference.
        """
        # Deduplicate: add the same source only once
        source_key = source.to_qualified_name()
        if not any(s.to_qualified_name() == source_key for s in self.sources):
            self.sources.append(source)

    def merge_from(self, other: "ColumnLineage") -> None:
        """Merge sources from another ColumnLineage.

        Used for INSERT INTO scenarios: the same column may have multiple sources.

        Args:
            other: Another ColumnLineage to merge from.

        Raises:
            ValueError: If trying to merge different columns.
        """
        if other.name != self.name:
            raise ValueError(
                f"Cannot merge different columns: {self.name} vs {other.name}"
            )

        # Merge source columns
        for source in other.sources:
            self.add_source(source)

        # If there's a new expression, append to metadata
        if other.expression:
            if "alternative_expressions" not in self.metadata:
                self.metadata["alternative_expressions"] = []
            self.metadata["alternative_expressions"].append(other.expression)

        # Decrease confidence (multiple sources increase uncertainty)
        self.confidence = min(self.confidence, other.confidence * 0.9)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (for serialization).

        Returns:
            Dictionary representation of the ColumnLineage.
        """
        return {
            "name": self.name,
            "data_type": self.data_type,
            "sources": [s.to_qualified_name() for s in self.sources],
            "expression": self.expression,
            "expression_type": self.expression_type.value,
            "confidence": self.confidence,
            "metadata": self.metadata,
            "is_aggregate": self.is_aggregate,
            "aggregate_function": self.aggregate_function,
            "is_group_by": self.is_group_by,
        }

