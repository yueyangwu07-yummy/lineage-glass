"""
Lineage analyzer module.

This package contains analysis functionality for the lineage analyzer,
including the LineageAnalyzer main entry point, ScopeBuilder class that
builds scope objects from AST, the SymbolResolver class that resolves
column references, the ExpressionVisitor class that extracts columns
from expressions, and the DependencyExtractor class that extracts
field-level dependencies.
"""

from lineage_analyzer.analyzer.dependency_extractor import DependencyExtractor
from lineage_analyzer.analyzer.expression_visitor import ExpressionVisitor
from lineage_analyzer.analyzer.lineage_analyzer import LineageAnalyzer
from lineage_analyzer.analyzer.scope_builder import ScopeBuilder
from lineage_analyzer.analyzer.symbol_resolver import SymbolResolver

__all__ = [
    "DependencyExtractor",
    "ExpressionVisitor",
    "LineageAnalyzer",
    "ScopeBuilder",
    "SymbolResolver",
]

