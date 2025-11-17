"""
Data models for lineage analysis.

This package contains all core data structures used for representing SQL
lineage information, including column references, table references, scopes,
dependencies, configuration, and results.
"""

from lineage_analyzer.models.column import ColumnRef
from lineage_analyzer.models.config import ErrorMode, LineageConfig
from lineage_analyzer.models.dependency import ColumnDependency, ExpressionType
from lineage_analyzer.models.result import LineageResult
from lineage_analyzer.models.scope import Scope
from lineage_analyzer.models.table import TableRef

__all__ = [
    "ColumnDependency",
    "ColumnRef",
    "ErrorMode",
    "ExpressionType",
    "LineageConfig",
    "LineageResult",
    "Scope",
    "TableRef",
]

