"""
Expression utility functions.

This module provides utility functions for working with SQL expressions,
including column deduplication, flattening, and complexity calculation.
"""

from __future__ import annotations

from typing import Any, Optional

import sqlglot
from sqlglot import expressions

from lineage_analyzer.models.column import ColumnRef


def deduplicate_columns(columns: list[ColumnRef]) -> list[ColumnRef]:
    """Remove duplicate column references from a list.

    This function removes duplicate column references from a list based
    on the fully qualified name (to_qualified_name()). It preserves the
    order of the first occurrence of each unique column.

    Args:
        columns: List of ColumnRef objects (may contain duplicates).

    Returns:
        List of unique ColumnRef objects, preserving order.

    Example:
        >>> col1 = ColumnRef(table="orders", column="id")
        >>> col2 = ColumnRef(table="orders", column="id")
        >>> cols = deduplicate_columns([col1, col2])
        >>> len(cols) == 1
        True
    """
    seen: dict[str, ColumnRef] = {}
    for col in columns:
        key = col.to_qualified_name()
        if key not in seen:
            seen[key] = col
    return list(seen.values())


def flatten_columns(nested_list: list[list[ColumnRef]]) -> list[ColumnRef]:
    """Flatten a nested list of column references.

    This function flattens a nested list of ColumnRef objects into a
    single flat list. It handles any level of nesting.

    Args:
        nested_list: Nested list of ColumnRef objects.

    Returns:
        Flat list of ColumnRef objects.

    Example:
        >>> col1 = ColumnRef(table="orders", column="id")
        >>> col2 = ColumnRef(table="orders", column="name")
        >>> nested = [[col1], [col2]]
        >>> flat = flatten_columns(nested)
        >>> len(flat) == 2
        True
    """
    result: list[ColumnRef] = []
    for item in nested_list:
        if isinstance(item, list):
            result.extend(flatten_columns(item))
        else:
            result.append(item)
    return result


def get_expression_complexity(expr: sqlglot.Expression) -> int:
    """Calculate the complexity of an expression (number of nodes).

    This function calculates the complexity of a SQL expression by
    counting the number of nodes in its AST. This is useful for
    debugging and performance monitoring.

    Args:
        expr: sqlglot expression node.

    Returns:
        Number of nodes in the expression tree.

    Example:
        >>> sql = "SELECT amount + tax FROM orders"
        >>> ast = sqlglot.parse_one(sql)
        >>> expr = ast.expressions[0]
        >>> complexity = get_expression_complexity(expr)
        >>> complexity > 0
        True
    """
    count = 1  # Count the current node
    for child in expr.walk():
        if child != expr:  # Don't count the root node twice
            count += 1
    return count


def contains_function(expr: sqlglot.Expression) -> bool:
    """Check if an expression contains a function call.

    This function recursively checks if an expression contains any
    function call nodes.

    Args:
        expr: sqlglot expression node.

    Returns:
        True if the expression contains a function call, False otherwise.

    Example:
        >>> sql = "SELECT UPPER(name) FROM users"
        >>> ast = sqlglot.parse_one(sql)
        >>> expr = ast.expressions[0]
        >>> contains_function(expr)
        True
    """
    for node in expr.walk():
        if isinstance(node, expressions.Func):
            return True
    return False


def contains_binary_op(expr: sqlglot.Expression) -> bool:
    """Check if an expression contains a binary operation.

    This function recursively checks if an expression contains any
    binary operation nodes (Add, Sub, Mul, Div, etc.).

    Args:
        expr: sqlglot expression node.

    Returns:
        True if the expression contains a binary operation, False otherwise.

    Example:
        >>> sql = "SELECT amount + tax FROM orders"
        >>> ast = sqlglot.parse_one(sql)
        >>> expr = ast.expressions[0]
        >>> contains_binary_op(expr)
        True
    """
    binary_ops = (
        expressions.Add,
        expressions.Sub,
        expressions.Mul,
        expressions.Div,
        expressions.Mod,
        expressions.EQ,
        expressions.NEQ,
        expressions.GT,
        expressions.GTE,
        expressions.LT,
        expressions.LTE,
        expressions.And,
        expressions.Or,
    )
    for node in expr.walk():
        if isinstance(node, binary_ops):
            return True
    return False


def is_aggregate_function(expr: sqlglot.Expression) -> bool:
    """Check if an expression is an aggregate function.

    This function checks if an expression is an aggregate function
    (SUM, COUNT, AVG, MIN, MAX, GROUP_CONCAT, etc.).

    Args:
        expr: sqlglot expression node.

    Returns:
        True if the expression is an aggregate function, False otherwise.

    Example:
        >>> sql = "SELECT COUNT(*) FROM users"
        >>> ast = sqlglot.parse_one(sql)
        >>> expr = ast.expressions[0]
        >>> is_aggregate_function(expr)
        True
    """
    # Check if it's an AggFunc node (base class for aggregate functions)
    if isinstance(expr, expressions.AggFunc):
        return True

    # Handle alias wrapper
    if isinstance(expr, expressions.Alias) and hasattr(expr, "this"):
        return is_aggregate_function(expr.this)

    # Check nested aggregate functions
    for node in expr.walk():
        if isinstance(node, expressions.AggFunc):
            return True

    return False


def is_window_function(expr: sqlglot.Expression) -> bool:
    """Check if an expression is a window function.

    This function checks if an expression is a window function (contains
    an OVER clause).

    Args:
        expr: sqlglot expression node.

    Returns:
        True if the expression is a window function, False otherwise.

    Example:
        >>> sql = "SELECT ROW_NUMBER() OVER (ORDER BY id) FROM users"
        >>> ast = sqlglot.parse_one(sql)
        >>> expr = ast.expressions[0]
        >>> is_window_function(expr)
        True
    """
    # Check if expression has Window node
    for node in expr.walk():
        if isinstance(node, expressions.Window):
            return True
        # Check if function has OVER clause (window attribute)
        if isinstance(node, expressions.Func):
            if hasattr(node, "over") and node.over:
                return True
            if hasattr(node, "args") and "over" in node.args:
                if node.args.get("over"):
                    return True

    return False

