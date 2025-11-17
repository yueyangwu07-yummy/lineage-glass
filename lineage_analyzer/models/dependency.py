"""
Column dependency model.

This module defines the ColumnDependency class and ExpressionType enum, which
together represent relationships between source and target columns in SQL
queries, including the type of dependency (direct, computed, function, etc.)
and metadata about the relationship.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class ExpressionType(str, Enum):
    """Enumeration of dependency relationship types in SQL expressions.

    This enum represents the different ways a target column can depend on
    source columns in a SQL query. Each type indicates a different kind of
    transformation or relationship between columns.

    Attributes:
        DIRECT: Direct column reference without transformation,
            e.g., SELECT col_a FROM table
        COMPUTED: Arithmetic or logical computation involving multiple columns,
            e.g., SELECT col_a + col_b FROM table
        FUNCTION: Single-argument function applied to a column,
            e.g., SELECT UPPER(col_a) FROM table
        CASE: CASE WHEN expression with conditional logic,
            e.g., SELECT CASE WHEN col_a > 0 THEN col_b ELSE col_c END
        AGGREGATION: Aggregate function (not supported in v0.1),
            e.g., SELECT SUM(col_a) FROM table
        WINDOW: Window function (not supported in v0.1),
            e.g., SELECT ROW_NUMBER() OVER (PARTITION BY col_a)
    """

    DIRECT = "direct"
    COMPUTED = "computed"
    FUNCTION = "function"
    CASE = "case"
    AGGREGATION = "aggregation"
    WINDOW = "window"

    @classmethod
    def values(cls) -> list[str]:
        """Return a list of all possible expression type values.

        Returns:
            List of string values for all expression types in the enum.

        Example:
            >>> ExpressionType.values()
            ['direct', 'computed', 'function', 'case', 'aggregation', 'window']
        """
        return [member.value for member in cls]


@dataclass
class ColumnDependency:
    """Represents a dependency relationship between source and target columns.

    A ColumnDependency captures the relationship between a source column (from
    which data originates) and a target column (where data ends up) in a SQL
    query. It includes information about the type of dependency, the original
    expression text, and a confidence score indicating the reliability of the
    dependency inference.

    Attributes:
        source: The source column from which data originates.
        target: The target column where data ends up.
        expression_type: The type of dependency relationship (direct, computed,
            function, case, etc.).
        expression: Optional original SQL expression text that created this
            dependency, useful for debugging and traceability.
        confidence: Confidence score between 0.0 and 1.0 indicating how
            reliable this dependency inference is. Defaults to 1.0 (fully
            confident).

    Example:
        >>> source = ColumnRef(table="orders", column="order_id")
        >>> target = ColumnRef(table="orders", column="order_id", alias="id")
        >>> dep = ColumnDependency(
        ...     source=source,
        ...     target=target,
        ...     expression_type=ExpressionType.DIRECT,
        ...     expression="order_id",
        ...     confidence=1.0
        ... )
        >>> dep.to_dict()
        {'source': {...}, 'target': {...}, 'expression_type': 'direct', ...}
    """

    source: ColumnRef
    target: ColumnRef
    expression_type: ExpressionType
    expression: Optional[str] = None
    confidence: float = 1.0
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

    def to_dict(self) -> dict[str, Any]:
        """Serialize the ColumnDependency to a dictionary.

        Converts the ColumnDependency instance to a dictionary representation
        that can be easily serialized to JSON or other formats. All attributes
        are included, with ColumnRef objects converted to dictionaries using
        their dataclass representation.

        Returns:
            Dictionary representation of the ColumnDependency, including
            source and target columns, expression type, expression text, and
            confidence score.

        Example:
            >>> dep = ColumnDependency(
            ...     source=ColumnRef(table="t", column="c1"),
            ...     target=ColumnRef(table="t", column="c2"),
            ...     expression_type=ExpressionType.DIRECT
            ... )
            >>> data = dep.to_dict()
            >>> isinstance(data, dict)
            True
        """
        return {
            "source": {
                "database": self.source.database,
                "schema": self.source.schema,
                "table": self.source.table,
                "column": self.source.column,
                "alias": self.source.alias,
            },
            "target": {
                "database": self.target.database,
                "schema": self.target.schema,
                "table": self.target.table,
                "column": self.target.column,
                "alias": self.target.alias,
            },
            "expression_type": self.expression_type.value,
            "expression": self.expression,
            "confidence": self.confidence,
            "is_aggregate": self.is_aggregate,
            "aggregate_function": self.aggregate_function,
            "is_group_by": self.is_group_by,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ColumnDependency:
        """Deserialize a ColumnDependency from a dictionary.

        Creates a ColumnDependency instance from a dictionary representation,
        typically produced by the to_dict() method. This method handles the
        conversion of nested dictionary structures back into ColumnRef objects.

        Args:
            data: Dictionary containing source, target, expression_type,
                expression (optional), and confidence (optional) fields.

        Returns:
            A new ColumnDependency instance constructed from the dictionary data.

        Raises:
            ValueError: If required fields are missing or invalid.
            KeyError: If required dictionary keys are not present.

        Example:
            >>> data = {
            ...     "source": {"table": "t", "column": "c1"},
            ...     "target": {"table": "t", "column": "c2"},
            ...     "expression_type": "direct"
            ... }
            >>> dep = ColumnDependency.from_dict(data)
            >>> isinstance(dep, ColumnDependency)
            True
        """
        from lineage_analyzer.models.column import ColumnRef

        source_dict = data["source"]
        target_dict = data["target"]

        source = ColumnRef(
            database=source_dict.get("database"),
            schema=source_dict.get("schema"),
            table=source_dict["table"],
            column=source_dict["column"],
            alias=source_dict.get("alias"),
        )

        target = ColumnRef(
            database=target_dict.get("database"),
            schema=target_dict.get("schema"),
            table=target_dict["table"],
            column=target_dict["column"],
            alias=target_dict.get("alias"),
        )

        expression_type = ExpressionType(data["expression_type"])
        expression = data.get("expression")
        confidence = data.get("confidence", 1.0)

        return cls(
            source=source,
            target=target,
            expression_type=expression_type,
            expression=expression,
            confidence=confidence,
        )

