"""
Registry module for lineage analysis.

This module provides registry classes for managing table definitions and
tracking lineage information across multiple SQL statements.
"""

from lineage_analyzer.registry.table_registry import TableRegistry

__all__ = ["TableRegistry"]

