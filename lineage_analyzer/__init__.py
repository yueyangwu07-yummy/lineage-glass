"""
SQL Field-Level Lineage Analyzer v1.0

A powerful tool for analyzing field-level data lineage in SQL scripts.
Trace any field from its final destination back to its original source tables.

Example:
    >>> from lineage_analyzer import ScriptAnalyzer
    >>> analyzer = ScriptAnalyzer()
    >>> result = analyzer.analyze_script(sql_script)
    >>> paths = result.trace("table_name", "column_name")
"""

from lineage_analyzer.version import __version__, __version_info__

__author__ = "Lineage Analyzer Contributors"

from lineage_analyzer.analyzer.lineage_analyzer import LineageAnalyzer
from lineage_analyzer.exceptions import (
    AmbiguousColumnError,
    LineageError,
    SchemaValidationError,
    UnresolvedReferenceError,
)
from lineage_analyzer.analyzer.script_analyzer import ScriptAnalyzer
from lineage_analyzer.models.classified_statement import ClassifiedStatement
from lineage_analyzer.models.column import ColumnRef
from lineage_analyzer.models.column_lineage import ColumnLineage
from lineage_analyzer.models.config import ErrorMode, LineageConfig
from lineage_analyzer.models.dependency import ColumnDependency, ExpressionType
from lineage_analyzer.models.lineage_path import LineageNode, LineagePath
from lineage_analyzer.models.result import LineageResult
from lineage_analyzer.models.script_analysis_result import ScriptAnalysisResult
from lineage_analyzer.models.statement_type import StatementType
from lineage_analyzer.models.table import TableRef
from lineage_analyzer.models.table_definition import TableDefinition, TableType
from lineage_analyzer.parser.script_splitter import ScriptSplitter
from lineage_analyzer.parser.statement_classifier import StatementClassifier
from lineage_analyzer.registry.table_registry import TableRegistry
from lineage_analyzer.resolver.transitive_resolver import TransitiveLineageResolver
from lineage_analyzer.schema.dict_provider import DictSchemaProvider
from lineage_analyzer.schema.provider import SchemaProvider

__all__ = [
    # Version info
    "__version__",
    "__version_info__",
    # Core analyzers
    "ScriptAnalyzer",
    "LineageAnalyzer",
    # Configuration
    "LineageConfig",
    "ErrorMode",
    # Results
    "ScriptAnalysisResult",
    "LineagePath",
    "LineageNode",
    "LineageResult",
    # Data models
    "ColumnRef",
    "TableRef",
    "ColumnDependency",
    "ExpressionType",
    "ColumnLineage",
    "TableDefinition",
    "TableType",
    # Registry
    "TableRegistry",
    # Schema
    "SchemaProvider",
    "DictSchemaProvider",
    # Exceptions
    "LineageError",
    "AmbiguousColumnError",
    "UnresolvedReferenceError",
    "SchemaValidationError",
    # Parser
    "ScriptSplitter",
    "StatementClassifier",
    "StatementType",
    "ClassifiedStatement",
    # Resolver
    "TransitiveLineageResolver",
]

