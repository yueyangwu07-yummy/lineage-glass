"""
Dictionary-based schema provider implementation.

This module defines the DictSchemaProvider class, which implements the
SchemaProvider interface using an in-memory dictionary. This is useful for
testing, prototyping, or when schema information is available as a simple
data structure.
"""

from typing import Optional

from lineage_analyzer.schema.provider import SchemaProvider


class DictSchemaProvider(SchemaProvider):
    """Schema provider that reads schema information from a dictionary.

    DictSchemaProvider implements the SchemaProvider interface using an
    in-memory dictionary. The dictionary maps table names to lists of column
    names, providing a simple and efficient way to provide schema information
    without requiring external data sources.

    This implementation is particularly useful for:
    - Testing and unit tests
    - Prototyping and development
    - Small-scale applications with static schemas
    - Mocking schema providers in tests

    Attributes:
        schema: Dictionary mapping table names to lists of column names.
            The keys are table names (strings), and the values are lists of
            column names (strings). Example: {"orders": ["id", "amount"]}

    Example:
        >>> schema_dict = {
        ...     "orders": ["order_id", "customer_id", "amount"],
        ...     "customers": ["customer_id", "name", "email"]
        ... }
        >>> provider = DictSchemaProvider(schema_dict)
        >>> provider.get_table_columns("orders")
        ['order_id', 'customer_id', 'amount']
        >>> provider.column_exists("orders", "order_id")
        True
        >>> provider.column_exists("orders", "nonexistent")
        False
    """

    def __init__(self, schema_dict: dict[str, list[str]]) -> None:
        """Initialize a DictSchemaProvider with a schema dictionary.

        Creates a new DictSchemaProvider instance with the provided schema
        dictionary. The dictionary should map table names to lists of column
        names. If an empty dictionary is provided, the provider will return
        empty results for all queries.

        Args:
            schema_dict: Dictionary mapping table names to lists of column
                names. Example: {"orders": ["id", "amount"]}

        Raises:
            TypeError: If schema_dict is not a dictionary.
            ValueError: If schema_dict is None.

        Example:
            >>> schema = {"table1": ["col1", "col2"]}
            >>> provider = DictSchemaProvider(schema)
            >>> isinstance(provider.schema, dict)
            True
        """
        if schema_dict is None:
            raise ValueError("schema_dict cannot be None")
        if not isinstance(schema_dict, dict):
            raise TypeError("schema_dict must be a dictionary")

        self.schema: dict[str, list[str]] = schema_dict

    def get_table_columns(self, table_name: str) -> list[str]:
        """Return all column names for a given table.

        Looks up the table in the schema dictionary and returns its column
        names. If the table is not found in the dictionary, returns an empty
        list.

        Args:
            table_name: Name of the table to query. Must match a key in the
                schema dictionary exactly (case-sensitive).

        Returns:
            List of column names for the specified table. Returns an empty
            list if the table is not found in the schema dictionary.

        Example:
            >>> schema = {"orders": ["id", "amount"]}
            >>> provider = DictSchemaProvider(schema)
            >>> provider.get_table_columns("orders")
            ['id', 'amount']
            >>> provider.get_table_columns("nonexistent")
            []
        """
        if not table_name:
            return []

        return self.schema.get(table_name, []).copy()

    def column_exists(self, table_name: str, column_name: str) -> bool:
        """Check if a column exists in a table.

        Looks up the table in the schema dictionary and checks if the
        specified column exists in its column list. Returns False if the
        table is not found or if the column is not in the table's column list.

        Args:
            table_name: Name of the table to query. Must match a key in the
                schema dictionary exactly (case-sensitive).
            column_name: Name of the column to check.

        Returns:
            True if the column exists in the table, False otherwise.

        Example:
            >>> schema = {"orders": ["id", "amount"]}
            >>> provider = DictSchemaProvider(schema)
            >>> provider.column_exists("orders", "id")
            True
            >>> provider.column_exists("orders", "nonexistent")
            False
            >>> provider.column_exists("nonexistent", "id")
            False
        """
        if not table_name or not column_name:
            return False

        columns = self.schema.get(table_name, [])
        return column_name in columns

    def get_table_schema(
        self, table_name: str
    ) -> Optional[dict[str, dict[str, str]]]:
        """Return detailed schema information for a table.

        This implementation returns None, as the dictionary-based provider
        only stores column names, not detailed schema information such as
        data types or constraints. Subclasses can override this method to
        provide additional schema information if needed.

        Args:
            table_name: Name of the table to query.

        Returns:
            None, as detailed schema information is not available in the
            dictionary-based implementation.

        Example:
            >>> schema = {"orders": ["id", "amount"]}
            >>> provider = DictSchemaProvider(schema)
            >>> provider.get_table_schema("orders") is None
            True
        """
        return None

