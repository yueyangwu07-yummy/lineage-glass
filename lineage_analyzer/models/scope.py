"""
Scope model for lineage analysis.

This module defines the Scope class, which represents a namespace or context
for SQL queries and subqueries. A scope tracks available tables and columns,
allowing the analyzer to resolve references and build lineage relationships.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from lineage_analyzer.models.column import ColumnRef
from lineage_analyzer.models.table import TableRef


@dataclass
class Scope:
    """Represents a namespace or context for SQL query analysis.

    A Scope tracks the tables and columns available within a particular
    context (e.g., a main query or subquery). It provides methods to register
    and resolve table and column references, enabling the lineage analyzer to
    understand which columns are available and where they come from.

    The Scope supports nested scopes through a parent reference, allowing
    subqueries to access columns from outer queries (v0.1 does not use this
    feature, but the structure is in place for future support).

    Attributes:
        parent: Optional parent scope for nested query contexts. In v0.1,
            this is typically None as nested scopes are not supported.
        tables: Dictionary mapping table names or aliases to TableRef objects.
            Used to resolve table references in the current scope.
        columns: Dictionary mapping column names to lists of ColumnRef objects.
            Used to resolve column references and track possible sources.
        output_columns: List of ColumnRef objects representing columns that
            are output by this scope (e.g., SELECT clause columns).

    Example:
        >>> scope = Scope()
        >>> table = TableRef(table="orders", alias="o")
        >>> scope.register_table(table)
        >>> resolved = scope.resolve_table("o")
        >>> resolved == table
        True
        >>> col = ColumnRef(table="orders", column="id")
        >>> scope.register_column(col)
        >>> found = scope.find_column("id")
        >>> len(found) == 1
        True
    """

    parent: Optional[Scope] = None
    tables: dict[str, TableRef] = field(default_factory=dict)
    columns: dict[str, list[ColumnRef]] = field(default_factory=dict)
    output_columns: list[ColumnRef] = field(default_factory=list)

    def register_table(self, table_ref: TableRef) -> None:
        """Register a table reference in this scope.

        Adds a TableRef to the scope's table registry, making it available
        for resolution by name or alias. If the table has an alias, it is
        registered under both its alias and its table name for flexible
        lookup.

        Args:
            table_ref: The TableRef to register in this scope.

        Raises:
            ValueError: If table_ref is None or invalid.

        Example:
            >>> scope = Scope()
            >>> table = TableRef(table="orders", alias="o")
            >>> scope.register_table(table)
            >>> "o" in scope.tables
            True
            >>> "orders" in scope.tables
            True
        """
        if table_ref is None:
            raise ValueError("table_ref cannot be None")

        # Register by table name
        self.tables[table_ref.table] = table_ref

        # Register by alias if present
        if table_ref.alias:
            self.tables[table_ref.alias] = table_ref

    def resolve_table(self, name: str) -> Optional[TableRef]:
        """Resolve a table name or alias to a TableRef.

        Looks up a table in the current scope by name or alias. If not found
        in the current scope and a parent scope exists, the lookup continues
        in the parent scope (v0.1 does not use parent scopes, but the
        structure supports it).

        Args:
            name: Table name or alias to resolve.

        Returns:
            The TableRef if found, None otherwise.

        Example:
            >>> scope = Scope()
            >>> table = TableRef(table="orders", alias="o")
            >>> scope.register_table(table)
            >>> resolved = scope.resolve_table("o")
            >>> resolved == table
            True
            >>> not_found = scope.resolve_table("customers")
            >>> not_found is None
            True
        """
        if not name:
            return None

        # Check current scope
        if name in self.tables:
            return self.tables[name]

        # Check parent scope if it exists (not used in v0.1)
        if self.parent is not None:
            return self.parent.resolve_table(name)

        return None

    def register_column(self, column_ref: ColumnRef) -> None:
        """Register a column reference in this scope.

        Adds a ColumnRef to the scope's column registry. Columns are stored
        in a list because the same column name might refer to multiple
        different columns (e.g., in a JOIN). The column is registered under
        its column name for lookup purposes.

        Args:
            column_ref: The ColumnRef to register in this scope.

        Raises:
            ValueError: If column_ref is None or invalid.

        Example:
            >>> scope = Scope()
            >>> col = ColumnRef(table="orders", column="id")
            >>> scope.register_column(col)
            >>> "id" in scope.columns
            True
            >>> len(scope.columns["id"]) == 1
            True
        """
        if column_ref is None:
            raise ValueError("column_ref cannot be None")

        column_name = column_ref.column
        if column_name not in self.columns:
            self.columns[column_name] = []
        self.columns[column_name].append(column_ref)

    def find_column(self, column_name: str) -> list[ColumnRef]:
        """Find all column references matching a column name.

        Searches for columns in the current scope by name. Returns all
        matching ColumnRef objects, as the same column name might refer to
        multiple columns (e.g., in a JOIN). If not found in the current scope
        and a parent scope exists, the search continues in the parent scope
        (v0.1 does not use parent scopes, but the structure supports it).

        Args:
            column_name: Name of the column to find.

        Returns:
            List of ColumnRef objects matching the column name. Returns an
            empty list if no matches are found.

        Example:
            >>> scope = Scope()
            >>> col1 = ColumnRef(table="orders", column="id")
            >>> col2 = ColumnRef(table="customers", column="id")
            >>> scope.register_column(col1)
            >>> scope.register_column(col2)
            >>> found = scope.find_column("id")
            >>> len(found) == 2
            True
        """
        if not column_name:
            return []

        # Check current scope
        if column_name in self.columns:
            return self.columns[column_name].copy()

        # Check parent scope if it exists (not used in v0.1)
        if self.parent is not None:
            return self.parent.find_column(column_name)

        return []

