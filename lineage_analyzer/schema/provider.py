"""
Abstract schema provider interface.

This module defines the SchemaProvider abstract base class, which provides
an interface for schema information providers. Implementations of this class
can retrieve schema information from various sources (databases, files,
APIs, etc.) to support lineage analysis and validation.
"""

from abc import ABC, abstractmethod
from typing import Optional


class SchemaProvider(ABC):
    """Abstract interface for schema information providers.

    SchemaProvider defines the contract that all schema information providers
    must implement. It provides methods for querying table and column
    information, which the lineage analyzer uses to validate references and
    resolve table structures.

    Implementations of SchemaProvider can retrieve schema information from
    various sources, such as:
    - Database catalogs (PostgreSQL, MySQL, etc.)
    - Data dictionaries or metadata stores
    - Configuration files (JSON, YAML, etc.)
    - APIs or web services

    Attributes:
        None (abstract base class has no attributes)

    Example:
        >>> class MySchemaProvider(SchemaProvider):
        ...     def get_table_columns(self, table_name: str) -> list[str]:
        ...         return ["col1", "col2"]
        ...     def column_exists(self, table_name: str, column_name: str) -> bool:
        ...         return column_name in self.get_table_columns(table_name)
    """

    @abstractmethod
    def get_table_columns(self, table_name: str) -> list[str]:
        """Return all column names for a given table.

        Retrieves the list of column names for a specified table. This method
        is used by the lineage analyzer to validate column references and to
        expand wildcard selections (SELECT *).

        Args:
            table_name: Name of the table to query. May be a fully qualified
                name (e.g., "database.schema.table") or a simple name,
                depending on the implementation.

        Returns:
            List of column names for the specified table. Returns an empty
            list if the table does not exist or has no columns.

        Raises:
            NotImplementedError: Must be implemented by subclasses.
            ValueError: If table_name is invalid or None.

        Example:
            >>> provider = MySchemaProvider()
            >>> columns = provider.get_table_columns("orders")
            >>> "order_id" in columns
            True
        """
        pass

    def get_columns(self, table_name: str) -> list[str]:
        """Alias for get_table_columns for backward compatibility.

        This method is an alias for get_table_columns() to maintain
        backward compatibility with existing code.

        Args:
            table_name: Name of the table to query.

        Returns:
            List of column names for the specified table.

        Example:
            >>> provider = MySchemaProvider()
            >>> columns = provider.get_columns("orders")
            >>> "order_id" in columns
            True
        """
        return self.get_table_columns(table_name)

    @abstractmethod
    def column_exists(self, table_name: str, column_name: str) -> bool:
        """Check if a column exists in a table.

        Verifies whether a specific column exists in the specified table.
        This method is used by the lineage analyzer to validate column
        references before creating lineage relationships.

        Args:
            table_name: Name of the table to query. May be a fully qualified
                name (e.g., "database.schema.table") or a simple name,
                depending on the implementation.
            column_name: Name of the column to check.

        Returns:
            True if the column exists in the table, False otherwise.

        Raises:
            NotImplementedError: Must be implemented by subclasses.
            ValueError: If table_name or column_name is invalid or None.

        Example:
            >>> provider = MySchemaProvider()
            >>> provider.column_exists("orders", "order_id")
            True
            >>> provider.column_exists("orders", "nonexistent")
            False
        """
        pass

    def get_table_schema(
        self, table_name: str
    ) -> Optional[dict[str, dict[str, str]]]:
        """Return detailed schema information for a table (optional).

        This is an optional method that can be implemented to provide
        additional schema information beyond column names, such as data types,
        constraints, or other metadata. The default implementation returns
        None, indicating that detailed schema information is not available.

        Args:
            table_name: Name of the table to query.

        Returns:
            Dictionary containing schema information, or None if not
            implemented. The structure of the dictionary is implementation-
            specific.

        Example:
            >>> provider = MySchemaProvider()
            >>> schema = provider.get_table_schema("orders")
            >>> schema is None or isinstance(schema, dict)
            True
        """
        return None

