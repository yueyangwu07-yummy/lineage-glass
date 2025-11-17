"""
Script splitter for SQL scripts.

This module defines the ScriptSplitter class, which splits SQL scripts containing
multiple statements into individual statements, preserving original text and
position information.
"""

from typing import List, Optional, Tuple

import sqlglot

from lineage_analyzer.exceptions import LineageError


class ScriptSplitter:
    """SQL script splitter.

    Responsibilities:
    1. Split SQL scripts containing multiple statements into individual statements
    2. Preserve original text and position information for each statement

    Usage:
        splitter = ScriptSplitter()
        statements = splitter.split("SELECT 1; SELECT 2;")
        # Returns: [(ast1, "SELECT 1"), (ast2, "SELECT 2")]
    """

    def split(
        self, script: str, dialect: Optional[str] = None
    ) -> List[Tuple[sqlglot.Expression, str]]:
        """Split SQL script.

        Args:
            script: SQL script text (may contain multiple statements).
            dialect: SQL dialect (None for auto-detect).

        Returns:
            List of (AST, raw_sql) tuples.

        Raises:
            LineageError: If parsing fails.
        """
        # Check for empty script first
        if not script or not script.strip():
            raise LineageError(
                "Script is empty or contains no valid SQL statements"
            )

        # Use sqlglot.parse() to parse multiple statements
        # Note: parse() returns a generator
        # Use None for dialect to let sqlglot auto-detect
        try:
            parsed_statements = list(sqlglot.parse(script, read=dialect))
        except Exception as e:
            raise LineageError(f"Failed to parse SQL script: {e}") from e

        # Filter out None values (sqlglot may return [None] for empty strings)
        valid_statements = [ast for ast in parsed_statements if ast is not None]

        if not valid_statements:
            raise LineageError(
                "Script is empty or contains no valid SQL statements"
            )

        # Extract original text for each statement
        result: List[Tuple[sqlglot.Expression, str]] = []
        for ast in valid_statements:

            # Use ast.sql() to regenerate SQL (may differ slightly from original)
            # If original format needs to be preserved, extract from original
            # text using position information
            raw_sql = ast.sql(dialect=dialect)

            result.append((ast, raw_sql))

        return result

    def split_preserving_original(
        self, script: str, dialect: Optional[str] = None
    ) -> List[Tuple[sqlglot.Expression, str]]:
        """Split script and preserve original SQL text (not regenerated).

        This method is more complex but preserves original format and comments.

        Current implementation: Simplified version, directly uses ast.sql()
        Future improvement: Extract from original text using AST position information.

        Args:
            script: SQL script.
            dialect: SQL dialect (None for auto-detect).

        Returns:
            List of (AST, original_sql) tuples.
        """
        # v1.0 simplified implementation: same as split()
        # TODO: Future improvement to position-based extraction
        return self.split(script, dialect)

