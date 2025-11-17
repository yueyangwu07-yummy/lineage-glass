"""
Statement type enumeration.

This module defines the StatementType enum, which represents different types
of SQL statements that can be classified and analyzed.
"""

from enum import Enum


class StatementType(Enum):
    """SQL statement type enumeration.

    Classification rules:
    - SELECT: Pure query statement
    - CREATE_TABLE_AS: CREATE TABLE ... AS SELECT ...
    - CREATE_TABLE: CREATE TABLE ... (column definitions)
    - INSERT_INTO_SELECT: INSERT INTO ... SELECT ...
    - CREATE_VIEW: CREATE VIEW ... AS SELECT ...
    - CREATE_TEMP_TABLE: CREATE TEMPORARY TABLE ...
    - DROP_TABLE: DROP TABLE ...
    - TRUNCATE: TRUNCATE TABLE ...
    - WITH_CTE: WITH ... AS (...) SELECT ... (CTE query)
    - UNKNOWN: Unrecognized type
    - UNSUPPORTED: Recognized but unsupported type (e.g., UPDATE, DELETE)
    """

    # Supported types (v1.0)
    SELECT = "select"
    CREATE_TABLE_AS = "create_table_as"
    INSERT_INTO_SELECT = "insert_into_select"
    CREATE_VIEW = "create_view"
    CREATE_TEMP_TABLE = "create_temp_table"
    WITH_CTE = "with_cte"

    # Recognized but not processed types
    CREATE_TABLE = "create_table"  # Pure DDL, no lineage
    DROP_TABLE = "drop_table"
    TRUNCATE = "truncate"

    # Unsupported types (v1.0)
    UPDATE = "update"
    DELETE = "delete"
    MERGE = "merge"

    # Other
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"

    def is_supported(self) -> bool:
        """Check if this statement type is supported for analysis.

        Returns:
            True if the statement type is supported, False otherwise.
        """
        return self in [
            StatementType.SELECT,
            StatementType.CREATE_TABLE_AS,
            StatementType.INSERT_INTO_SELECT,
            StatementType.CREATE_VIEW,
            StatementType.CREATE_TEMP_TABLE,
            StatementType.WITH_CTE,
        ]

    def creates_table(self) -> bool:
        """Check if this statement type creates a table.

        Returns:
            True if the statement creates a table, False otherwise.
        """
        return self in [
            StatementType.CREATE_TABLE_AS,
            StatementType.CREATE_TABLE,
            StatementType.CREATE_TEMP_TABLE,
        ]

    def creates_view(self) -> bool:
        """Check if this statement type creates a view.

        Returns:
            True if the statement creates a view, False otherwise.
        """
        return self == StatementType.CREATE_VIEW

    def modifies_data(self) -> bool:
        """Check if this statement type modifies data.

        Returns:
            True if the statement modifies data, False otherwise.
        """
        return self in [
            StatementType.INSERT_INTO_SELECT,
            StatementType.UPDATE,
            StatementType.DELETE,
            StatementType.TRUNCATE,
        ]

