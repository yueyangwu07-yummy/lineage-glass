"""
SQL parser implementation.

This module defines the SQLParser class, which converts SQL strings to
sqlglot AST objects for further analysis.
"""

from typing import Optional

import sqlglot
from sqlglot import expressions

from lineage_analyzer.exceptions import LineageError
from lineage_analyzer.models.config import LineageConfig
from lineage_analyzer.utils.ast_utils import is_select_statement


class SQLParser:
    """SQL parser that converts SQL strings to AST.

    This class provides functionality to parse SQL strings into abstract
    syntax trees (AST) using the sqlglot library. It handles error cases
    and validates that the SQL is a SELECT statement.

    Attributes:
        config: LineageConfig object containing parser configuration.

    Example:
        >>> config = LineageConfig()
        >>> parser = SQLParser(config)
        >>> sql = "SELECT id, name FROM users"
        >>> ast = parser.parse(sql)
        >>> is_select_statement(ast)
        True
    """

    def __init__(self, config: LineageConfig) -> None:
        """Initialize a SQLParser with configuration.

        Args:
            config: LineageConfig object containing parser configuration.
        """
        self.config = config

    def parse(self, sql: str) -> sqlglot.Expression:
        """Parse a SQL string into an AST.

        This method parses a SQL string into a sqlglot AST object. It
        validates that the SQL is a SELECT statement and handles parsing
        errors gracefully.

        Args:
            sql: SQL string to parse.

        Returns:
            sqlglot AST expression representing the parsed SQL.

        Raises:
            LineageError: If the SQL cannot be parsed or is not a SELECT statement.
            NotImplementedError: If the SQL is not a SELECT statement.

        Example:
            >>> parser = SQLParser(LineageConfig())
            >>> sql = "SELECT id FROM users"
            >>> ast = parser.parse(sql)
            >>> isinstance(ast, expressions.Select)
            True
        """
        if not sql or not sql.strip():
            raise LineageError("SQL string cannot be empty")

        try:
            # Parse the SQL string
            ast = sqlglot.parse_one(sql)

            if ast is None:
                raise LineageError(
                    f"Failed to parse SQL: {sql}. "
                    "The SQL might be invalid or unsupported."
                )

            # Check if it's a SELECT statement
            if not is_select_statement(ast):
                raise NotImplementedError(
                    f"Only SELECT statements are supported. "
                    f"Got: {type(ast).__name__}. "
                    f"SQL: {sql[:100]}..."
                )

            return ast

        except NotImplementedError:
            # Re-raise NotImplementedError without wrapping
            raise

        except sqlglot.errors.ParseError as e:
            # sqlglot parsing error
            error_msg = f"SQL parsing error: {str(e)}. SQL: {sql[:200]}..."
            raise LineageError(error_msg) from e

        except Exception as e:
            # Other unexpected errors
            error_msg = (
                f"Unexpected error while parsing SQL: {str(e)}. "
                f"SQL: {sql[:200]}..."
            )
            raise LineageError(error_msg) from e

