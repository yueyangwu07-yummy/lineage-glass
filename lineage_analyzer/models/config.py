"""
Configuration model for lineage analysis.

This module defines the LineageConfig class and ErrorMode enum, which control
the behavior of the lineage analyzer, including error handling strategies and
analysis options.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ErrorMode(str, Enum):
    """Enumeration of error handling modes for lineage analysis.

    This enum defines how the lineage analyzer should behave when encountering
    errors or ambiguous situations during analysis. Different modes provide
    different levels of strictness and error tolerance.

    Attributes:
        FAIL: Raise an exception immediately when an error is encountered.
            This is the strictest mode and ensures that all errors are
            surfaced immediately.
        WARN: Log a warning message but continue processing. This mode allows
            the analysis to continue even when errors occur, but records them
            for later review.
        IGNORE: Silently ignore errors and continue processing. This mode
            provides maximum tolerance but may hide important issues.

    Example:
        >>> mode = ErrorMode.FAIL
        >>> mode.value
        'fail'
        >>> ErrorMode.values()
        ['fail', 'warn', 'ignore']
    """

    FAIL = "fail"
    WARN = "warn"
    IGNORE = "ignore"

    @classmethod
    def values(cls) -> list[str]:
        """Return a list of all possible error mode values.

        Returns:
            List of string values for all error modes in the enum.

        Example:
            >>> ErrorMode.values()
            ['fail', 'warn', 'ignore']
        """
        return [member.value for member in cls]


@dataclass
class LineageConfig:
    """Configuration settings for lineage analysis.

    This class contains all configuration options that control how the lineage
    analyzer processes SQL queries and handles various edge cases. It provides
    sensible defaults for all settings, making it easy to use with minimal
    configuration while allowing full customization when needed.

    Attributes:
        strict_mode: If True, enables strict validation and error checking.
            When False, the analyzer is more lenient and may allow some
            ambiguous or invalid constructs. Defaults to True.
        require_table_prefix: If True, requires all column references to
            include a table prefix (e.g., "table.column" instead of just
            "column"). This helps avoid ambiguity but may not be practical
            for all SQL dialects. Defaults to False.
        schema_validation: If True, validates that referenced columns exist
            in the provided schema. This requires a SchemaProvider to be
            configured. Defaults to False (not used in v0.1).
        expand_wildcards: If True, expands SELECT * into explicit column
            lists. This can help with lineage tracking but requires schema
            information. Defaults to False (not used in v0.1).
        include_implicit_dependencies: If True, includes implicit dependencies
            (e.g., columns used in WHERE clauses) in the lineage graph.
            Defaults to False (not supported in v0.1).
        on_ambiguity: Error handling mode when column name ambiguity is
            detected (e.g., same column name in multiple tables). Defaults
            to ErrorMode.FAIL.
        on_unresolved: Error handling mode when a table or column reference
            cannot be resolved. Defaults to ErrorMode.WARN.

    Example:
        >>> config = LineageConfig(strict_mode=True, require_table_prefix=False)
        >>> config.on_ambiguity
        <ErrorMode.FAIL: 'fail'>
        >>> config_dict = {
        ...     "strict_mode": False,
        ...     "on_unresolved": ErrorMode.IGNORE
        ... }
        >>> custom_config = LineageConfig(**config_dict)
    """

    strict_mode: bool = True
    require_table_prefix: bool = False
    schema_validation: bool = False
    expand_wildcards: bool = False
    include_implicit_dependencies: bool = False
    on_ambiguity: ErrorMode = ErrorMode.FAIL
    on_unresolved: ErrorMode = ErrorMode.WARN

    # Complexity limits
    max_expression_nodes: int = 1500  # Maximum nodes per expression
    max_expression_depth: int = 50  # Maximum nesting depth
    max_case_branches: int = 100  # Maximum CASE branches
    on_complexity_exceeded: ErrorMode = ErrorMode.FAIL  # Behavior when limits exceeded

    def __post_init__(self) -> None:
        """Validate configuration settings."""
        if not isinstance(self.strict_mode, bool):
            raise TypeError("strict_mode must be a boolean")
        if not isinstance(self.require_table_prefix, bool):
            raise TypeError("require_table_prefix must be a boolean")
        if not isinstance(self.schema_validation, bool):
            raise TypeError("schema_validation must be a boolean")
        if not isinstance(self.expand_wildcards, bool):
            raise TypeError("expand_wildcards must be a boolean")
        if not isinstance(self.include_implicit_dependencies, bool):
            raise TypeError("include_implicit_dependencies must be a boolean")
        if not isinstance(self.on_ambiguity, ErrorMode):
            raise TypeError("on_ambiguity must be an ErrorMode instance")
        if not isinstance(self.on_unresolved, ErrorMode):
            raise TypeError("on_unresolved must be an ErrorMode instance")

