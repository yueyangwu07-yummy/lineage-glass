"""
Script analyzer for multi-statement SQL scripts.

This module defines the ScriptAnalyzer class, which analyzes entire SQL scripts
containing multiple statements and builds complete lineage graphs.
"""

from typing import Any, Dict, List, Optional

from lineage_analyzer.analyzer.create_table_analyzer import CreateTableAnalyzer
from lineage_analyzer.analyzer.insert_into_analyzer import InsertIntoAnalyzer
from lineage_analyzer.analyzer.with_cte_analyzer import WithCTEAnalyzer
from lineage_analyzer.exceptions import LineageError
from lineage_analyzer.models.classified_statement import ClassifiedStatement
from lineage_analyzer.models.config import LineageConfig
from lineage_analyzer.models.statement_type import StatementType
from lineage_analyzer.models.table_definition import TableDefinition
from lineage_analyzer.parser.script_splitter import ScriptSplitter
from lineage_analyzer.parser.statement_classifier import StatementClassifier
from lineage_analyzer.registry.table_registry import TableRegistry
from lineage_analyzer.schema.provider import SchemaProvider


class ScriptAnalyzer:
    """SQL script analyzer (v1.0 main entry point).

    Responsibilities:
    1. Split script into multiple SQL statements
    2. Classify and analyze each statement
    3. Build complete lineage graph

    Usage:
        analyzer = ScriptAnalyzer(config, schema_provider)
        result = analyzer.analyze_script(script)
    """

    def __init__(
        self,
        config: Optional[LineageConfig] = None,
        schema_provider: Optional[SchemaProvider] = None,
    ) -> None:
        """Initialize a ScriptAnalyzer.

        Args:
            config: LineageConfig for analysis configuration.
            schema_provider: Optional SchemaProvider for schema information.
        """
        self.config = config or LineageConfig()
        self.schema_provider = schema_provider

        # Initialize components
        self.registry = TableRegistry()
        self.splitter = ScriptSplitter()
        self.classifier = StatementClassifier()
        self.create_table_analyzer = CreateTableAnalyzer(
            self.registry, self.config, self.schema_provider
        )
        self.insert_into_analyzer = InsertIntoAnalyzer(
            self.registry, self.config, self.schema_provider
        )
        self.with_cte_analyzer = WithCTEAnalyzer(
            self.registry, self.config, self.schema_provider
        )

    def analyze_script(self, script: str) -> "ScriptAnalysisResult":
        """Analyze entire SQL script.

        Args:
            script: SQL script text.

        Returns:
            ScriptAnalysisResult: Analysis result.
        """
        from lineage_analyzer.models.script_analysis_result import (
            ScriptAnalysisResult,
        )

        # 1. Split script
        statements = self.splitter.split(script)

        # 2. Classify each statement
        classified_statements: List[ClassifiedStatement] = []
        for i, (ast, raw_sql) in enumerate(statements):
            classified = self.classifier.classify(ast, raw_sql, statement_index=i)
            classified_statements.append(classified)

        # 3. Analyze each statement
        analysis_results = []
        for classified in classified_statements:
            result = self._analyze_statement(classified)
            analysis_results.append(result)

            # Increment statement counter
            self.registry.increment_statement_counter()

        # 4. Build result
        return ScriptAnalysisResult(
            registry=self.registry,
            statements=classified_statements,
            analysis_results=analysis_results,
            config=self.config,
        )

    def _analyze_statement(
        self, statement: ClassifiedStatement
    ) -> Dict[str, Any]:
        """Analyze a single statement.

        Dispatch to different analyzers based on statement type.

        Args:
            statement: Classified statement.

        Returns:
            Dict: Analysis result (format varies by type).
        """
        stmt_type = statement.statement_type

        # === CREATE TABLE AS / CREATE TEMP TABLE ===
        if stmt_type in [
            StatementType.CREATE_TABLE_AS,
            StatementType.CREATE_TEMP_TABLE,
        ]:
            table_def = self.create_table_analyzer.analyze(statement)
            return {
                "type": "create_table",
                "table": table_def.to_dict(),
                "success": True,
            }

        # === CREATE VIEW ===
        elif stmt_type == StatementType.CREATE_VIEW:
            # View handling is similar to table, reuse CreateTableAnalyzer
            # Only table_type is different
            table_def = self.create_table_analyzer.analyze(statement)
            return {
                "type": "create_view",
                "view": table_def.to_dict(),
                "success": True,
            }

        # === SELECT ===
        elif stmt_type == StatementType.SELECT:
            # v1.0: Simple handling, don't register as table
            # TODO: Phase 3 support
            return {
                "type": "select",
                "success": True,
                "message": "SELECT statements are analyzed but not registered as tables",
            }

        # === INSERT INTO SELECT ===
        elif stmt_type == StatementType.INSERT_INTO_SELECT:
            try:
                updated_columns = self.insert_into_analyzer.analyze(statement)
                return {
                    "type": "insert_into",
                    "target_table": statement.target_table,
                    "updated_columns": [
                        col.to_dict() for col in updated_columns.values()
                    ],
                    "success": True,
                }
            except LineageError as e:
                return {
                    "type": "insert_into",
                    "success": False,
                    "error": str(e),
                }

        # === WITH CTE ===
        elif stmt_type == StatementType.WITH_CTE:
            return self.with_cte_analyzer.analyze(statement)

        # === Unsupported types ===
        else:
            return {
                "type": "unsupported",
                "success": False,
                "statement_type": stmt_type.value,
                "message": f"Statement type {stmt_type.value} is not supported",
            }

