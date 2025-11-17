"""
Table registry for managing table definitions.

This module defines the TableRegistry class, which manages all table definitions
during script execution, including registration, querying, and updating.
"""

import warnings
from typing import Any, Dict, List, Optional

from lineage_analyzer.exceptions import LineageError
from lineage_analyzer.models.column_lineage import ColumnLineage
from lineage_analyzer.models.dependency import ExpressionType
from lineage_analyzer.models.table_definition import TableDefinition, TableType


class TableRegistry:
    """Table registry: manages all table definitions during script execution.

    Responsibilities:
    1. Register new tables (CREATE TABLE/VIEW)
    2. Query table definitions
    3. Update table definitions (INSERT INTO)
    4. Track table lifecycle

    Usage:
        registry = TableRegistry()

        # Register new table
        registry.register_table(TableDefinition(name="t1", ...))

        # Query table
        table_def = registry.get_table("t1")

        # Check if table exists
        if registry.has_table("t1"):
            ...
    """

    def __init__(self) -> None:
        """Initialize a TableRegistry."""
        self.tables: Dict[str, TableDefinition] = {}
        self._statement_counter = 0  # Track which statement we're processing

    def register_table(self, table_def: TableDefinition) -> None:
        """Register a table definition.

        Args:
            table_def: Table definition.

        Raises:
            LineageError: If table already exists and cannot be overwritten.
        """
        table_name = self._normalize_table_name(table_def.name)

        if table_name in self.tables:
            # Table already exists, handle according to strategy
            existing = self.tables[table_name]

            # If it's a source table, don't allow overwriting
            if existing.is_source_table:
                raise LineageError(
                    f"Cannot redefine source table '{table_name}'. "
                    f"Source tables are assumed to exist before the script."
                )

            # If it's a table defined in the script, allow overwriting (e.g., DROP + CREATE)
            # but record a warning
            warnings.warn(
                f"Table '{table_name}' is being redefined at statement {self._statement_counter}. "
                f"Previous definition at statement {existing.created_at_statement} will be overwritten.",
                UserWarning,
            )

        # Set creation statement number
        if table_def.created_at_statement is None:
            table_def.created_at_statement = self._statement_counter

        self.tables[table_name] = table_def

    def get_table(self, name: str) -> Optional[TableDefinition]:
        """Get table definition.

        Args:
            name: Table name (supports schema.table format).

        Returns:
            TableDefinition or None if not found.
        """
        table_name = self._normalize_table_name(name)
        return self.tables.get(table_name)

    def has_table(self, name: str) -> bool:
        """Check if table exists.

        Args:
            name: Table name.

        Returns:
            True if table exists, False otherwise.
        """
        table_name = self._normalize_table_name(name)
        return table_name in self.tables

    def register_source_table(
        self, name: str, columns: Optional[List[str]] = None
    ) -> None:
        """Register a source table (exists outside the script).

        Args:
            name: Table name.
            columns: Optional list of column names.
        """
        table_name = self._normalize_table_name(name)

        if self.has_table(table_name):
            return  # Already exists, skip

        # Create table definition
        table_def = TableDefinition(
            name=table_name,
            table_type=TableType.EXTERNAL,
            is_source_table=True,
        )

        # Add columns (if provided)
        if columns:
            for col_name in columns:
                # Source table columns have no upstream dependencies
                table_def.add_column(
                    ColumnLineage(
                        name=col_name,
                        sources=[],  # Source table columns have no sources
                        expression_type=ExpressionType.DIRECT,
                    )
                )

        self.tables[table_name] = table_def

    def update_table_columns(
        self, table_name: str, new_columns: Dict[str, ColumnLineage]
    ) -> None:
        """Update table column definitions (for INSERT INTO).

        Args:
            table_name: Table name.
            new_columns: New column lineage dictionary.

        Raises:
            LineageError: If table doesn't exist.
        """
        table_def = self.get_table(table_name)
        if not table_def:
            raise LineageError(
                f"Cannot update table '{table_name}': table not found. "
                f"Make sure the table is created before INSERT INTO."
            )

        # Merge column definitions
        for col_name, col_lineage in new_columns.items():
            table_def.add_column(col_lineage)

    def get_all_tables(self) -> List[TableDefinition]:
        """Get all table definitions.

        Returns:
            List of all TableDefinition objects.
        """
        return list(self.tables.values())

    def get_source_tables(self) -> List[TableDefinition]:
        """Get all source tables.

        Returns:
            List of source TableDefinition objects.
        """
        return [t for t in self.tables.values() if t.is_source_table]

    def get_derived_tables(self) -> List[TableDefinition]:
        """Get all derived tables (non-source tables).

        Returns:
            List of derived TableDefinition objects.
        """
        return [t for t in self.tables.values() if not t.is_source_table]

    def increment_statement_counter(self) -> None:
        """Increment statement counter (called when processing each SQL statement)."""
        self._statement_counter += 1

    def reset(self) -> None:
        """Reset registry (for analyzing a new script)."""
        self.tables.clear()
        self._statement_counter = 0

    def remove_table(self, table_name: str) -> bool:
        """Remove table from Registry.

        Used for cleaning up CTEs and other temporary tables.

        Args:
            table_name: Table name

        Returns:
            bool: Whether the table was successfully removed
        """
        normalized_name = self._normalize_table_name(table_name)

        if normalized_name in self.tables:
            del self.tables[normalized_name]
            return True

        return False

    def _normalize_table_name(self, name: str) -> str:
        """Normalize table name (unify case, remove extra spaces).

        Args:
            name: Original table name.

        Returns:
            Normalized table name.
        """
        # Convert to lowercase (SQL is usually case-insensitive)
        # Can be configured if case sensitivity is needed
        return name.strip().lower()

    def to_dict(self) -> Dict[str, Any]:
        """Export to dictionary (for serialization).

        Returns:
            Dictionary representation of the registry.
        """
        return {
            "tables": {name: table.to_dict() for name, table in self.tables.items()},
            "statement_counter": self._statement_counter,
        }

