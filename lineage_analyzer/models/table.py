"""
Table reference model.

This module defines the TableRef class, which represents a table or subquery
reference in SQL, including database, schema, table name, and alias information.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, eq=True)
class TableRef:
    """Represents a table or subquery reference in SQL.

    A TableRef uniquely identifies a table in a SQL query by its database,
    schema, and table name. It may also include an alias if the table is
    aliased in the query (e.g., "orders o" where "o" is the alias). This class
    is immutable and hashable, making it suitable for use in sets and
    dictionaries.

    Attributes:
        table: Name of the actual table (required).
        database: Optional name of the database containing the table.
        schema: Optional name of the schema containing the table.
        alias: Optional alias for the table as used in the SQL query.
        is_subquery: Whether this reference represents a subquery rather than
            a physical table. Defaults to False (not used in v0.1).

    Example:
        >>> tbl = TableRef(table="orders", alias="o")
        >>> tbl.to_qualified_name()
        'orders'
        >>> tbl_full = TableRef(
        ...     database="prod", schema="public", table="orders", alias="o"
        ... )
        >>> tbl_full.to_qualified_name()
        'prod.public.orders'
    """

    table: str
    database: Optional[str] = None
    schema: Optional[str] = None
    alias: Optional[str] = None
    is_subquery: bool = False

    def __post_init__(self) -> None:
        """Validate that required fields are not empty."""
        if not self.table:
            raise ValueError("table name cannot be empty")

    def to_qualified_name(self) -> str:
        """Return the fully qualified table name.

        Returns a string representation of the table in the format
        "database.schema.table", omitting any None components. The format
        follows SQL identifier naming conventions. The alias is not included
        in the qualified name.

        Returns:
            A fully qualified table name string, e.g., "prod.public.orders"
            or "orders" if database and schema are not specified.

        Example:
            >>> tbl = TableRef(table="orders")
            >>> tbl.to_qualified_name()
            'orders'
            >>> tbl_full = TableRef(
            ...     database="prod", schema="public", table="orders"
            ... )
            >>> tbl_full.to_qualified_name()
            'prod.public.orders'
        """
        parts: list[str] = []
        if self.database:
            parts.append(self.database)
        if self.schema:
            parts.append(self.schema)
        parts.append(self.table)
        return ".".join(parts)

    def __hash__(self) -> int:
        """Return the hash value of this TableRef.

        TableRef is hashable based on its database, schema, and table values.
        The alias is not included in the hash to ensure that two TableRefs
        referring to the same table (with different aliases) are considered
        equal.

        Returns:
            Hash value based on database, schema, and table.
        """
        return hash((self.database, self.schema, self.table, self.is_subquery))

    def __eq__(self, other: object) -> bool:
        """Check equality with another TableRef.

        Two TableRefs are considered equal if they have the same database,
        schema, table, and is_subquery values. The alias is not considered
        in equality comparison.

        Args:
            other: Object to compare with.

        Returns:
            True if the TableRefs refer to the same table, False otherwise.
        """
        if not isinstance(other, TableRef):
            return False
        return (
            self.database == other.database
            and self.schema == other.schema
            and self.table == other.table
            and self.is_subquery == other.is_subquery
        )

    def __repr__(self) -> str:
        """Return a human-readable string representation.

        Returns a string representation that includes all non-None components
        of the table reference, making it easy to understand which table is
        being referenced.

        Returns:
            Human-readable string representation of the TableRef.

        Example:
            >>> tbl = TableRef(table="orders", alias="o")
            >>> repr(tbl)
            "TableRef(table='orders', alias='o')"
        """
        parts: list[str] = []
        if self.database:
            parts.append(f"database='{self.database}'")
        if self.schema:
            parts.append(f"schema='{self.schema}'")
        parts.append(f"table='{self.table}'")
        if self.alias:
            parts.append(f"alias='{self.alias}'")
        if self.is_subquery:
            parts.append("is_subquery=True")
        return f"TableRef({', '.join(parts)})"

