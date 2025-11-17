"""
Table definition model.

This module defines the TableDefinition class and TableType enum, which represent
the complete definition of a table, including its columns and lineage information.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from lineage_analyzer.models.column import ColumnRef
from lineage_analyzer.models.column_lineage import ColumnLineage


class TableType(Enum):
    """Table type enumeration."""

    TABLE = "table"  # Physical table
    VIEW = "view"  # View
    TEMP_TABLE = "temp_table"  # Temporary table
    CTE = "cte"  # CTE (WITH clause)
    EXTERNAL = "external"  # External source table (exists outside script)
    SUBQUERY = "subquery"  # Subquery (inline)


@dataclass
class TableDefinition:
    """Complete table definition.

    Used to record all tables that appear in a script (including temporary
    tables, views, physical tables).

    Attributes:
        name: Table name (fully qualified, e.g., "schema.table").
        columns: Column definition dictionary {column_name -> ColumnLineage}.
        table_type: Table type (TABLE/VIEW/TEMP_TABLE/EXTERNAL).
        created_by_sql: SQL statement that created this table (if CREATE TABLE AS).
        created_at_statement: Statement number in script where this table was created (0-indexed).
        is_source_table: Whether this is a source table (exists outside the script).
        is_recursive: Whether this is a recursive CTE (WITH RECURSIVE). Only applies to CTE tables.
        schema: Schema name (optional).
        database: Database name (optional).
        metadata: Additional metadata.

    Example:
        # Table created via CREATE TABLE AS
        TableDefinition(
            name="user_summary",
            columns={
                "user_id": ColumnLineage(name="user_id", sources=[...]),
                "total": ColumnLineage(name="total", sources=[...])
            },
            table_type=TableType.TABLE,
            created_by_sql="CREATE TABLE user_summary AS SELECT ...",
            created_at_statement=5
        )

        # Source table (exists outside script)
        TableDefinition(
            name="orders",
            columns={},  # Empty for now, can be filled later
            table_type=TableType.EXTERNAL,
            is_source_table=True
        )
    """

    name: str
    columns: Dict[str, ColumnLineage] = field(default_factory=dict)
    table_type: Optional[TableType] = None
    created_by_sql: Optional[str] = None
    created_at_statement: Optional[int] = None
    is_source_table: bool = False
    is_recursive: bool = False
    schema: Optional[str] = None
    database: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_column(self, column_lineage: ColumnLineage) -> None:
        """Add a column definition.

        Args:
            column_lineage: Column lineage information.
        """
        if column_lineage.name in self.columns:
            # If column already exists, merge lineage (for INSERT INTO)
            self.columns[column_lineage.name].merge_from(column_lineage)
        else:
            self.columns[column_lineage.name] = column_lineage

    def get_column(self, name: str) -> Optional[ColumnLineage]:
        """Get column definition.

        Args:
            name: Column name.

        Returns:
            ColumnLineage or None if column doesn't exist.
        """
        return self.columns.get(name)

    def has_column(self, name: str) -> bool:
        """Check if column exists.

        Args:
            name: Column name.

        Returns:
            True if column exists, False otherwise.
        """
        return name in self.columns

    def get_all_source_columns(self) -> List[ColumnRef]:
        """Get all source columns that all columns in this table depend on (recursive).

        Returns:
            Deduplicated list of source columns.
        """
        all_sources: List[ColumnRef] = []
        for column_lineage in self.columns.values():
            all_sources.extend(column_lineage.sources)

        # Deduplicate
        seen = set()
        unique_sources: List[ColumnRef] = []
        for source in all_sources:
            key = source.to_qualified_name()
            if key not in seen:
                seen.add(key)
                unique_sources.append(source)

        return unique_sources

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation of the TableDefinition.
        """
        return {
            "name": self.name,
            "columns": {name: col.to_dict() for name, col in self.columns.items()},
            "table_type": self.table_type.value if self.table_type else None,
            "created_by_sql": self.created_by_sql,
            "created_at_statement": self.created_at_statement,
            "is_source_table": self.is_source_table,
            "is_recursive": self.is_recursive,
            "schema": self.schema,
            "database": self.database,
            "metadata": self.metadata,
        }

