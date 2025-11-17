"""
Classified statement model.

This module defines the ClassifiedStatement class, which represents a SQL
statement that has been classified and contains extracted key information.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import sqlglot

from lineage_analyzer.models.statement_type import StatementType


@dataclass
class ClassifiedStatement:
    """Classified SQL statement.

    Contains statement type and extracted key information.

    Attributes:
        statement_type: Statement type.
        ast: sqlglot AST object.
        raw_sql: Original SQL text.

        # Extracted key information (varies by type)
        target_table: Target table name (for CREATE/INSERT target).
        query_ast: Query part AST (SELECT part).
        is_temporary: Whether this is a temporary table.

        # Metadata
        statement_index: Position in script (0-indexed).
        metadata: Additional information.

    Example:
        # SELECT statement
        ClassifiedStatement(
            statement_type=StatementType.SELECT,
            ast=...,
            raw_sql="SELECT * FROM users",
            query_ast=...  # Same as entire AST
        )

        # CREATE TABLE AS
        ClassifiedStatement(
            statement_type=StatementType.CREATE_TABLE_AS,
            ast=...,
            raw_sql="CREATE TABLE t1 AS SELECT * FROM users",
            target_table="t1",
            query_ast=...  # SELECT part
        )

        # INSERT INTO SELECT
        ClassifiedStatement(
            statement_type=StatementType.INSERT_INTO_SELECT,
            ast=...,
            raw_sql="INSERT INTO t1 SELECT * FROM users",
            target_table="t1",
            query_ast=...  # SELECT part
        )
    """

    statement_type: StatementType
    ast: sqlglot.Expression
    raw_sql: str

    # Extracted key information
    target_table: Optional[str] = None
    query_ast: Optional[sqlglot.Expression] = None
    is_temporary: bool = False

    # Metadata
    statement_index: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_supported(self) -> bool:
        """Check if this statement is supported for analysis.

        Returns:
            True if the statement is supported, False otherwise.
        """
        return self.statement_type.is_supported()

    def has_query(self) -> bool:
        """Check if this statement contains a query part (SELECT).

        Returns:
            True if the statement has a query part, False otherwise.
        """
        return self.query_ast is not None

