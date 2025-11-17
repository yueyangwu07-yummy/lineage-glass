"""
SQL formatting and highlighting utilities.

This module provides functionality to format SQL statements and highlight
specific positions or columns for better error reporting and debugging.
"""

from __future__ import annotations

import re
from typing import Optional

import sqlglot


def format_sql(sql: str, dialect: str = "generic") -> str:
    """Format SQL statement.

    Uses sqlglot's built-in formatter to generate readable SQL.

    Args:
        sql: Original SQL.
        dialect: SQL dialect.

    Returns:
        Formatted SQL.

    Example:
        Input: "SELECT id,name FROM users WHERE age>18"
        Output:
        SELECT
          id,
          name
        FROM users
        WHERE
          age > 18
    """
    try:
        ast = sqlglot.parse_one(sql, dialect=dialect)
        return ast.sql(pretty=True, dialect=dialect)
    except Exception:
        # If parsing fails, return original SQL
        return sql


def highlight_position(
    sql: str,
    position: int,
    length: int = 1,
    context_lines: int = 2,
) -> str:
    """Highlight a specific position in SQL.

    Used to mark error positions or warning positions.

    Args:
        sql: SQL statement.
        position: Character position (0-based).
        length: Highlight length.
        context_lines: Number of context lines.

    Returns:
        SQL text with highlighting.

    Example:
        Input: "SELECT id FROM users", position=7
        Output:
        SELECT id FROM users
               ^^
    """
    lines = sql.split("\n")

    # Find the line containing this position
    current_pos = 0
    target_line = 0
    col_in_line = 0

    for i, line in enumerate(lines):
        line_len = len(line) + 1  # +1 for newline
        if current_pos + line_len > position:
            target_line = i
            col_in_line = position - current_pos
            break
        current_pos += line_len

    # Build output
    result = []

    # Show context
    start_line = max(0, target_line - context_lines)
    end_line = min(len(lines), target_line + context_lines + 1)

    for i in range(start_line, end_line):
        line = lines[i]
        result.append(f"{i+1:3d} | {line}")

        # Add indicator below target line
        if i == target_line:
            pointer = " " * (col_in_line + 6)  # 6 = "xxx | " length
            pointer += "^" * length
            result.append(pointer)

    return "\n".join(result)


def highlight_column_in_query(
    sql: str,
    column_name: str,
    table_qualifier: Optional[str] = None,
) -> str:
    """Highlight all occurrences of a specific column in SQL.

    Args:
        sql: SQL statement.
        column_name: Column name.
        table_qualifier: Table prefix (optional).

    Returns:
        SQL with highlighting.

    Example:
        Input: "SELECT id, name FROM users WHERE id > 10"
               column_name="id"
        Output:
        SELECT **id**, name FROM users WHERE **id** > 10
                ^^                            ^^
    """
    # Build regex pattern
    if table_qualifier:
        pattern = rf"\b{re.escape(table_qualifier)}\.{re.escape(column_name)}\b"
    else:
        pattern = rf"\b{re.escape(column_name)}\b"

    # Find all match positions
    matches = list(re.finditer(pattern, sql, re.IGNORECASE))

    if not matches:
        return sql

    # Add markers below each match position
    lines = sql.split("\n")
    result = []

    for line_num, line in enumerate(lines):
        result.append(line)

        # Find all matches in this line
        line_start = sum(len(l) + 1 for l in lines[:line_num])
        line_matches = [
            m
            for m in matches
            if line_start <= m.start() < line_start + len(line)
        ]

        if line_matches:
            marker = [" "] * len(line)
            for match in line_matches:
                col = match.start() - line_start
                for i in range(
                    col, min(col + len(match.group()), len(line))
                ):
                    marker[i] = "^"
            result.append("".join(marker))

    return "\n".join(result)

