"""
Lineage analysis result model.

This module defines the LineageResult class, which represents the result
of a lineage analysis operation, including dependencies, warnings, and
metadata.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from lineage_analyzer.models.dependency import ColumnDependency
from lineage_analyzer.models.scope import Scope
from lineage_analyzer.utils.warnings import LineageWarning


@dataclass
class LineageResult:
    """Result of a lineage analysis operation.

    This class represents the result of analyzing a SQL query for
    field-level dependencies. It includes the dependencies, scope
    information, warnings, and metadata about the analysis.

    Attributes:
        dependencies: List of ColumnDependency objects representing
            field-level dependencies.
        scope: Optional Scope object containing table and column
            information.
        warnings: List of LineageWarning objects collected during
            analysis.
        sql: Original SQL query string that was analyzed.
        success: Whether the analysis was successful.
        error: Optional error message if the analysis failed.

    Example:
        >>> analyzer = LineageAnalyzer()
        >>> result = analyzer.analyze("SELECT id, name FROM users")
        >>> result.success
        True
        >>> len(result.dependencies) > 0
        True
    """

    dependencies: list[ColumnDependency]
    scope: Optional[Scope]
    warnings: list[LineageWarning]
    sql: str
    success: bool
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary format.

        This method converts the LineageResult to a dictionary
        representation that can be easily serialized to JSON or other
        formats.

        Returns:
            Dictionary representation of the result, including
            dependencies, tables, warnings, and metadata.

        Example:
            >>> result = analyzer.analyze("SELECT id FROM users")
            >>> data = result.to_dict()
            >>> data["success"]
            True
            >>> "dependencies" in data
            True
        """
        # Get unique tables from scope
        tables: list[str] = []
        if self.scope:
            unique_tables = {
                table.table for table in self.scope.tables.values()
            }
            tables = sorted(list(unique_tables))

        return {
            "success": self.success,
            "sql": self.sql,
            "dependencies": [dep.to_dict() for dep in self.dependencies],
            "tables": tables,
            "warnings": [
                {"level": w.level, "message": w.message, "context": w.context}
                for w in self.warnings
            ],
            "error": self.error,
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert result to JSON string.

        This method converts the LineageResult to a JSON string
        representation, suitable for serialization and storage.

        Args:
            indent: Number of spaces to use for indentation. Defaults to 2.

        Returns:
            JSON string representation of the result.

        Example:
            >>> result = analyzer.analyze("SELECT id FROM users")
            >>> json_str = result.to_json()
            >>> "dependencies" in json_str
            True
        """
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_graph(self) -> "DependencyGraph":
        """Convert result to dependency graph.

        This method converts the LineageResult to a DependencyGraph
        object, which provides graph-based analysis capabilities.

        Returns:
            DependencyGraph object representing the dependencies.

        Example:
            >>> result = analyzer.analyze("SELECT amount + tax AS total FROM orders")
            >>> graph = result.to_graph()
            >>> upstream = graph.get_upstream_columns("total")
            >>> len(upstream) == 2
            True
        """
        from lineage_analyzer.graph.dependency_graph import DependencyGraph

        graph = DependencyGraph()

        for dep in self.dependencies:
            graph.add_dependency(dep)

        return graph

    def get_source_tables(self) -> list[str]:
        """Get all source tables (deduplicated).

        This method returns a list of all unique source tables that
        appear in the dependencies.

        Returns:
            List of unique table names.

        Example:
            >>> result = analyzer.analyze("SELECT id FROM users")
            >>> tables = result.get_source_tables()
            >>> "users" in tables
            True
        """
        unique_tables = {dep.source.table for dep in self.dependencies}
        return sorted(list(unique_tables))

    def get_target_columns(self) -> list[str]:
        """Get all target columns (deduplicated).

        This method returns a list of all unique target columns that
        appear in the dependencies.

        Returns:
            List of unique target column names.

        Example:
            >>> result = analyzer.analyze("SELECT id, name FROM users")
            >>> targets = result.get_target_columns()
            >>> len(targets) == 2
            True
        """
        unique_columns = {dep.target.column for dep in self.dependencies}
        return sorted(list(unique_columns))

    def get_dependencies_for_target(
        self, target_column: str
    ) -> list[ColumnDependency]:
        """Get all dependencies for a specific target column.

        This method returns all dependencies that have the specified
        target column.

        Args:
            target_column: Name of the target column to filter by.

        Returns:
            List of ColumnDependency objects for the target column.

        Example:
            >>> result = analyzer.analyze("SELECT amount + tax AS total FROM orders")
            >>> deps = result.get_dependencies_for_target("total")
            >>> len(deps) == 2
            True
        """
        return [
            dep for dep in self.dependencies if dep.target.column == target_column
        ]

    def has_warnings(self) -> bool:
        """Check if there are any warnings.

        This method checks if the result contains any warnings (WARNING or ERROR level).
        INFO level messages are not considered warnings.

        Returns:
            True if there are warnings, False otherwise.

        Example:
            >>> result = analyzer.analyze("SELECT id FROM users")
            >>> result.has_warnings()
            False
        """
        return any(w.level in ("WARNING", "ERROR") for w in self.warnings)

    def has_errors(self) -> bool:
        """Check if there are any error-level warnings.

        This method checks if the result contains any warnings with
        ERROR level.

        Returns:
            True if there are error-level warnings, False otherwise.

        Example:
            >>> result = analyzer.analyze("SELECT id FROM users")
            >>> result.has_errors()
            False
        """
        return any(w.level == "ERROR" for w in self.warnings)

    def to_formatted_string(self, include_sql: bool = True) -> str:
        """Generate formatted result report.

        Args:
            include_sql: Whether to include original SQL.

        Returns:
            Human-readable text report.

        Example output:
            ================================================================================
            Lineage Analysis Result
            ================================================================================

            Status: ✓ Success

            SQL Query:
            ----------
            SELECT
              o.amount + o.tax AS total,
              c.name AS customer_name
            FROM orders o
            JOIN customers c ON o.customer_id = c.id

            Dependencies Found: 3
            --------------------
            1. orders.amount → total (computed)
               Expression: o.amount + o.tax

            2. orders.tax → total (computed)
               Expression: o.amount + o.tax

            3. customers.name → customer_name (direct)

            Source Tables: orders, customers
            Target Columns: total, customer_name

            Warnings: 0
            ================================================================================
        """
        from lineage_analyzer.models.dependency import ExpressionType
        from lineage_analyzer.utils.sql_formatter import format_sql

        lines = []
        lines.append("=" * 80)
        lines.append("Lineage Analysis Result")
        lines.append("=" * 80)
        lines.append("")

        # Status
        status_icon = "✓" if self.success else "✗"
        lines.append(
            f"Status: {status_icon} {'Success' if self.success else 'Failed'}"
        )
        lines.append("")

        # SQL
        if include_sql and self.sql:
            lines.append("SQL Query:")
            lines.append("-" * 10)
            lines.append(format_sql(self.sql))
            lines.append("")

        # Dependencies
        if self.dependencies:
            lines.append(f"Dependencies Found: {len(self.dependencies)}")
            lines.append("-" * 20)

            for i, dep in enumerate(self.dependencies, 1):
                source_full = f"{dep.source.table}.{dep.source.column}"
                target = dep.target.column
                expr_type = dep.expression_type.value

                lines.append(
                    f"{i}. {source_full} → {target} ({expr_type})"
                )

                if (
                    dep.expression
                    and dep.expression_type != ExpressionType.DIRECT
                ):
                    lines.append(f"   Expression: {dep.expression}")

                if dep.confidence < 1.0:
                    lines.append(f"   Confidence: {dep.confidence:.0%}")

                lines.append("")

            # Statistics
            lines.append(
                f"Source Tables: {', '.join(self.get_source_tables())}"
            )
            lines.append(
                f"Target Columns: {', '.join(self.get_target_columns())}"
            )
            lines.append("")

        # Warnings
        if self.warnings:
            lines.append(f"Warnings: {len(self.warnings)}")
            lines.append("-" * 10)
            for w in self.warnings:
                lines.append(f"[{w.level}] {w.message}")
            lines.append("")
        else:
            lines.append("Warnings: 0")
            lines.append("")

        # Error
        if not self.success and self.error:
            lines.append("Error:")
            lines.append("-" * 10)
            lines.append(self.error)
            lines.append("")

        lines.append("=" * 80)

        return "\n".join(lines)

