"""
Lineage analyzer main entry point.

This module defines the LineageAnalyzer class, which is the main entry
point for analyzing SQL queries for field-level dependencies.
"""

from __future__ import annotations

from typing import Optional

from lineage_analyzer.analyzer.dependency_extractor import DependencyExtractor
from lineage_analyzer.analyzer.scope_builder import ScopeBuilder
from lineage_analyzer.analyzer.symbol_resolver import SymbolResolver
from lineage_analyzer.exceptions import LineageError
from lineage_analyzer.models.config import LineageConfig
from lineage_analyzer.models.result import LineageResult
from lineage_analyzer.models.scope import Scope
from lineage_analyzer.parser.sql_parser import SQLParser
from lineage_analyzer.schema.provider import SchemaProvider


class LineageAnalyzer:
    """Field-level lineage analyzer - main entry point.

    This class is the main entry point for analyzing SQL queries for
    field-level dependencies. It encapsulates the entire analysis
    workflow, from parsing SQL to extracting dependencies.

    Usage:
        >>> analyzer = LineageAnalyzer()
        >>> result = analyzer.analyze("SELECT id, name FROM users")
        >>> print(result.to_json())

    Attributes:
        config: LineageConfig object containing analyzer configuration.
        schema_provider: Optional SchemaProvider for schema validation.

    Example:
        >>> analyzer = LineageAnalyzer()
        >>> result = analyzer.analyze("SELECT id FROM users")
        >>> result.success
        True
        >>> len(result.dependencies) > 0
        True
    """

    def __init__(
        self,
        config: Optional[LineageConfig] = None,
        schema_provider: Optional[SchemaProvider] = None,
    ) -> None:
        """Initialize analyzer.

        This method initializes the LineageAnalyzer with the provided
        configuration and schema provider.

        Args:
            config: LineageConfig object (if None, uses default config).
            schema_provider: Optional SchemaProvider for schema validation.

        Example:
            >>> config = LineageConfig(strict_mode=True)
            >>> analyzer = LineageAnalyzer(config)
            >>> isinstance(analyzer.config, LineageConfig)
            True
        """
        self.config = config or LineageConfig()
        self.schema_provider = schema_provider

        # Lazy initialization of components
        self.parser: Optional[SQLParser] = None
        self.scope_builder: Optional[ScopeBuilder] = None

    def analyze(self, sql: str) -> LineageResult:
        """Analyze a SQL query and return field dependencies.

        This is the main method for analyzing SQL queries. It performs
        the complete analysis workflow:
        1. Parse SQL -> AST
        2. Build Scope (extract tables)
        3. Create SymbolResolver
        4. Extract dependencies
        5. Package as LineageResult and return

        Args:
            sql: SQL query string to analyze.

        Returns:
            LineageResult object containing dependencies and metadata.

        Raises:
            LineageError: Various subclasses of LineageError for different
                failure scenarios (parsing errors, ambiguity, etc.).

        Example:
            >>> analyzer = LineageAnalyzer()
            >>> result = analyzer.analyze("SELECT id, name FROM users")
            >>> result.success
            True
            >>> len(result.dependencies) == 2
            True
        """
        try:
            # Step 1: Parse SQL
            if not self.parser:
                self.parser = SQLParser(self.config)
            ast = self.parser.parse(sql)

            # Step 2: Build Scope
            if not self.scope_builder:
                self.scope_builder = ScopeBuilder(
                    self.config, self.schema_provider
                )
            scope = self.scope_builder.build_scope(ast)

            # Step 3: Create SymbolResolver
            resolver = SymbolResolver(scope, self.config, self.schema_provider)

            # Step 4: Extract Dependencies
            extractor = DependencyExtractor(scope, resolver, self.config)
            dependencies = extractor.extract(ast)

            # Step 5: Build Result
            result = LineageResult(
                dependencies=dependencies,
                scope=scope,
                warnings=resolver.warnings.get_all(),
                sql=sql,
                success=True,
            )

            return result

        except LineageError as e:
            # Wrap as failed Result instead of raising (user can choose how to handle)
            return LineageResult(
                dependencies=[],
                scope=None,
                warnings=[],
                sql=sql,
                success=False,
                error=str(e),
            )
        except NotImplementedError as e:
            # Wrap NotImplementedError as failed Result
            return LineageResult(
                dependencies=[],
                scope=None,
                warnings=[],
                sql=sql,
                success=False,
                error=str(e),
            )
        except Exception as e:
            # Unexpected errors
            raise LineageError(
                f"Unexpected error during analysis: {e}"
            ) from e

    def analyze_batch(self, sqls: list[str]) -> list[LineageResult]:
        """Analyze multiple SQL queries in batch.

        This method analyzes multiple SQL queries and returns a list
        of LineageResult objects, one for each query.

        Args:
            sqls: List of SQL query strings to analyze.

        Returns:
            List of LineageResult objects, one for each query.

        Example:
            >>> analyzer = LineageAnalyzer()
            >>> sqls = ["SELECT id FROM users", "SELECT amount FROM orders"]
            >>> results = analyzer.analyze_batch(sqls)
            >>> len(results) == 2
            True
            >>> all(r.success for r in results)
            True
        """
        return [self.analyze(sql) for sql in sqls]

