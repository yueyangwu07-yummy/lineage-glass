"""
Warning system for lineage analysis.

This module defines warning and error collection functionality for the
lineage analyzer, allowing warnings and errors to be collected during
analysis and reported to users.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LineageWarning:
    """Warning or error message for lineage analysis.

    This class represents a warning or error message that occurred during
    lineage analysis. It includes the severity level, message text, and
    optional context information.

    Attributes:
        level: Severity level ("INFO", "WARNING", "ERROR").
        message: Warning or error message text.
        context: Optional context information (e.g., SQL snippet).

    Example:
        >>> warning = LineageWarning(
        ...     level="WARNING",
        ...     message="Ambiguous column name",
        ...     context="SELECT id FROM orders"
        ... )
        >>> warning.level
        'WARNING'
    """

    level: str
    message: str
    context: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate warning level."""
        valid_levels = ["INFO", "WARNING", "ERROR"]
        if self.level not in valid_levels:
            raise ValueError(
                f"Invalid warning level: {self.level}. "
                f"Must be one of {valid_levels}"
            )


class WarningCollector:
    """Collects warnings and errors during lineage analysis.

    This class provides functionality to collect warnings and errors
    during lineage analysis. It allows warnings to be added, queried,
    and retrieved for reporting to users.

    Attributes:
        warnings: List of LineageWarning objects collected during analysis.

    Example:
        >>> collector = WarningCollector()
        >>> collector.add("WARNING", "Ambiguous column name")
        >>> collector.has_errors()
        False
        >>> collector.add("ERROR", "Column not found")
        >>> collector.has_errors()
        True
        >>> len(collector.get_all())
        2
    """

    def __init__(self) -> None:
        """Initialize a WarningCollector."""
        self.warnings: list[LineageWarning] = []

    def add(
        self, level: str, message: str, context: Optional[str] = None
    ) -> None:
        """Add a warning or error message.

        This method adds a warning or error message to the collector.
        The message includes a severity level, message text, and optional
        context information.

        Args:
            level: Severity level ("INFO", "WARNING", "ERROR").
            message: Warning or error message text.
            context: Optional context information (e.g., SQL snippet).

        Example:
            >>> collector = WarningCollector()
            >>> collector.add("WARNING", "Ambiguous column", "SELECT id")
            >>> len(collector.warnings)
            1
        """
        warning = LineageWarning(level=level, message=message, context=context)
        self.warnings.append(warning)

    def has_errors(self) -> bool:
        """Check if any error-level warnings exist.

        This method checks if any warnings with "ERROR" level have been
        collected. This is useful for determining if the analysis should
        be considered failed.

        Returns:
            True if any error-level warnings exist, False otherwise.

        Example:
            >>> collector = WarningCollector()
            >>> collector.add("WARNING", "Some warning")
            >>> collector.has_errors()
            False
            >>> collector.add("ERROR", "Some error")
            >>> collector.has_errors()
            True
        """
        return any(warning.level == "ERROR" for warning in self.warnings)

    def get_all(self) -> list[LineageWarning]:
        """Get all collected warnings and errors.

        This method returns all warnings and errors that have been
        collected during analysis. The warnings are returned in the
        order they were added.

        Returns:
            List of LineageWarning objects.

        Example:
            >>> collector = WarningCollector()
            >>> collector.add("WARNING", "Warning 1")
            >>> collector.add("ERROR", "Error 1")
            >>> warnings = collector.get_all()
            >>> len(warnings)
            2
        """
        return self.warnings.copy()

    def get_by_level(self, level: str) -> list[LineageWarning]:
        """Get warnings and errors by severity level.

        This method returns all warnings and errors with the specified
        severity level. The warnings are returned in the order they were
        added.

        Args:
            level: Severity level to filter by ("INFO", "WARNING", "ERROR").

        Returns:
            List of LineageWarning objects with the specified level.

        Example:
            >>> collector = WarningCollector()
            >>> collector.add("WARNING", "Warning 1")
            >>> collector.add("ERROR", "Error 1")
            >>> collector.add("WARNING", "Warning 2")
            >>> warnings = collector.get_by_level("WARNING")
            >>> len(warnings)
            2
        """
        return [
            warning for warning in self.warnings if warning.level == level
        ]

    def clear(self) -> None:
        """Clear all collected warnings and errors.

        This method removes all warnings and errors from the collector,
        allowing it to be reused for a new analysis.

        Example:
            >>> collector = WarningCollector()
            >>> collector.add("WARNING", "Some warning")
            >>> collector.clear()
            >>> len(collector.get_all())
            0
        """
        self.warnings.clear()

    def add_ambiguity_warning(
        self,
        column_name: str,
        possible_tables: list[str],
        chosen_table: str,
        context: Optional[str] = None,
    ) -> None:
        """Add an ambiguity warning for a column name.

        This method adds a warning when a column name is ambiguous and
        a table has been chosen from multiple possibilities.

        Args:
            column_name: Name of the ambiguous column.
            possible_tables: List of table names that could contain the column.
            chosen_table: Name of the table that was chosen.
            context: Optional SQL context for the warning.

        Example:
            >>> collector = WarningCollector()
            >>> collector.add_ambiguity_warning(
            ...     "id", ["orders", "customers"], "orders", "SELECT id FROM ..."
            ... )
            >>> len(collector.get_all())
            1
        """
        message = (
            f"Column '{column_name}' is ambiguous. "
            f"Possible sources: {', '.join(possible_tables)}. "
            f"Using '{chosen_table}' (first table in FROM clause)."
        )
        self.add("WARNING", message, context)

    def add_schema_missing_warning(
        self,
        column_name: str,
        table_name: str,
        context: Optional[str] = None,
    ) -> None:
        """Add a warning when a column is not found in schema.

        This method adds a warning when a column is not found in the
        schema for a table, but processing continues.

        Args:
            column_name: Name of the column that was not found.
            table_name: Name of the table where the column was expected.
            context: Optional SQL context for the warning.

        Example:
            >>> collector = WarningCollector()
            >>> collector.add_schema_missing_warning(
            ...     "non_existent", "orders", "SELECT non_existent FROM orders"
            ... )
            >>> len(collector.get_all())
            1
        """
        message = (
            f"Column '{column_name}' not found in schema for table '{table_name}'. "
            f"Proceeding with assumption that it exists."
        )
        self.add("WARNING", message, context)

    def add_inference_warning(
        self,
        column_name: str,
        inferred_table: str,
        confidence: float,
        context: Optional[str] = None,
    ) -> None:
        """Add a warning when a column source is inferred.

        This method adds an informational warning when a column source
        is inferred with a certain confidence level.

        Args:
            column_name: Name of the column that was inferred.
            inferred_table: Name of the table that was inferred.
            confidence: Confidence level of the inference (0.0-1.0).
            context: Optional SQL context for the warning.

        Example:
            >>> collector = WarningCollector()
            >>> collector.add_inference_warning(
            ...     "id", "orders", 0.6, "SELECT id FROM orders o JOIN customers c"
            ... )
            >>> len(collector.get_all())
            1
        """
        message = (
            f"Inferred '{column_name}' comes from table '{inferred_table}' "
            f"(confidence: {confidence:.0%}). "
            f"Consider using table prefix for clarity."
        )
        self.add("INFO", message, context)

    def get_summary(self) -> dict[str, int]:
        """Get a summary of warnings by level.

        This method returns a dictionary with counts of warnings
        grouped by severity level.

        Returns:
            Dictionary with counts of warnings by level.

        Example:
            >>> collector = WarningCollector()
            >>> collector.add("INFO", "Info 1")
            >>> collector.add("WARNING", "Warning 1")
            >>> collector.add("ERROR", "Error 1")
            >>> collector.add("INFO", "Info 2")
            >>> summary = collector.get_summary()
            >>> summary == {"INFO": 2, "WARNING": 1, "ERROR": 1}
            True
        """
        summary: dict[str, int] = {"INFO": 0, "WARNING": 0, "ERROR": 0}
        for warning in self.warnings:
            summary[warning.level] = summary.get(warning.level, 0) + 1
        return summary

