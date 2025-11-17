"""
Schema provider interfaces and implementations.

This package contains abstract interfaces and concrete implementations for
providing schema information to the lineage analyzer. Schema providers allow
the analyzer to validate column references and resolve table structures.
"""

from lineage_analyzer.schema.dict_provider import DictSchemaProvider
from lineage_analyzer.schema.provider import SchemaProvider

__all__ = [
    "DictSchemaProvider",
    "SchemaProvider",
]

