"""
Utility functions and helpers for lineage analysis.

This package contains utility functions and helper classes that support
the lineage analyzer, such as string manipulation, validation, and common
operations.
"""

from lineage_analyzer.utils.expression_utils import (
    contains_binary_op,
    contains_function,
    deduplicate_columns,
    flatten_columns,
    get_expression_complexity,
    is_aggregate_function,
    is_window_function,
)
from lineage_analyzer.utils.warnings import LineageWarning, WarningCollector

__all__ = [
    "contains_binary_op",
    "contains_function",
    "deduplicate_columns",
    "flatten_columns",
    "get_expression_complexity",
    "is_aggregate_function",
    "is_window_function",
    "LineageWarning",
    "WarningCollector",
]

