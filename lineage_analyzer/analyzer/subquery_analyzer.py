"""
Analyzer for subqueries in FROM clause (derived tables).

Phase 1: Non-correlated subqueries (derived tables with mandatory alias).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional

from sqlglot import expressions as exp

from lineage_analyzer.analyzer.dependency_extractor import DependencyExtractor
from lineage_analyzer.analyzer.symbol_resolver import SymbolResolver
from lineage_analyzer.models.column_lineage import ColumnLineage
from lineage_analyzer.models.config import LineageConfig
from lineage_analyzer.models.dependency import ColumnDependency
from lineage_analyzer.models.scope import Scope
from lineage_analyzer.models.table_definition import TableDefinition, TableType
from lineage_analyzer.registry.table_registry import TableRegistry
from lineage_analyzer.schema.provider import SchemaProvider


class SubqueryAnalyzer:
    """Analyze subqueries in FROM clause as derived tables."""

    def __init__(
        self,
        registry: TableRegistry,
        config: LineageConfig,
        schema_provider: Optional[SchemaProvider] = None,
    ) -> None:
        self.registry = registry
        self.config = config
        self.schema_provider = schema_provider

    def analyze_derived_table(
        self,
        subquery_node: exp.Subquery,
        alias: str,
    ) -> TableDefinition:
        """
        Analyze a derived table (subquery in FROM) and return a TableDefinition.

        Args:
            subquery_node: Subquery node whose 'this' must be a Select/Union.
            alias: Required alias name used to reference the derived table.

        Returns:
            TableDefinition registered under the alias with column lineages.
        """
        select_node = subquery_node.this
        if not isinstance(select_node, (exp.Select, exp.Union)):
            raise ValueError(
                f"Subquery must contain SELECT/UNION, got {type(select_node)}"
            )

        # Build scope for the subquery
        from lineage_analyzer.analyzer.scope_builder import ScopeBuilder
        scope_builder = ScopeBuilder(self.config, self.schema_provider, self.registry)
        scope = scope_builder.build_scope(select_node)

        # Create resolver and dependency extractor
        resolver = SymbolResolver(scope, self.config, self.schema_provider)
        # Attach registry for SELECT * expansion
        resolver.registry = self.registry
        extractor = DependencyExtractor(scope, resolver, self.config)

        dependencies = extractor.extract(select_node)
        columns = self._convert_dependencies_to_lineages(dependencies)

        table_def = TableDefinition(
            name=alias,
            columns={col.name: col for col in columns},
            table_type=TableType.SUBQUERY,
            is_source_table=False,
        )

        # Register immediately so that subsequent name resolution (e.g., table.*) works
        self.registry.register_table(table_def)
        return table_def

    def _convert_dependencies_to_lineages(
        self, dependencies: List[ColumnDependency]
    ) -> List[ColumnLineage]:
        """Merge ColumnDependency list into ColumnLineage list by target column."""
        grouped: Dict[str, List[ColumnDependency]] = defaultdict(list)
        for dep in dependencies:
            grouped[dep.target.column].append(dep)

        result: List[ColumnLineage] = []
        for target_name, deps in grouped.items():
            sources = [d.source for d in deps]
            expression = deps[0].expression if deps else None
            expression_type = deps[0].expression_type if deps else None
            confidence = deps[0].confidence if deps else 1.0

            # Extract aggregate attributes (use first dependency's attributes)
            is_aggregate = deps[0].is_aggregate if deps else False
            aggregate_function = deps[0].aggregate_function if deps else None
            is_group_by = deps[0].is_group_by if deps else False

            result.append(
                ColumnLineage(
                    name=target_name,
                    sources=sources,
                    expression=expression,
                    expression_type=expression_type,
                    confidence=confidence,
                    is_aggregate=is_aggregate,
                    aggregate_function=aggregate_function,
                    is_group_by=is_group_by,
                )
            )
        return result

    def analyze_where_subquery(
        self,
        subquery_node: exp.Subquery,
        parent_scope: Scope,
    ) -> None:
        """
        Analyze subqueries in WHERE/HAVING clauses.

        Key: WHERE subqueries are NOT registered as tables, only analyze
        their internal lineage.

        Args:
            subquery_node: Subquery node
            parent_scope: Parent scope (for correlated subquery resolution
                of outer columns)
        """
        # 1. Extract the SELECT statement from the subquery
        select_node = subquery_node.this
        if not isinstance(select_node, (exp.Select, exp.Union)):
            return  # Not a SELECT/UNION, skip

        # 2. Build scope for the subquery, passing parent_scope (key!)
        from lineage_analyzer.analyzer.scope_builder import ScopeBuilder
        scope_builder = ScopeBuilder(self.config, self.schema_provider, self.registry)
        subquery_scope = scope_builder.build_from_clause_scope(
            select_node,
            parent_scope=parent_scope  # Pass parent scope
        )

        # 3. WHERE subqueries are NOT registered as tables, but we need to analyze
        #    their internal structure for lineage. We don't extract dependencies
        #    from SELECT clause because it may contain aggregate functions.
        #    We only recursively process nested WHERE/HAVING subqueries.

        # 4. Recursively process nested WHERE subqueries within this subquery
        if isinstance(select_node, exp.Select):
            where_clause = select_node.args.get("where")
            if where_clause:
                self._analyze_nested_where_subqueries(where_clause, subquery_scope)

            having_clause = select_node.args.get("having")
            if having_clause:
                self._analyze_nested_where_subqueries(having_clause, subquery_scope)
        elif isinstance(select_node, exp.Union):
            # For UNION, process WHERE/HAVING in each branch
            branches = self._collect_union_branches(select_node)
            for branch in branches:
                if isinstance(branch, exp.Select):
                    where_clause = branch.args.get("where")
                    if where_clause:
                        self._analyze_nested_where_subqueries(where_clause, subquery_scope)
                    having_clause = branch.args.get("having")
                    if having_clause:
                        self._analyze_nested_where_subqueries(having_clause, subquery_scope)

    def _analyze_nested_where_subqueries(
        self,
        where_node: exp.Expression,
        current_scope: Scope,
    ) -> None:
        """Recursively analyze nested subqueries in WHERE/HAVING clauses."""
        for node in where_node.walk():
            if isinstance(node, exp.Subquery):
                self.analyze_where_subquery(node, current_scope)

    def _collect_union_branches(
        self, union_node: exp.Union
    ) -> list[exp.Expression]:
        """
        Collect all branches from a UNION structure (handles nested UNIONs).

        Args:
            union_node: Union node (may contain nested Unions)

        Returns:
            List of all branch expressions (Select or Union nodes)
        """
        branches = []
        
        # Left side
        left = union_node.this
        if isinstance(left, exp.Union):
            # Nested UNION - recurse
            branches.extend(self._collect_union_branches(left))
        else:
            # Leaf branch (Select)
            branches.append(left)
        
        # Right side
        right = union_node.expression
        if isinstance(right, exp.Union):
            # Nested UNION - recurse
            branches.extend(self._collect_union_branches(right))
        else:
            # Leaf branch (Select)
            branches.append(right)
        
        return branches


