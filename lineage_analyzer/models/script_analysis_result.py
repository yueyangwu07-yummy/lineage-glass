"""
Script analysis result model.

This module defines the ScriptAnalysisResult class, which represents the
complete analysis result of a SQL script.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from lineage_analyzer.models.classified_statement import ClassifiedStatement
from lineage_analyzer.models.column import ColumnRef
from lineage_analyzer.models.config import LineageConfig
from lineage_analyzer.models.lineage_path import LineagePath
from lineage_analyzer.models.table_definition import TableDefinition
from lineage_analyzer.registry.table_registry import TableRegistry


@dataclass
class ScriptAnalysisResult:
    """Script analysis result.

    Contains:
    1. TableRegistry (all table definitions)
    2. Classified statements list
    3. Analysis results for each statement

    Attributes:
        registry: Table registry.
        statements: List of classified statements.
        analysis_results: Analysis results for each statement.
        config: Configuration.
    """

    registry: TableRegistry
    statements: List[ClassifiedStatement]
    analysis_results: List[Dict[str, Any]]
    config: LineageConfig
    _resolver: Optional["TransitiveLineageResolver"] = field(
        default=None, init=False, repr=False
    )

    def get_all_tables(self) -> List[TableDefinition]:
        """Get all table definitions.

        Returns:
            List of all TableDefinition objects.
        """
        return self.registry.get_all_tables()

    def get_table(self, name: str) -> Optional[TableDefinition]:
        """Get specific table definition.

        Args:
            name: Table name.

        Returns:
            TableDefinition or None if not found.
        """
        return self.registry.get_table(name)

    def get_source_tables(self) -> List[TableDefinition]:
        """Get all source tables.

        Returns:
            List of source TableDefinition objects.
        """
        return self.registry.get_source_tables()

    def get_derived_tables(self) -> List[TableDefinition]:
        """Get all derived tables.

        Returns:
            List of derived TableDefinition objects.
        """
        return self.registry.get_derived_tables()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (for serialization).

        Returns:
            Dictionary representation of the result.
        """
        return {
            "tables": {
                name: table.to_dict()
                for name, table in self.registry.tables.items()
            },
            "statements_count": len(self.statements),
            "supported_statements": sum(
                1 for stmt in self.statements if stmt.is_supported()
            ),
            "analysis_results": self.analysis_results,
        }

    @property
    def resolver(self) -> "TransitiveLineageResolver":
        """Lazy-load transitive lineage resolver.

        Returns:
            TransitiveLineageResolver instance.
        """
        if self._resolver is None:
            from lineage_analyzer.resolver.transitive_resolver import (
                TransitiveLineageResolver,
            )

            self._resolver = TransitiveLineageResolver(self.registry)
        return self._resolver

    def trace(
        self, table_name: str, column_name: str
    ) -> List[LineagePath]:
        """Trace field to source.

        This is the most commonly used function, providing a concise interface.

        Args:
            table_name: Table name.
            column_name: Column name.

        Returns:
            List[LineagePath]: All lineage paths.
        """
        return self.resolver.trace_to_source(table_name, column_name)

    def impact(
        self, table_name: str, column_name: str
    ) -> List[ColumnRef]:
        """Impact analysis.

        Args:
            table_name: Table name.
            column_name: Column name.

        Returns:
            List[ColumnRef]: Affected downstream fields.
        """
        return self.resolver.find_impact(table_name, column_name)

    def explain(self, table_name: str, column_name: str) -> str:
        """Explain field's calculation chain.

        Args:
            table_name: Table name.
            column_name: Column name.

        Returns:
            str: Human-readable explanation text.
        """
        return self.resolver.explain_calculation(table_name, column_name)

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string.

        Args:
            indent: JSON indentation level.

        Returns:
            JSON string representation.
        """
        import json

        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

