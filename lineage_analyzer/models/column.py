"""
Column reference model.

This module defines the ColumnRef class, which represents a fully qualified
column reference in SQL, including database, schema, table, column, and alias
information.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, eq=True)
class ColumnRef:
    """Represents a fully qualified column reference in SQL.

    A ColumnRef uniquely identifies a column in a SQL query by its database,
    schema, table, and column name. It may also include an alias if the column
    is renamed in the query. This class is immutable and hashable, making it
    suitable for use in sets and dictionaries.

    Attributes:
        table: Name of the table containing the column (required).
        column: Name of the column (required).
        database: Optional name of the database containing the table.
        schema: Optional name of the schema containing the table.
        alias: Optional alias for the column as used in the SQL query.

    Example:
        >>> col = ColumnRef(table="orders", column="order_id", alias="id")
        >>> col.to_qualified_name()
        'orders.order_id'
        >>> col_alias = ColumnRef(
        ...     database="prod",
        ...     schema="public",
        ...     table="orders",
        ...     column="order_id"
        ... )
        >>> col_alias.to_qualified_name()
        'prod.public.orders.order_id'
    """

    table: str
    column: str
    database: Optional[str] = None
    schema: Optional[str] = None
    alias: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate that required fields are not empty."""
        if not self.table:
            raise ValueError("table name cannot be empty")
        if not self.column:
            raise ValueError("column name cannot be empty")

    def to_qualified_name(self) -> str:
        """Return the fully qualified column name.

        Returns a string representation of the column in the format
        "database.schema.table.column", omitting any None components. The
        format follows SQL identifier naming conventions.

        Returns:
            A fully qualified column name string, e.g., "prod.public.orders.id"
            or "orders.id" if database and schema are not specified.

        Example:
            >>> col = ColumnRef(table="orders", column="id")
            >>> col.to_qualified_name()
            'orders.id'
            >>> col_full = ColumnRef(
            ...     database="prod", schema="public", table="orders", column="id"
            ... )
            >>> col_full.to_qualified_name()
            'prod.public.orders.id'
        """
        parts: list[str] = []
        if self.database:
            parts.append(self.database)
        if self.schema:
            parts.append(self.schema)
        parts.append(self.table)
        parts.append(self.column)
        return ".".join(parts)

    def __hash__(self) -> int:
        """Return the hash value of this ColumnRef.

        ColumnRef is hashable based on its database, schema, table, and column
        values. The alias is not included in the hash to ensure that two
        ColumnRefs referring to the same column (with different aliases) are
        considered equal.

        Returns:
            Hash value based on database, schema, table, and column.
        """
        return hash((self.database, self.schema, self.table, self.column))

    def __eq__(self, other: object) -> bool:
        """Check equality with another ColumnRef.

        Two ColumnRefs are considered equal if they have the same database,
        schema, table, and column values. The alias is not considered in
        equality comparison.

        Args:
            other: Object to compare with.

        Returns:
            True if the ColumnRefs refer to the same column, False otherwise.
        """
        if not isinstance(other, ColumnRef):
            return False
        return (
            self.database == other.database
            and self.schema == other.schema
            and self.table == other.table
            and self.column == other.column
        )

    def __repr__(self) -> str:
        """Return a human-readable string representation.

        Returns a string representation that includes all non-None components
        of the column reference, making it easy to understand which column
        is being referenced.

        Returns:
            Human-readable string representation of the ColumnRef.

        Example:
            >>> col = ColumnRef(table="orders", column="id", alias="order_id")
            >>> repr(col)
            "ColumnRef(table='orders', column='id', alias='order_id')"
        """
        parts: list[str] = []
        if self.database:
            parts.append(f"database='{self.database}'")
        if self.schema:
            parts.append(f"schema='{self.schema}'")
        parts.append(f"table='{self.table}'")
        parts.append(f"column='{self.column}'")
        if self.alias:
            parts.append(f"alias='{self.alias}'")
        return f"ColumnRef({', '.join(parts)})"

