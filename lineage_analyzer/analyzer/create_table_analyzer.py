"""
CREATE TABLE AS analyzer for lineage analysis.

This module defines the CreateTableAnalyzer class, which analyzes CREATE TABLE AS
statements and extracts column lineage information.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional

import sqlglot

from lineage_analyzer.analyzer.cte_extractor import CTEExtractor
from lineage_analyzer.analyzer.dependency_extractor import DependencyExtractor
from lineage_analyzer.analyzer.scope_builder import ScopeBuilder
from lineage_analyzer.analyzer.symbol_resolver import SymbolResolver
from lineage_analyzer.exceptions import LineageError
from lineage_analyzer.models.classified_statement import ClassifiedStatement
from lineage_analyzer.models.column_lineage import ColumnLineage
from lineage_analyzer.models.config import LineageConfig
from lineage_analyzer.models.dependency import ColumnDependency
from lineage_analyzer.models.table_definition import TableDefinition, TableType
from lineage_analyzer.registry.table_registry import TableRegistry
from lineage_analyzer.schema.provider import SchemaProvider


class CreateTableAnalyzer:
    """CREATE TABLE AS statement analyzer.

    Responsibilities:
    1. Analyze CREATE TABLE ... AS SELECT ... statements
    2. Extract target table column definitions
    3. Analyze field dependencies in SELECT part
    4. Build TableDefinition and register to Registry

    Process:
        CREATE TABLE t1 AS SELECT a + b AS total FROM orders
        ↓
        1. Extract target table name: t1
        2. Analyze SELECT:
           - total comes from orders.a and orders.b
        3. Build TableDefinition:
           - t1.total sources are [orders.a, orders.b]
        4. Register to Registry

    Usage:
        analyzer = CreateTableAnalyzer(registry, config)
        table_def = analyzer.analyze(classified_statement)
    """

    def __init__(
        self,
        registry: TableRegistry,
        config: LineageConfig,
        schema_provider: Optional[SchemaProvider] = None,
    ) -> None:
        """Initialize a CreateTableAnalyzer.

        Args:
            registry: TableRegistry to register created tables.
            config: LineageConfig for analysis configuration.
            schema_provider: Optional SchemaProvider for schema information.
        """
        self.registry = registry
        self.config = config
        self.schema_provider = schema_provider

        # Create CTE extractor
        self.cte_extractor = CTEExtractor(
            registry=registry, config=config, schema_provider=schema_provider
        )

    def analyze(self, statement: ClassifiedStatement) -> TableDefinition:
        """Analyze a CREATE TABLE AS statement.

        Args:
            statement: Classified statement (must be CREATE_TABLE_AS or CREATE_TEMP_TABLE).

        Returns:
            TableDefinition: Definition of the newly created table.

        Raises:
            LineageError: If statement type is incorrect or analysis fails.
        """
        # 1. Validate statement type
        if not (
            statement.statement_type.creates_table()
            or statement.statement_type.creates_view()
        ):
            raise LineageError(
                f"CreateTableAnalyzer only handles table/view creation statements, "
                f"got: {statement.statement_type}"
            )

        if not statement.has_query():
            raise LineageError(
                f"CREATE TABLE statement has no query part. "
                f"Only CREATE TABLE AS SELECT is supported."
            )

        # 2. Extract target table name
        target_table = statement.target_table
        if not target_table:
            raise LineageError(
                "Cannot extract target table name from CREATE TABLE AS"
            )

        # 3. Analyze field dependencies in SELECT part
        query_ast = statement.query_ast
        if query_ast is None:
            raise LineageError("Query AST is None")

        # Check if CREATE statement has WITH clause (CTE)
        # In CREATE TABLE AS, WITH clause is at CREATE level, not SELECT level
        # Extract and register CTEs before analyzing main query
        cte_tables = {}
        
        # Check CREATE AST for WITH clause first (for CREATE TABLE AS WITH ... SELECT)
        create_ast = statement.ast
        if isinstance(create_ast, sqlglot.expressions.Create):
            create_with = create_ast.args.get("with")
            if create_with:
                # Extract CTEs from CREATE's WITH clause
                # Create a temporary SELECT node that includes the WITH clause for extraction
                # We'll extract CTEs from the WITH node directly
                if hasattr(create_with, "expressions"):
                    # Use CTEExtractor to extract CTEs (handles both Select and Union)
                    # Create a temporary Select node with the WITH clause for extraction
                    if isinstance(query_ast, sqlglot.expressions.Select):
                        # Temporarily add WITH to query_ast for extraction
                        original_with = query_ast.args.get('with')
                        query_ast.args['with'] = create_with
                        
                        if self.cte_extractor.has_ctes(query_ast):
                            ctes = self.cte_extractor.extract_ctes(query_ast)
                            
                            if ctes:
                                # Analyze and register CTEs (before analyzing main query)
                                cte_tables = self.cte_extractor.analyze_and_register_ctes(
                                    ctes, statement_index=statement.statement_index
                                )

                                # Record log (optional)
                                if cte_tables:
                                    pass
                        
                        # Restore original WITH (or remove if it wasn't there)
                        if original_with:
                            query_ast.args['with'] = original_with
                        elif 'with' in query_ast.args:
                            del query_ast.args['with']
        
        # Also check query_ast for WITH clause (for cases where WITH is in SELECT)
        # AND check Create node for WITH clause (CREATE TABLE AS WITH ...)
        if not cte_tables:
            # First, check if WITH is in the Create node itself
            if isinstance(statement.ast, sqlglot.expressions.Create):
                create_ast = statement.ast
                with_node = create_ast.args.get('with')
                if with_node:
                    # WITH clause is in Create node, need to extract CTEs from it
                    # Create a temporary Select node with the WITH clause for extraction
                    # We can use the query_ast and add the WITH clause to it
                    if isinstance(query_ast, sqlglot.expressions.Select):
                        # Temporarily add WITH to query_ast for extraction
                        query_ast.args['with'] = with_node
                        if self.cte_extractor.has_ctes(query_ast):
                            ctes = self.cte_extractor.extract_ctes(query_ast)
                            # Remove WITH from query_ast (it's only for CTE extraction)
                            # The actual query doesn't need it since CTEs are already registered
                            # But we should keep it for now to avoid breaking things
            # Also check query_ast directly (for cases where WITH is in SELECT)
            if not cte_tables and isinstance(query_ast, sqlglot.expressions.Select):
                if self.cte_extractor.has_ctes(query_ast):
                    # 1. Extract CTE definitions
                    ctes = self.cte_extractor.extract_ctes(query_ast)
                    
                    # 2. Analyze and register CTEs (before analyzing main query)
                    cte_tables = self.cte_extractor.analyze_and_register_ctes(
                        ctes, statement_index=statement.statement_index
                    )

                    # Record log (optional)
                    if cte_tables:
                        pass

        try:
            # Analyze main query (CTEs are now in Registry)
            column_lineages = self._analyze_query(query_ast)
        except Exception as e:
            # Ensure CTEs are cleaned up even on error
            self._cleanup_ctes(cte_tables)
            raise e

        # 4. Build TableDefinition
        if statement.statement_type.creates_view():
            table_type = TableType.VIEW
        elif statement.is_temporary:
            table_type = TableType.TEMP_TABLE
        else:
            table_type = TableType.TABLE

        table_def = TableDefinition(
            name=target_table,
            columns={col.name: col for col in column_lineages},
            table_type=table_type,
            created_by_sql=statement.raw_sql,
            created_at_statement=statement.statement_index,
            is_source_table=False,
        )

        # 5. Register to Registry (before cleanup so expansion can work)
        self.registry.register_table(table_def)

        # 6. Clean up CTEs after analysis (CTEs are only valid within this statement)
        # This must be done after table_def is registered so expansion can work
        self._cleanup_ctes(cte_tables)

        return table_def

    def _analyze_query(
        self, query_ast: sqlglot.Expression
    ) -> List[ColumnLineage]:
        """Analyze SELECT query and extract field lineage.

        This reuses v0.1 core logic:
        1. ScopeBuilder: Build scope (extract FROM tables)
        2. SymbolResolver: Resolve column references
        3. DependencyExtractor: Extract dependencies

        Args:
            query_ast: SELECT statement AST.

        Returns:
            List[ColumnLineage]: Lineage information for each output column.
        """
        # 1. Build Scope (using v0.1's ScopeBuilder with Registry support)
        scope_builder = ScopeBuilder(
            self.config, self.schema_provider, self.registry
        )
        scope = scope_builder.build_scope(query_ast)

        # 1.5. Auto-register source tables from scope to registry
        # This ensures source tables are available for transitive resolution
        # BUT: Don't register CTEs as source tables - they should already be in registry
        for table_ref in scope.tables.values():
            table_name = table_ref.table
            # Only register if not already in registry AND not a CTE
            if not self.registry.has_table(table_name):
                # Check if this might be a CTE (should already be registered)
                # If it's not in registry, it's a real source table
                # Try to get columns from schema provider
                if self.schema_provider:
                    try:
                        columns = self.schema_provider.get_table_columns(
                            table_ref.to_qualified_name()
                        )
                        self.registry.register_source_table(
                            table_name, columns
                        )
                    except Exception:
                        # Schema doesn't have this table, register without columns
                        self.registry.register_source_table(table_name)
                else:
                    # No schema provider, register without columns
                    self.registry.register_source_table(table_name)

        # 2. Create Symbol Resolver
        resolver = SymbolResolver(scope, self.config, self.schema_provider)
        # Attach registry to resolver for SELECT * expansion (CTEs)
        resolver.registry = self.registry

        # 3. Extract dependencies (using v0.1's DependencyExtractor)
        extractor = DependencyExtractor(scope, resolver, self.config)
        dependencies = extractor.extract(query_ast)

        # 4. Convert ColumnDependency to ColumnLineage
        column_lineages = self._convert_dependencies_to_lineages(dependencies)

        return column_lineages

    def _convert_dependencies_to_lineages(
        self, dependencies: List[ColumnDependency]
    ) -> List[ColumnLineage]:
        """Convert ColumnDependency list to ColumnLineage list.

        Key points:
        - ColumnDependency is v0.1 output format (single dependency edge)
        - ColumnLineage is v1.0 format (complete lineage for one column)
        - Need to merge multiple dependencies into one lineage

        Example:
            dependencies = [
                ColumnDependency(source=orders.amount, target=total, ...),
                ColumnDependency(source=orders.tax, target=total, ...)
            ]

            Convert to:

            lineages = [
                ColumnLineage(
                    name="total",
                    sources=[orders.amount, orders.tax],
                    expression="amount + tax"
                )
            ]

        Args:
            dependencies: List of ColumnDependency objects.

        Returns:
            List[ColumnLineage]: Deduplicated and merged column lineages.
        """
        # Group by target column
        grouped: dict[str, List[ColumnDependency]] = defaultdict(list)
        for dep in dependencies:
            target_name = dep.target.column
            grouped[target_name].append(dep)

        # Build ColumnLineage for each target column
        lineages = []
        for target_name, deps in grouped.items():
            # Collect all source columns
            sources = []
            for dep in deps:
                sources.append(dep.source)

            # Extract expression (use first dependency's expression)
            # Note: All dependencies for the same target column should have
            # the same expression
            expression = deps[0].expression if deps else None
            expression_type = deps[0].expression_type if deps else None
            confidence = deps[0].confidence if deps else 1.0

            # Extract aggregate attributes (use first dependency's attributes)
            is_aggregate = deps[0].is_aggregate if deps else False
            aggregate_function = deps[0].aggregate_function if deps else None
            is_group_by = deps[0].is_group_by if deps else False

            # Create ColumnLineage
            lineage = ColumnLineage(
                name=target_name,
                sources=sources,
                expression=expression,
                expression_type=expression_type,
                confidence=confidence,
                is_aggregate=is_aggregate,
                aggregate_function=aggregate_function,
                is_group_by=is_group_by,
            )

            lineages.append(lineage)

        return lineages

    def _cleanup_ctes(self, cte_tables: Dict[str, TableDefinition]) -> None:
        """
        Clean up CTE tables (remove from Registry).

        Before removing CTEs, expand CTE column lineage into dependent tables.
        This ensures that tables created from CTEs can trace back to source tables
        even after CTEs are removed.

        CTEs are only valid within the current statement, so they should
        be removed after analysis to avoid polluting subsequent statements.

        Args:
            cte_tables: Dictionary of registered CTE tables
        """
        # Before removing CTEs, expand CTE column lineage into dependent tables
        # This ensures transitive tracing works even after CTEs are removed
        # We need to recursively expand because CTEs may reference other CTEs
        changed = True
        while changed:
            changed = False
            for table_def in self.registry.get_all_tables():
                # Skip CTE tables themselves (we'll remove them anyway)
                if table_def.name in cte_tables:
                    continue

                for col_name, col_lineage in table_def.columns.items():
                    # Check if this column references any CTE
                    expanded_sources = []
                    needs_expansion = False
                    for source in col_lineage.sources:
                        if source.table in cte_tables:
                            # This source is a CTE column, expand it
                            needs_expansion = True
                            cte_table = cte_tables[source.table]
                            if cte_table.has_column(source.column):
                                cte_col_lineage = cte_table.get_column(source.column)
                                # Add CTE column's sources (may include other CTEs)
                                expanded_sources.extend(cte_col_lineage.sources)
                        else:
                            # Not a CTE column, keep it as is
                            expanded_sources.append(source)

                    # Update column lineage with expanded sources (if changed)
                    if needs_expansion and expanded_sources != col_lineage.sources:
                        col_lineage.sources = expanded_sources
                        changed = True  # Mark that we changed something, need another pass

        # Now remove CTEs from Registry
        for cte_name in cte_tables.keys():
            # Remove from Registry
            if self.registry.has_table(cte_name):
                self.registry.remove_table(cte_name)

