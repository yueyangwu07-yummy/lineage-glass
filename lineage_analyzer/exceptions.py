"""
Custom exception classes for lineage analysis.

This module defines all custom exceptions used throughout the lineage analyzer
package. These exceptions provide specific error types for different failure
scenarios in lineage analysis.
"""

from typing import Optional


class LineageError(Exception):
    """Base exception class for all lineage analysis errors.

    This exception serves as the base class for all custom exceptions in the
    lineage analyzer package. It provides a common interface for error handling
    and can be used to catch any lineage-related error.

    Attributes:
        message: Human-readable error message describing the error.
    """

    def __init__(self, message: str) -> None:
        """Initialize a LineageError with a message.

        Args:
            message: Error message describing what went wrong.
        """
        self.message = message
        super().__init__(self.message)


class AmbiguousColumnError(LineageError):
    """Exception raised when a column name is ambiguous.

    This exception is raised when a column name cannot be uniquely resolved
    because it exists in multiple tables within the same scope. For example,
    when joining two tables that both have a column named 'id', and the query
    references 'id' without a table prefix.

    Attributes:
        message: Error message describing the ambiguity.
        column_name: Name of the ambiguous column.
        possible_tables: List of tables that contain this column.
        sql: Optional SQL query for context.
        position: Optional character position of the column reference.
    """

    def __init__(
        self,
        message: str,
        column_name: str,
        possible_tables: Optional[list[str]] = None,
        sql: Optional[str] = None,
        position: Optional[int] = None,
    ) -> None:
        """Initialize an AmbiguousColumnError.

        Args:
            message: Error message describing the ambiguity.
            column_name: Name of the ambiguous column.
            possible_tables: Optional list of tables that contain this column.
            sql: Optional SQL query for context.
            position: Optional character position of the column reference.
        """
        self.column_name = column_name
        self.possible_tables = possible_tables or []
        self.sql = sql
        self.position = position

        # If possible_tables and sql are provided, build enhanced message
        if possible_tables and sql:
            message = self._build_message()

        super().__init__(message)

    def _build_message(self) -> str:
        """Build detailed error message with formatting."""
        from lineage_analyzer.utils.sql_formatter import (
            format_sql,
            highlight_column_in_query,
        )

        msg = [f"Column '{self.column_name}' is ambiguous.\n"]

        if self.possible_tables:
            msg.append("Possible sources:")
            for table in self.possible_tables:
                msg.append(f"  • {table}.{self.column_name}")

        if self.sql:
            msg.append("\nQuery:")
            # Format SQL
            formatted_sql = format_sql(self.sql)
            # Highlight column name
            highlighted = highlight_column_in_query(
                formatted_sql, self.column_name
            )
            msg.append(highlighted)

            if self.possible_tables:
                msg.append("\nSuggestion:")
                msg.append("  Use table prefix to clarify:")
                for i, table in enumerate(self.possible_tables):
                    # Assume first letter of table as alias
                    alias = table[0].lower() if table else "t"
                    msg.append(
                        f"    - {alias}.{self.column_name} (for {table}.{self.column_name})"
                    )

        return "\n".join(msg)


class UnresolvedReferenceError(LineageError):
    """Exception raised when a table or column reference cannot be resolved.

    This exception is raised when the analyzer encounters a reference to a
    table or column that cannot be found in the current scope or schema.
    This might happen when a table alias is misspelled or a column doesn't
    exist in the referenced table.

    Attributes:
        message: Error message describing the unresolved reference.
        reference: The unresolved reference name.
        available_tables: Optional list of available tables.
        sql: Optional SQL query for context.
    """

    def __init__(
        self,
        message: str,
        reference: str,
        available_tables: Optional[list[str]] = None,
        sql: Optional[str] = None,
    ) -> None:
        """Initialize an UnresolvedReferenceError.

        Args:
            message: Error message describing the unresolved reference.
            reference: The unresolved reference name.
            available_tables: Optional list of available tables.
            sql: Optional SQL query for context.
        """
        self.reference = reference
        self.available_tables = available_tables or []
        self.sql = sql

        # If available_tables and sql are provided, build enhanced message
        if available_tables and sql:
            message = self._build_message()

        super().__init__(message)

    def _build_message(self) -> str:
        """Build detailed error message with formatting."""
        from lineage_analyzer.utils.sql_formatter import format_sql

        msg = [f"Cannot resolve reference '{self.reference}'.\n"]

        if self.available_tables:
            msg.append("Available tables:")
            for table in self.available_tables:
                msg.append(f"  • {table}")
        else:
            msg.append("No tables found in FROM clause.")

        if self.sql:
            msg.append("\nQuery:")
            msg.append(format_sql(self.sql))

        return "\n".join(msg)


class SchemaValidationError(LineageError):
    """Exception raised when schema validation fails.

    This exception is raised when the analyzer attempts to validate a column
    or table against a schema, and the validation fails. This might occur
    when a column is referenced that doesn't exist in the table's schema,
    or when table metadata is invalid.

    Attributes:
        message: Error message describing the validation failure.
        table_name: Name of the table that failed validation.
        column_name: Name of the column that failed validation, if applicable.
    """

    def __init__(
        self, message: str, table_name: str, column_name: str | None = None
    ) -> None:
        """Initialize a SchemaValidationError.

        Args:
            message: Error message describing the validation failure.
            table_name: Name of the table that failed validation.
            column_name: Optional name of the column that failed validation.
        """
        super().__init__(message)
        self.table_name = table_name
        self.column_name = column_name

