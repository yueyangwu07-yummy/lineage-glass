"""
WITH CTE statement analyzer.

This module defines the WithCTEAnalyzer class, which analyzes standalone
WITH CTE statements (not part of CREATE TABLE or INSERT).
"""

from __future__ import annotations

from typing import Dict, Any

import sqlglot
from sqlglot import exp

from lineage_analyzer.analyzer.cte_extractor import CTEExtractor, CTEDefinition
from lineage_analyzer.models.classified_statement import ClassifiedStatement
from lineage_analyzer.registry.table_registry import TableRegistry
from lineage_analyzer.models.config import LineageConfig
from lineage_analyzer.schema.provider import SchemaProvider


class WithCTEAnalyzer:
    """
    WITH CTE statement analyzer.

    Responsibilities:
    Analyze standalone WITH statements (e.g., WITH tmp AS (...) SELECT * FROM tmp)

    Note:
    Standalone WITH statements are typically used for queries, not creating
    persistent tables. We analyze CTEs themselves but don't register the
    final SELECT result.

    Usage:
        analyzer = WithCTEAnalyzer(registry, config, schema_provider)
        result = analyzer.analyze(stmt)
    """

    def __init__(
        self,
        registry: TableRegistry,
        config: LineageConfig,
        schema_provider: SchemaProvider = None,
    ):
        """
        Initialize a WithCTEAnalyzer.

        Args:
            registry: Table registry
            config: Lineage configuration
            schema_provider: Optional schema provider
        """
        self.registry = registry
        self.config = config
        self.schema_provider = schema_provider

        # Create CTE extractor (reuse Step 1 code)
        self.cte_extractor = CTEExtractor(
            registry=registry, config=config, schema_provider=schema_provider
        )

    def analyze(self, stmt: ClassifiedStatement) -> Dict[str, Any]:
        """
        Analyze WITH CTE statement.

        Args:
            stmt: Classified WITH_CTE statement

        Returns:
            Analysis result dictionary

        Logic:
        1. Extract CTE definitions
        2. Analyze and register CTEs
        3. Analyze main query (but don't create table)
        4. Clean up CTEs

        Note:
        Standalone WITH statements typically don't create tables, just queries.
        We analyze CTEs to ensure their lineage is recorded, but don't register
        the main query result.
        """
        try:
            # Get WITH statement AST
            ast = stmt.ast

            if not isinstance(ast, exp.Select):
                return {
                    "success": False,
                    "error": f"Expected SELECT node, got {type(ast).__name__}",
                    "type": "with_cte",
                }

            # Extract and register CTEs (reuse Step 1 logic)
            cte_tables = {}
            if self.cte_extractor.has_ctes(ast):
                ctes = self.cte_extractor.extract_ctes(ast)

                if ctes:
                    cte_tables = self.cte_extractor.analyze_and_register_ctes(
                        ctes, statement_index=stmt.statement_index
                    )

            # Clean up CTEs (standalone WITH statements cleanup after analysis)
            # Note: We don't expand lineage here because no persistent tables are created
            for cte_name in cte_tables.keys():
                if self.registry.has_table(cte_name):
                    self.registry.remove_table(cte_name)

            return {
                "success": True,
                "type": "with_cte",
                "cte_count": len(cte_tables),
                "cte_names": list(cte_tables.keys()),
                "message": f"Analyzed {len(cte_tables)} CTE(s), but no persistent tables created",
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "type": "with_cte",
            }

