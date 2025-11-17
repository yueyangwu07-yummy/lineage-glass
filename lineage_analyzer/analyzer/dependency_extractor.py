"""
Dependency extractor for lineage analysis.

This module defines the DependencyExtractor class, which extracts
field-level dependencies from SELECT statements.
"""

from __future__ import annotations

import re
from typing import Optional

import sqlglot
from sqlglot import expressions

from lineage_analyzer.analyzer.expression_visitor import ExpressionVisitor
from lineage_analyzer.analyzer.symbol_resolver import SymbolResolver
from lineage_analyzer.exceptions import LineageError
from lineage_analyzer.models.column import ColumnRef
from lineage_analyzer.models.config import ErrorMode, LineageConfig
from lineage_analyzer.models.dependency import ColumnDependency, ExpressionType
from lineage_analyzer.models.scope import Scope
from lineage_analyzer.utils.ast_utils import get_select_expressions
from lineage_analyzer.utils.expression_utils import (
    contains_binary_op,
    contains_function,
    deduplicate_columns,
    is_aggregate_function,
    is_window_function,
)

# Supported aggregate function types
AGGREGATE_FUNCTIONS = {
    expressions.Sum,
    expressions.Avg,
    expressions.Min,
    expressions.Max,
    expressions.Count,
}


class DependencyExtractor:
    """Extracts field-level dependencies from SELECT statements.

    This class extracts field-level dependencies from SELECT statements,
    tracking which source columns contribute to which target columns.

    Attributes:
        scope: Scope object containing table and column information.
        resolver: SymbolResolver used to resolve column references.
        config: LineageConfig object containing extractor configuration.
        dependencies: List of ColumnDependency objects extracted.

    Example:
        >>> extractor = DependencyExtractor(scope, resolver, config)
        >>> dependencies = extractor.extract(ast)
        >>> len(dependencies) > 0
        True
    """

    def __init__(
        self,
        scope: Scope,
        resolver: SymbolResolver,
        config: LineageConfig,
    ) -> None:
        """Initialize a DependencyExtractor.

        Args:
            scope: Scope object containing table and column information.
            resolver: SymbolResolver used to resolve column references.
            config: LineageConfig object containing extractor configuration.
        """
        self.scope = scope
        self.resolver = resolver
        self.config = config
        self.dependencies: list[ColumnDependency] = []

    def extract(
        self, ast: sqlglot.Expression
    ) -> list[ColumnDependency]:
        """Extract all field dependencies from AST.

        This is the main entry point for extracting dependencies from
        a SELECT statement AST. It processes all SELECT expressions and
        creates ColumnDependency objects for each source-target pair.

        Main workflow:
        1. Check if AST contains UNION/UNION ALL
        2. If UNION, recursively process all branches and merge
        3. Otherwise, process as single SELECT
        4. Get SELECT list
        5. Iterate over each SELECT expression
        6. Extract expression dependencies (source columns)
        7. Determine target column name (considering aliases)
        8. Determine expression type
        9. Get original expression text (for traceability)
        10. Create ColumnDependency objects for each source-target pair

        Args:
            ast: sqlglot SELECT statement AST (may be Union or Select).

        Returns:
            List of ColumnDependency objects.

        Raises:
            NotImplementedError: If unsupported features are encountered
                (aggregate functions, window functions).

        Example:
            >>> extractor = DependencyExtractor(scope, resolver, config)
            >>> dependencies = extractor.extract(ast)
            >>> len(dependencies) > 0
            True
        """
        self.dependencies = []

        # Check if this is a UNION/UNION ALL
        if isinstance(ast, expressions.Union):
            # Handle UNION: recursively process all branches and merge
            return self._extract_from_union(ast)

        # === Complexity check ===
        from lineage_analyzer.utils.complexity import (
            ComplexityAnalyzer,
            check_complexity_limits,
        )

        complexity_analyzer = ComplexityAnalyzer()
        metrics = complexity_analyzer.analyze_select_statement(ast)

        # Check if limits are exceeded
        is_valid, error_msg = check_complexity_limits(
            metrics,
            max_nodes=self.config.max_expression_nodes,
            max_depth=self.config.max_expression_depth,
            max_case_branches=self.config.max_case_branches,
        )

        if not is_valid:
            if self.config.on_complexity_exceeded == ErrorMode.FAIL:
                from lineage_analyzer.exceptions import LineageError

                raise LineageError(f"Complexity check failed: {error_msg}")
            elif self.config.on_complexity_exceeded == ErrorMode.WARN:
                self.resolver.warnings.add(
                    "WARNING",
                    f"High complexity detected: {error_msg}",
                    context=ast.sql() if hasattr(ast, "sql") else None,
                )

        # Record complexity metrics (for debugging and monitoring)
        if self.config.on_complexity_exceeded != ErrorMode.IGNORE:
            self.resolver.warnings.add(
                "INFO",
                f"Expression complexity: {metrics.total_nodes} nodes, "
                f"{metrics.max_depth} max depth, {metrics.num_columns} columns, "
                f"{metrics.num_functions} functions, {metrics.num_case_branches} CASE branches",
                context=None,
            )

        # === Check for GROUP BY or aggregate functions ===
        # If there's a GROUP BY clause, use aggregation extraction logic
        # Also handle scalar aggregates (aggregates without GROUP BY)
        if isinstance(ast, expressions.Select):
            group_by = ast.args.get("group")
            if group_by:
                # Use aggregation extraction logic
                return self._extract_with_aggregation(ast, self.scope)
            
            # Check for scalar aggregates (aggregates without GROUP BY)
            select_expressions = get_select_expressions(ast)
            has_scalar_aggregate = False
            for expr in select_expressions:
                actual_expr = expr.this if isinstance(expr, expressions.Alias) else expr
                if self._is_aggregate_function_type(actual_expr):
                    has_scalar_aggregate = True
                    break
            
            if has_scalar_aggregate:
                # Handle scalar aggregates (treat as single-group aggregation)
                return self._extract_with_aggregation(ast, self.scope)

        # === Continue with original logic (non-aggregate queries) ===
        # Get SELECT expressions
        select_expressions = get_select_expressions(ast)

        for expr in select_expressions:
            # Check if this is a Star expression (SELECT * or SELECT table.*)
            is_star = self._is_star_expression(expr)
            
            if is_star:
                # Handle SELECT * or SELECT table.*
                # Get table qualifier if it's SELECT table.*
                table_qualifier = None
                if isinstance(expr, expressions.Column) and expr.table:
                    # Extract table qualifier from Identifier or string
                    if isinstance(expr.table, expressions.Identifier):
                        table_qualifier = expr.table.name
                    elif isinstance(expr.table, str):
                        table_qualifier = expr.table
                    elif hasattr(expr.table, "this"):
                        table_qualifier = expr.table.this
                
                # If no table qualifier (SELECT *), try to get from FROM clause
                if table_qualifier is None and isinstance(ast, expressions.Select):
                    from_clause = ast.args.get("from")
                    if from_clause and from_clause.this:
                        # Extract table name from FROM clause
                        from lineage_analyzer.utils.ast_utils import extract_table_name
                        try:
                            table_name, alias = extract_table_name(from_clause.this)
                            # Use alias if present, otherwise use table name
                            table_qualifier = alias if alias else table_name
                        except Exception:
                            # If extraction fails, table_qualifier remains None
                            pass
                
                # Resolve star column
                if hasattr(self.resolver, "resolve_star_column"):
                    star_columns = self.resolver.resolve_star_column(table_qualifier)
                    # Create a dependency for each column from the star
                    for source_col in star_columns:
                        # Target column name is the column name itself
                        target_col = ColumnRef(
                            table="__OUTPUT__",
                            column=source_col.column,
                            alias=None,
                        )
                        
                        # Get confidence for this column
                        confidence = 1.0  # Default confidence for schema-resolved columns
                        if hasattr(self.resolver, "resolve_column_with_inference"):
                            try:
                                _, confidence = self.resolver.resolve_column_with_inference(
                                    source_col.column,
                                    source_col.table,
                                    expr.sql() if hasattr(expr, "sql") else None,
                                )
                            except Exception:
                                confidence = 1.0
                        
                        dependency = ColumnDependency(
                            source=source_col,
                            target=target_col,
                            expression_type=ExpressionType.DIRECT,
                            expression=f"{source_col.table}.{source_col.column}",
                            confidence=confidence,
                        )
                        self.dependencies.append(dependency)
                # If resolver doesn't support star columns, skip
            else:
                # Check if this expression contains a subquery
                # Subqueries can appear directly or wrapped in Alias
                actual_expr = expr
                if isinstance(expr, expressions.Alias):
                    actual_expr = expr.this

                # Check if the expression is a subquery or contains one
                if isinstance(actual_expr, expressions.Subquery):
                    # Handle subquery in SELECT list
                    target_name = self._get_target_column_name(expr)
                    subquery_deps = self._handle_select_subquery(
                        subquery_node=actual_expr,
                        alias_name=target_name,
                        scope=self.scope
                    )
                    self.dependencies.extend(subquery_deps)
                elif self._contains_subquery(actual_expr):
                    # Expression contains a subquery (e.g., salary + (SELECT ...))
                    # Extract columns including those from subqueries
                    target_name = self._get_target_column_name(expr)
                    source_columns_conf = self._extract_source_columns_with_confidence(expr)
                    
                    # Also extract dependencies from nested subqueries
                    subquery_deps = self._extract_subquery_dependencies_from_expression(
                        actual_expr, self.scope
                    )
                    
                    # Merge subquery dependencies into source columns
                    for sub_dep in subquery_deps:
                        for source_col in [sub_dep.source]:
                            if source_col not in source_columns_conf:
                                source_columns_conf[source_col] = sub_dep.confidence
                    
                    # Determine expression type
                    expr_type = self._determine_expression_type(expr)
                    expression_text = self._get_expression_text(expr)
                    
                    # Create dependency for each source column
                    for source_col, confidence in source_columns_conf.items():
                        target_col = ColumnRef(
                            table="__OUTPUT__",
                            column=target_name,
                            alias=None,
                        )
                        dependency = ColumnDependency(
                            source=source_col,
                            target=target_col,
                            expression_type=expr_type,
                            expression=expression_text,
                            confidence=confidence,
                        )
                        self.dependencies.append(dependency)
                else:
                    # Regular expression handling
                    # 1. Determine target column name
                    target_name = self._get_target_column_name(expr)

                    # 2. Extract source columns with confidence
                    source_columns_conf = self._extract_source_columns_with_confidence(expr)

                    # 3. Determine expression type
                    expr_type = self._determine_expression_type(expr)

                    # 4. Get original expression text (formatted)
                    expression_text = self._get_expression_text(expr)

                    # 5. Create dependency for each source column
                    # If there are no source columns (e.g., constant), still create a dependency
                    # with a placeholder source so the column can be referenced
                    if source_columns_conf:
                        for source_col, confidence in source_columns_conf.items():
                            target_col = ColumnRef(
                                table="__OUTPUT__",  # Output columns use special table name
                                column=target_name,
                                alias=None,
                            )

                            dependency = ColumnDependency(
                                source=source_col,
                                target=target_col,
                                expression_type=expr_type,
                                expression=expression_text,
                                confidence=confidence,
                            )

                            self.dependencies.append(dependency)
                    else:
                        # No source columns (constant or computed from constants)
                        # Still create a dependency entry so the column exists
                        # Use a placeholder source that indicates this is a constant/computed value
                        target_col = ColumnRef(
                            table="__OUTPUT__",
                            column=target_name,
                            alias=None,
                        )
                        # Create a placeholder source (will be filtered out during conversion)
                        # The important thing is that the target column exists
                        placeholder_source = ColumnRef(
                            table="__CONSTANT__",
                            column=target_name,
                            alias=None,
                        )
                        dependency = ColumnDependency(
                            source=placeholder_source,
                            target=target_col,
                            expression_type=expr_type,
                            expression=expression_text,
                            confidence=1.0,
                        )
                        self.dependencies.append(dependency)

        # Process WHERE clause subqueries
        if isinstance(ast, expressions.Select):
            where_clause = ast.args.get("where")
            if where_clause:
                self._analyze_where_subqueries(where_clause, self.scope)

            # Process HAVING clause subqueries
            having_clause = ast.args.get("having")
            if having_clause:
                self._analyze_where_subqueries(having_clause, self.scope)

        return self.dependencies

    def _get_select_expressions(
        self, ast: sqlglot.Expression
    ) -> list[sqlglot.Expression]:
        """Get all expressions from SELECT clause.

        This method extracts all expressions from the SELECT clause
        of a SELECT statement AST.

        Args:
            ast: sqlglot SELECT statement AST.

        Returns:
            List of sqlglot expression nodes from SELECT clause.

        Example:
            >>> extractor = DependencyExtractor(scope, resolver, config)
            >>> exprs = extractor._get_select_expressions(ast)
            >>> len(exprs) > 0
            True
        """
        return get_select_expressions(ast)

    def _get_target_column_name(self, expr: sqlglot.Expression) -> str:
        """Determine the name of the target column.

        This method determines the name of the target column based on:
        1. If there's an AS alias, use the alias
        2. If it's a simple column reference (SELECT col), use the column name
        3. If it's a complex expression without an alias, generate a name
           (e.g., "expr_1") or use the original SQL

        Args:
            expr: SELECT expression node.

        Returns:
            Target column name.

        Example:
            >>> extractor = DependencyExtractor(scope, resolver, config)
            >>> alias_node = sqlglot.parse_one("SELECT id AS user_id").expressions[0]
            >>> name = extractor._get_target_column_name(alias_node)
            >>> name == "user_id"
            True
        """
        # Check for alias
        if isinstance(expr, expressions.Alias):
            alias = expr.alias
            if isinstance(alias, expressions.Identifier):
                return alias.name
            elif isinstance(alias, str):
                return alias
            # Fallback: get alias from args
            if hasattr(expr, "args") and "alias" in expr.args:
                alias_val = expr.args["alias"]
                if isinstance(alias_val, expressions.Identifier):
                    return alias_val.name
                elif isinstance(alias_val, str):
                    return alias_val

        # Check for simple column reference
        if isinstance(expr, expressions.Column):
            return expr.name

        # Complex expression without alias: use SQL text or generate name
        if hasattr(expr, "sql"):
            sql_text = expr.sql()
            # Normalize whitespace
            sql_text = re.sub(r"\s+", " ", sql_text).strip()
            return sql_text

        return "unnamed_expr"

    def _extract_source_columns(
        self, expr: sqlglot.Expression
    ) -> list[ColumnRef]:
        """Extract all source columns from an expression.

        This method uses ExpressionVisitor to extract all column
        dependencies from an expression. It deduplicates the results
        (same column appearing multiple times only generates one dependency).

        Args:
            expr: SELECT expression node.

        Returns:
            List of unique ColumnRef objects (deduplicated).

        Example:
            >>> extractor = DependencyExtractor(scope, resolver, config)
            >>> add_node = sqlglot.parse_one("SELECT a + b").expressions[0]
            >>> columns = extractor._extract_source_columns(add_node)
            >>> len(columns) >= 2
            True
        """
        visitor = ExpressionVisitor(self.resolver, debug=False)
        columns = visitor.visit(expr)

        # Deduplicate (same column appearing multiple times)
        return deduplicate_columns(columns)

    def _extract_source_columns_with_confidence(
        self, expr: sqlglot.Expression
    ) -> dict[ColumnRef, float]:
        """Extract all source columns from an expression with confidence scores.

        This enhanced method extracts columns and their confidence scores
        from an expression. It deduplicates columns and returns the maximum
        confidence for each unique column.

        Args:
            expr: SELECT expression node.

        Returns:
            Dictionary mapping ColumnRef to confidence score (0.0-1.0).

        Example:
            >>> extractor = DependencyExtractor(scope, resolver, config)
            >>> add_node = sqlglot.parse_one("SELECT a + b").expressions[0]
            >>> columns_conf = extractor._extract_source_columns_with_confidence(add_node)
            >>> len(columns_conf) >= 2
            True
        """
        # Use ExpressionVisitor to get columns
        visitor = ExpressionVisitor(self.resolver, debug=False)
        columns = visitor.visit(expr)

        # Deduplicate columns first
        unique_columns = deduplicate_columns(columns)

        # Build confidence map for unique columns
        confidence_map: dict[ColumnRef, float] = {}
        context = expr.sql() if hasattr(expr, "sql") else None

        # Get confidence for each unique column
        # Since columns are already resolved, we can estimate confidence
        # based on how they were resolved (explicit prefix, schema match, etc.)
        for col in unique_columns:
            # Estimate confidence based on resolution method
            # Explicit table prefix: high confidence
            # Single table: high confidence
            # Schema match: high confidence
            # Ambiguous resolution: lower confidence
            if hasattr(self.resolver, "resolve_column_with_inference"):
                try:
                    # Re-resolve to get confidence (this is safe since column is already resolved)
                    # Pass None as table_qualifier to let resolver infer
                    _, confidence = self.resolver.resolve_column_with_inference(
                        col.column, None, context
                    )
                except Exception:
                    # If inference fails, check if we have explicit table info
                    # If column has explicit table info, assume high confidence
                    confidence = 0.95 if col.table and col.table != "__OUTPUT__" else 1.0
            else:
                # No enhanced method available, use default confidence
                confidence = 1.0

            confidence_map[col] = confidence

        return confidence_map

    def _determine_expression_type(
        self, expr: sqlglot.Expression
    ) -> ExpressionType:
        """Determine the type of an expression.

        This method determines the expression type based on:
        1. Pure column reference -> DIRECT
        2. Contains arithmetic operations -> COMPUTED
        3. Contains function calls -> FUNCTION
        4. CASE expression -> CASE
        5. Aggregate function -> AGGREGATION (v0.1: raise error)
        6. Window function -> WINDOW (v0.1: raise error)

        Args:
            expr: SELECT expression node.

        Returns:
            ExpressionType enum value.

        Raises:
            NotImplementedError: If aggregate or window functions are detected.

        Example:
            >>> extractor = DependencyExtractor(scope, resolver, config)
            >>> col_node = sqlglot.parse_one("SELECT id").expressions[0]
            >>> expr_type = extractor._determine_expression_type(col_node)
            >>> expr_type == ExpressionType.DIRECT
            True
        """
        # Check if expression contains subqueries - if so, skip aggregate checking
        # (aggregates in subqueries are handled separately)
        has_subquery = self._contains_subquery(expr)
        
        if not has_subquery:
            # Only check for aggregates if there are no subqueries
            # Check for aggregate function
            if is_aggregate_function(expr):
                raise NotImplementedError(
                    "Aggregate functions are not supported in v0.1. "
                    f"Expression: {expr.sql() if hasattr(expr, 'sql') else str(expr)}"
                )

            # Check for window function
            if is_window_function(expr):
                raise NotImplementedError(
                    "Window functions are not supported in v0.1. "
                    f"Expression: {expr.sql() if hasattr(expr, 'sql') else str(expr)}"
                )
            
            # Check for aggregates in children (but not in subqueries)
            for node in expr.walk():
                # Skip subqueries - they're handled separately
                if isinstance(node, expressions.Subquery):
                    continue
                if is_aggregate_function(node):
                    raise NotImplementedError(
                        "Aggregate functions are not supported in v0.1. "
                        f"Expression: {expr.sql() if hasattr(expr, 'sql') else str(expr)}"
                    )

        # Handle alias: check the actual expression
        if isinstance(expr, expressions.Alias):
            return self._determine_expression_type(expr.this)

        # Handle column reference
        if isinstance(expr, expressions.Column):
            return ExpressionType.DIRECT

        # Handle CASE expression
        if isinstance(expr, expressions.Case):
            return ExpressionType.CASE

        # Handle function call
        if contains_function(expr):
            return ExpressionType.FUNCTION

        # Handle binary operations
        if contains_binary_op(expr):
            return ExpressionType.COMPUTED

        # Default: treat as direct
        return ExpressionType.DIRECT

    def _get_expression_text(self, expr: sqlglot.Expression) -> Optional[str]:
        """Get formatted expression text.

        This method extracts the original SQL text for an expression
        and formats it (removes extra whitespace) for traceability.

        Args:
            expr: SELECT expression node.

        Returns:
            Formatted expression text, or None if not available.

        Example:
            >>> extractor = DependencyExtractor(scope, resolver, config)
            >>> add_node = sqlglot.parse_one("SELECT a + b").expressions[0]
            >>> text = extractor._get_expression_text(add_node)
            >>> "a + b" in text or "a+b" in text
            True
        """
        if hasattr(expr, "sql"):
            sql_text = expr.sql()
            # Normalize whitespace: replace multiple spaces with single space
            sql_text = re.sub(r"\s+", " ", sql_text).strip()
            return sql_text
        return str(expr) if expr else None

    def _is_star_expression(self, expr: sqlglot.Expression) -> bool:
        """Check if an expression is a Star expression (SELECT * or SELECT table.*).

        Args:
            expr: SELECT expression node.

        Returns:
            True if the expression is a Star expression, False otherwise.

        Example:
            >>> extractor = DependencyExtractor(scope, resolver, config)
            >>> star_node = sqlglot.parse_one("SELECT *").expressions[0]
            >>> extractor._is_star_expression(star_node)
            True
        """
        # Check if it's a direct Star node
        if isinstance(expr, expressions.Star):
            return True
        
        # Check if it's a Column node containing a Star (SELECT table.*)
        if isinstance(expr, expressions.Column):
            if hasattr(expr, "this") and isinstance(expr.this, expressions.Star):
                return True
            # Also check if it's a Star wrapped in an Identifier
            if hasattr(expr, "this") and hasattr(expr.this, "this") and isinstance(expr.this.this, expressions.Star):
                return True
        
        # Check if it's an Alias wrapping a Star
        if isinstance(expr, expressions.Alias):
            if hasattr(expr, "this") and isinstance(expr.this, expressions.Star):
                return True
            if hasattr(expr, "this") and isinstance(expr.this, expressions.Column):
                if hasattr(expr.this, "this") and isinstance(expr.this.this, expressions.Star):
                    return True
        
        return False

    def _extract_from_union(
        self, union_node: expressions.Union
    ) -> list[ColumnDependency]:
        """
        Extract dependencies from a UNION/UNION ALL statement.
        
        UNION requires:
        1. All branches have the same number of columns
        2. Columns are matched by position (1st column to 1st column, etc.)
        3. Column names come from the first branch
        4. Dependencies from all branches are merged
        
        Args:
            union_node: Union node (UNION or UNION ALL)
            
        Returns:
            List of ColumnDependency objects with merged sources from all branches
        """
        # Collect all branches (left and right, recursively)
        branches = self._collect_union_branches(union_node)
        
        if len(branches) < 2:
            # Invalid UNION (should have at least 2 branches)
            raise LineageError("UNION must have at least 2 branches")
        
        # Extract dependencies from each branch
        # IMPORTANT: Each branch needs its own scope because tables may differ
        branch_dependencies = []
        for i, branch in enumerate(branches):
            if isinstance(branch, expressions.Select):
                # Build scope for this specific branch
                # Each branch may have different tables, so we need separate scopes
                from lineage_analyzer.analyzer.scope_builder import ScopeBuilder
                # Get schema_provider from resolver (SymbolResolver has schema_provider attribute)
                schema_provider = getattr(self.resolver, 'schema_provider', None)
                # Get registry from scope_builder if available, or from resolver
                registry = getattr(self.scope, 'registry', None)
                if not registry and hasattr(self.resolver, 'registry'):
                    registry = self.resolver.registry
                
                branch_scope_builder = ScopeBuilder(
                    self.config, 
                    schema_provider,
                    registry
                )
                branch_scope = branch_scope_builder.build_scope(branch)
                
                # Create resolver and extractor for this branch
                branch_resolver = SymbolResolver(branch_scope, self.config, schema_provider)
                # IMPORTANT: Attach registry to resolver for SELECT * expansion (CTEs)
                if registry:
                    branch_resolver.registry = registry
                branch_extractor = DependencyExtractor(branch_scope, branch_resolver, self.config)
            else:
                # For nested Union, use current scope (will be handled recursively)
                branch_extractor = DependencyExtractor(self.scope, self.resolver, self.config)
            
            branch_deps = branch_extractor.extract(branch)
            branch_dependencies.append(branch_deps)
        
        # Merge dependencies by column position
        # Get column count from first branch
        first_branch_deps = branch_dependencies[0]
        if not first_branch_deps:
            # Empty branch - return empty
            return []
        
        # Group dependencies by target column position
        # We need to determine the column order from the first branch
        first_branch_targets = {}
        for dep in first_branch_deps:
            target_col = dep.target.column
            if target_col not in first_branch_targets:
                first_branch_targets[target_col] = []
            first_branch_targets[target_col].append(dep)
        
        # Get ordered list of target columns (from first branch SELECT expressions)
        first_branch = branches[0]
        if isinstance(first_branch, expressions.Select):
            first_branch_exprs = get_select_expressions(first_branch)
            
            # Check if first branch has SELECT * (Star expression)
            has_star = any(self._is_star_expression(expr) for expr in first_branch_exprs)
            
            if has_star and first_branch_deps:
                # SELECT * case: use target column names from dependencies
                # The dependencies were created from the expanded columns
                ordered_targets = list(first_branch_targets.keys())
            else:
                # Regular SELECT: use target names from expressions
                ordered_targets = [self._get_target_column_name(expr) for expr in first_branch_exprs]
        else:
            # If first branch is also a Union, we need to handle it differently
            # For now, use the target column names we found
            ordered_targets = list(first_branch_targets.keys())
        
        # Merge dependencies for each position
        merged_dependencies = []
        for pos, target_name in enumerate(ordered_targets):
            # Collect all sources for this position from all branches
            all_sources = []
            expression_types = []
            expressions_text = []
            confidences = []
            
            for branch_idx, branch_deps in enumerate(branch_dependencies):
                # Get dependencies for this position from this branch
                # We need to map by position, not by name
                branch_exprs = get_select_expressions(branches[branch_idx])
                
                # Check if this branch has SELECT * (Star expression)
                has_star = any(self._is_star_expression(expr) for expr in branch_exprs)
                
                if has_star:
                    # SELECT * case: match by target column name directly
                    # The dependencies were created with target columns matching the source columns
                    # SELECT * expands to multiple columns, so we match by target name, not position
                    for dep in branch_deps:
                        if dep.target.column == target_name:
                            all_sources.append(dep.source)
                            expression_types.append(dep.expression_type)
                            expressions_text.append(dep.expression)
                            confidences.append(dep.confidence)
                elif pos < len(branch_exprs):
                    # Regular SELECT: match by target name from expression
                    branch_expr = branch_exprs[pos]
                    branch_target = self._get_target_column_name(branch_expr)
                    
                    # Find dependencies for this target in this branch
                    for dep in branch_deps:
                        if dep.target.column == branch_target:
                            all_sources.append(dep.source)
                            expression_types.append(dep.expression_type)
                            expressions_text.append(dep.expression)
                            confidences.append(dep.confidence)
            
            # Deduplicate sources
            seen_sources = set()
            unique_sources = []
            for source in all_sources:
                source_key = source.to_qualified_name()
                if source_key not in seen_sources:
                    seen_sources.add(source_key)
                    unique_sources.append(source)
            
            # Determine merged expression type (prefer more specific types)
            # Priority: CASE > FUNCTION > COMPUTED > DIRECT
            merged_expr_type = ExpressionType.DIRECT
            if ExpressionType.CASE in expression_types:
                merged_expr_type = ExpressionType.CASE
            elif ExpressionType.FUNCTION in expression_types:
                merged_expr_type = ExpressionType.FUNCTION
            elif ExpressionType.COMPUTED in expression_types:
                merged_expr_type = ExpressionType.COMPUTED
            
            # Use first expression text (or combine if needed)
            merged_expr_text = expressions_text[0] if expressions_text else None
            
            # Use minimum confidence (most conservative)
            merged_confidence = min(confidences) if confidences else 1.0
            
            # Create merged dependency for each unique source
            # All sources contribute to the same target column
            for source in unique_sources:
                target_col = ColumnRef(
                    table="__OUTPUT__",
                    column=target_name,  # Use column name from first branch
                    alias=None,
                )
                
                dependency = ColumnDependency(
                    source=source,
                    target=target_col,
                    expression_type=merged_expr_type,
                    expression=merged_expr_text,
                    confidence=merged_confidence,
                )
                merged_dependencies.append(dependency)
        
        return merged_dependencies
    
    def _collect_union_branches(
        self, union_node: expressions.Union
    ) -> list[sqlglot.Expression]:
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
        if isinstance(left, expressions.Union):
            # Nested UNION - recurse
            branches.extend(self._collect_union_branches(left))
        else:
            # Leaf branch (Select)
            branches.append(left)
        
        # Right side
        right = union_node.expression
        if isinstance(right, expressions.Union):
            # Nested UNION - recurse
            branches.extend(self._collect_union_branches(right))
        else:
            # Leaf branch (Select)
            branches.append(right)
        
        return branches

    def _analyze_where_subqueries(
        self,
        where_node: sqlglot.Expression,
        scope: Scope,
    ) -> None:
        """
        Analyze all subqueries in WHERE/HAVING clauses.

        Uses walk() to traverse the entire WHERE AST tree and find all
        Subquery nodes.

        Args:
            where_node: WHERE/HAVING clause expression node
            scope: Current scope (passed as parent_scope to subqueries)
        """
        # Lazy import to avoid circular dependency
        from lineage_analyzer.analyzer.subquery_analyzer import SubqueryAnalyzer

        for node in where_node.walk():
            if isinstance(node, expressions.Subquery):
                # Get registry from resolver if available
                registry = getattr(self.resolver, 'registry', None)
                if not registry:
                    # Try to get from scope if it has registry attribute
                    registry = getattr(scope, 'registry', None)
                
                # Create SubqueryAnalyzer
                # We need config and schema_provider from resolver
                config = self.config
                schema_provider = getattr(self.resolver, 'schema_provider', None)
                
                subquery_analyzer = SubqueryAnalyzer(registry, config, schema_provider)
                subquery_analyzer.analyze_where_subquery(
                    subquery_node=node,
                    parent_scope=scope  # Pass current scope as parent
                )

    def _handle_select_subquery(
        self,
        subquery_node: expressions.Subquery,
        alias_name: str,
        scope: Scope,
    ) -> list[ColumnDependency]:
        """
        Handle subqueries in SELECT list.

        Subquery results become columns in the outer query, so we need to
        trace their lineage.

        Args:
            subquery_node: Subquery node
            alias_name: Column alias name (target column)
            scope: Current scope (passed as parent_scope for correlated subqueries)

        Returns:
            List of ColumnDependency objects for the subquery column
        """
        # Get the SELECT statement from the subquery
        select_node = subquery_node.this
        if not isinstance(select_node, (expressions.Select, expressions.Union)):
            return []

        # Build scope for the subquery with parent_scope
        from lineage_analyzer.analyzer.scope_builder import ScopeBuilder
        
        # Get registry, config, and schema_provider
        registry = getattr(self.resolver, 'registry', None)
        if not registry:
            registry = getattr(scope, 'registry', None)
        config = self.config
        schema_provider = getattr(self.resolver, 'schema_provider', None)
        
        scope_builder = ScopeBuilder(config, schema_provider, registry)
        subquery_scope = scope_builder.build_from_clause_scope(
            select_node,
            parent_scope=scope  # Pass parent scope for correlated subqueries
        )

        # Create resolver and extractor for the subquery
        resolver = SymbolResolver(subquery_scope, config, schema_provider)
        resolver.registry = registry
        extractor = DependencyExtractor(subquery_scope, resolver, config)

        # Check if subquery SELECT contains aggregate functions
        # If so, we can't extract dependencies from SELECT, only from WHERE/HAVING
        has_aggregates = False
        if isinstance(select_node, expressions.Select):
            select_exprs = get_select_expressions(select_node)
            for expr in select_exprs:
                # Check for aggregate functions by walking the expression
                for node in expr.walk():
                    if is_aggregate_function(node):
                        has_aggregates = True
                        break
                if has_aggregates:
                    break

        # Extract dependencies from the subquery (skip if has aggregates)
        subquery_deps = []
        if not has_aggregates:
            try:
                subquery_deps = extractor.extract(select_node)
            except NotImplementedError:
                # If extraction fails (e.g., aggregates), skip SELECT processing
                pass

        # Analyze WHERE/HAVING subqueries in the subquery
        if isinstance(select_node, expressions.Select):
            where_clause = select_node.args.get("where")
            if where_clause:
                extractor._analyze_where_subqueries(where_clause, subquery_scope)
            having_clause = select_node.args.get("having")
            if having_clause:
                extractor._analyze_where_subqueries(having_clause, subquery_scope)

        # Map subquery dependencies to the outer column
        # For scalar subqueries, we typically get one column
        if not subquery_deps:
            # Subquery returns no dependencies (e.g., constant)
            return []

        # Collect all source columns from subquery dependencies
        all_sources = []
        for dep in subquery_deps:
            all_sources.append(dep.source)

        # Create dependencies mapping subquery sources to outer column
        result_deps = []
        expression_text = subquery_node.sql() if hasattr(subquery_node, "sql") else None
        
        for source_col in all_sources:
            target_col = ColumnRef(
                table="__OUTPUT__",
                column=alias_name,
                alias=None,
            )
            
            # Determine expression type based on subquery
            expr_type = ExpressionType.FUNCTION  # Subquery is like a function
            
            dependency = ColumnDependency(
                source=source_col,
                target=target_col,
                expression_type=expr_type,
                expression=expression_text,
                confidence=1.0,  # Default confidence
            )
            result_deps.append(dependency)

        return result_deps

    def _contains_subquery(self, expr: sqlglot.Expression) -> bool:
        """
        Check if an expression contains a subquery.

        Args:
            expr: Expression node to check

        Returns:
            True if expression contains a subquery, False otherwise
        """
        for node in expr.walk():
            if isinstance(node, expressions.Subquery):
                return True
        return False

    def _extract_subquery_dependencies_from_expression(
        self,
        expr: sqlglot.Expression,
        scope: Scope,
    ) -> list[ColumnDependency]:
        """
        Extract dependencies from all subqueries in an expression.

        Args:
            expr: Expression node that may contain subqueries
            scope: Current scope

        Returns:
            List of ColumnDependency objects from subqueries
        """
        all_deps = []
        
        for node in expr.walk():
            if isinstance(node, expressions.Subquery):
                # Extract dependencies from this subquery
                select_node = node.this
                if isinstance(select_node, (expressions.Select, expressions.Union)):
                    # Check for aggregates - skip SELECT processing if present
                    has_aggregates = False
                    if isinstance(select_node, expressions.Select):
                        select_exprs = get_select_expressions(select_node)
                        for sel_expr in select_exprs:
                            for walk_node in sel_expr.walk():
                                if is_aggregate_function(walk_node):
                                    has_aggregates = True
                                    break
                            if has_aggregates:
                                break
                    
                    # Build scope for subquery
                    from lineage_analyzer.analyzer.scope_builder import ScopeBuilder
                    
                    registry = getattr(self.resolver, 'registry', None)
                    if not registry:
                        registry = getattr(scope, 'registry', None)
                    config = self.config
                    schema_provider = getattr(self.resolver, 'schema_provider', None)
                    
                    scope_builder = ScopeBuilder(config, schema_provider, registry)
                    subquery_scope = scope_builder.build_from_clause_scope(
                        select_node,
                        parent_scope=scope
                    )
                    
                    resolver = SymbolResolver(subquery_scope, config, schema_provider)
                    resolver.registry = registry
                    extractor = DependencyExtractor(subquery_scope, resolver, config)
                    
                    # Only extract if no aggregates
                    if not has_aggregates:
                        try:
                            subquery_deps = extractor.extract(select_node)
                            all_deps.extend(subquery_deps)
                        except (NotImplementedError, LineageError):
                            # Skip if extraction fails
                            pass
        
        return all_deps

    def _is_aggregate_function_type(self, node: expressions.Expression) -> bool:
        """Check if a node is an aggregate function type."""
        return type(node) in AGGREGATE_FUNCTIONS

    def _get_aggregate_function_name(self, node: expressions.Expression) -> Optional[str]:
        """Get aggregate function name."""
        if isinstance(node, expressions.Sum):
            return 'SUM'
        elif isinstance(node, expressions.Avg):
            return 'AVG'
        elif isinstance(node, expressions.Min):
            return 'MIN'
        elif isinstance(node, expressions.Max):
            return 'MAX'
        elif isinstance(node, expressions.Count):
            return 'COUNT'
        return None

    def _extract_columns_from_aggregate(
        self,
        agg_node: expressions.Expression,
        scope: Scope
    ) -> list[ColumnRef]:
        """
        Extract source columns from an aggregate function.

        Example: AVG(salary) -> [employees.salary]
                 SUM(salary * 1.1) -> [employees.salary]
                 COUNT(*) -> [] (no specific source columns)
        """
        columns = []

        # Special handling for COUNT(*)
        if isinstance(agg_node, expressions.Count):
            arg = agg_node.this if hasattr(agg_node, 'this') else None
            if arg is None or isinstance(arg, expressions.Star):
                # COUNT(*) or COUNT(*): no specific source columns
                # Return empty list (table-level dependency)
                return []

        # Get the argument of the aggregate function
        # For most aggregates, the column is in the 'this' attribute
        if hasattr(agg_node, 'this') and agg_node.this:
            arg = agg_node.this
            # If it's a Column, resolve it directly
            if isinstance(arg, expressions.Column):
                column_name = arg.name
                table_qualifier = None
                if arg.table:
                    if isinstance(arg.table, expressions.Identifier):
                        table_qualifier = arg.table.name
                    elif isinstance(arg.table, str):
                        table_qualifier = arg.table
                    elif hasattr(arg.table, "name"):
                        table_qualifier = arg.table.name

                col_ref = self.resolver.resolve_column(column_name, table_qualifier)
                if col_ref:
                    columns.append(col_ref)
            else:
                # For complex expressions, extract all columns
                visitor = ExpressionVisitor(self.resolver, debug=False)
                extracted_cols = visitor.visit(arg)
                columns.extend(extracted_cols)

        return deduplicate_columns(columns)

    def _has_group_by(self, select_node: expressions.Select) -> bool:
        """Check if SELECT has GROUP BY clause."""
        return select_node.args.get("group") is not None

    def _extract_group_by_columns(
        self,
        select_node: expressions.Select,
        scope: Scope
    ) -> list[ColumnRef]:
        """
        Extract GROUP BY clause columns.

        Returns list of ColumnRef objects for group by columns.
        """
        group_by = select_node.args.get("group")
        if not group_by:
            return []

        group_columns = []

        # Get expressions from GROUP BY
        if hasattr(group_by, 'expressions'):
            group_exprs = group_by.expressions
        elif hasattr(group_by, 'this') and hasattr(group_by.this, 'expressions'):
            group_exprs = group_by.this.expressions
        else:
            return []

        for group_expr in group_exprs:
            if isinstance(group_expr, expressions.Column):
                # Extract column name and table qualifier
                column_name = group_expr.name
                table_qualifier = None
                if group_expr.table:
                    if isinstance(group_expr.table, expressions.Identifier):
                        table_qualifier = group_expr.table.name
                    elif isinstance(group_expr.table, str):
                        table_qualifier = group_expr.table
                    elif hasattr(group_expr.table, "name"):
                        table_qualifier = group_expr.table.name

                col_ref = self.resolver.resolve_column(column_name, table_qualifier)
                if col_ref:
                    group_columns.append(col_ref)
            else:
                # Expression GROUP BY: extract all columns from the expression
                visitor = ExpressionVisitor(self.resolver, debug=False)
                extracted_cols = visitor.visit(group_expr)
                group_columns.extend(extracted_cols)

        return group_columns

    def _extract_group_by_expressions(
        self,
        select_node: expressions.Select,
        select_alias_map: dict[str, str] = None
    ) -> list[str]:
        """
        Extract GROUP BY expressions as SQL strings for matching.

        Supports alias references: if GROUP BY references a SELECT alias,
        resolve it back to the actual expression.

        Args:
            select_node: SELECT statement node
            select_alias_map: Optional pre-built alias map from SELECT list

        Returns:
            List of SQL strings representing GROUP BY expressions.
        """
        group_by = select_node.args.get("group")
        if not group_by:
            return []

        group_exprs_sql = []

        # Get expressions from GROUP BY
        if hasattr(group_by, 'expressions'):
            group_exprs = group_by.expressions
        elif hasattr(group_by, 'this') and hasattr(group_by.this, 'expressions'):
            group_exprs = group_by.this.expressions
        else:
            return []

        # Build alias map if not provided
        if select_alias_map is None:
            select_alias_map = {}
            select_expressions = get_select_expressions(select_node)
            for projection in select_expressions:
                if isinstance(projection, expressions.Alias):
                    alias_name = projection.alias
                    if isinstance(alias_name, expressions.Identifier):
                        alias_name = alias_name.name
                    elif not isinstance(alias_name, str):
                        alias_name = str(alias_name)
                    expr_sql = projection.this.sql() if hasattr(projection.this, "sql") else str(projection.this)
                    select_alias_map[alias_name] = expr_sql

        for group_expr in group_exprs:
            # Check if this is an alias reference
            if isinstance(group_expr, expressions.Column) and group_expr.table is None:
                col_name = group_expr.name
                if col_name in select_alias_map:
                    # It's an alias reference, use the actual expression
                    expr_sql = select_alias_map[col_name]
                else:
                    # Not an alias, use the column as-is
                    expr_sql = group_expr.sql() if hasattr(group_expr, "sql") else str(group_expr)
            else:
                # Regular expression
                expr_sql = group_expr.sql() if hasattr(group_expr, "sql") else str(group_expr)
            group_exprs_sql.append(expr_sql)

        return group_exprs_sql

    def _extract_with_aggregation(
        self,
        select_node: expressions.Select,
        scope: Scope
    ) -> list[ColumnDependency]:
        """
        Extract dependencies from GROUP BY query.

        Logic:
        1. Extract GROUP BY columns
        2. Process SELECT list:
           - Regular columns: must be in GROUP BY
           - Aggregate functions: extract source columns and mark
        3. Return dependency list
        """
        dependencies = []

        # 1. Extract GROUP BY columns and expressions
        # First build alias map for alias reference resolution
        select_expressions = get_select_expressions(select_node)
        select_alias_map = {}  # {alias_name: expression_sql}
        for projection in select_expressions:
            if isinstance(projection, expressions.Alias):
                alias_name = projection.alias
                if isinstance(alias_name, expressions.Identifier):
                    alias_name = alias_name.name
                elif not isinstance(alias_name, str):
                    alias_name = str(alias_name)
                expr_sql = projection.this.sql() if hasattr(projection.this, "sql") else str(projection.this)
                select_alias_map[alias_name] = expr_sql

        group_by_columns = self._extract_group_by_columns(select_node, scope)
        group_by_column_names = {
            (col.table, col.column) for col in group_by_columns
        }
        group_by_expressions = self._extract_group_by_expressions(select_node, select_alias_map)
        
        # Also track which aliases are directly referenced in GROUP BY
        group_by_alias_names = set()
        group_by = select_node.args.get("group")
        if group_by:
            if hasattr(group_by, 'expressions'):
                group_exprs = group_by.expressions
            elif hasattr(group_by, 'this') and hasattr(group_by.this, 'expressions'):
                group_exprs = group_by.this.expressions
            else:
                group_exprs = []
            
            for group_expr in group_exprs:
                # Check if this is an alias reference (unqualified column)
                if isinstance(group_expr, expressions.Column):
                    # Check if it's an unqualified column (no table prefix)
                    table_qualifier = None
                    if group_expr.table:
                        if isinstance(group_expr.table, expressions.Identifier):
                            table_qualifier = group_expr.table.name
                        elif isinstance(group_expr.table, str):
                            table_qualifier = group_expr.table
                        elif hasattr(group_expr.table, "name"):
                            table_qualifier = group_expr.table.name
                    
                    # If no table qualifier, it might be an alias reference
                    if table_qualifier is None:
                        col_name = group_expr.name
                        if col_name in select_alias_map:
                            group_by_alias_names.add(col_name)

        # 2. Process SELECT list (select_expressions already extracted above)

        for projection in select_expressions:
            # Handle aliased expressions
            if isinstance(projection, expressions.Alias):
                alias_name = projection.alias
                if isinstance(alias_name, expressions.Identifier):
                    alias_name = alias_name.name
                elif not isinstance(alias_name, str):
                    alias_name = str(alias_name)

                expression = projection.this

                # Check if it's an aggregate function
                if self._is_aggregate_function_type(expression):
                    # Aggregate column
                    agg_func_name = self._get_aggregate_function_name(expression)
                    source_columns = self._extract_columns_from_aggregate(expression, scope)

                    # For COUNT(*), source_columns may be empty
                    if source_columns:
                        # Create dependency for each source column
                        for source_col in source_columns:
                            target_col = ColumnRef(
                                table="__OUTPUT__",
                                column=alias_name,
                                alias=None,
                            )

                            dependency = ColumnDependency(
                                source=source_col,
                                target=target_col,
                                expression_type=ExpressionType.AGGREGATION,
                                expression=expression.sql() if hasattr(expression, "sql") else None,
                                confidence=1.0,
                                is_aggregate=True,
                                aggregate_function=agg_func_name,
                                is_group_by=False,
                            )
                            dependencies.append(dependency)
                    else:
                        # COUNT(*) or similar: no specific source columns
                        # Create a dependency with a placeholder source column
                        # Use the first table from scope as a table-level reference
                        table_refs = list(scope.tables.values())
                        if table_refs:
                            # Use first table's first column as a placeholder
                            # This represents table-level dependency
                            placeholder_col = ColumnRef(
                                table=table_refs[0].table,
                                column="*",  # Special marker for COUNT(*)
                                alias=None,
                            )
                        else:
                            # Fallback: use a generic placeholder
                            placeholder_col = ColumnRef(
                                table="__UNKNOWN__",
                                column="*",
                                alias=None,
                            )

                        target_col = ColumnRef(
                            table="__OUTPUT__",
                            column=alias_name,
                            alias=None,
                        )

                        dependency = ColumnDependency(
                            source=placeholder_col,
                            target=target_col,
                            expression_type=ExpressionType.AGGREGATION,
                            expression=expression.sql() if hasattr(expression, "sql") else None,
                            confidence=1.0,
                            is_aggregate=True,
                            aggregate_function=agg_func_name,
                            is_group_by=False,
                        )
                        dependencies.append(dependency)

                elif isinstance(expression, expressions.Column):
                    # Regular column: must be in GROUP BY
                    column_name = expression.name
                    table_qualifier = None
                    if expression.table:
                        if isinstance(expression.table, expressions.Identifier):
                            table_qualifier = expression.table.name
                        elif isinstance(expression.table, str):
                            table_qualifier = expression.table
                        elif hasattr(expression.table, "name"):
                            table_qualifier = expression.table.name

                    col_ref = self.resolver.resolve_column(column_name, table_qualifier)
                    if col_ref:
                        # Verify if in GROUP BY
                        is_in_group_by = (col_ref.table, col_ref.column) in group_by_column_names

                        target_col = ColumnRef(
                            table="__OUTPUT__",
                            column=alias_name,
                            alias=None,
                        )

                        dependency = ColumnDependency(
                            source=col_ref,
                            target=target_col,
                            expression_type=ExpressionType.DIRECT,
                            expression=expression.sql() if hasattr(expression, "sql") else None,
                            confidence=1.0,
                            is_aggregate=False,
                            aggregate_function=None,
                            is_group_by=is_in_group_by,
                        )
                        dependencies.append(dependency)

                else:
                    # Other expressions (e.g., computed columns, function calls like YEAR(hire_date))
                    # Check if this expression matches a GROUP BY expression
                    expr_sql = expression.sql() if hasattr(expression, "sql") else str(expression)
                    # Check if expression matches GROUP BY, or if alias is directly referenced in GROUP BY
                    is_expr_in_group_by = (
                        expr_sql in group_by_expressions or
                        alias_name in group_by_alias_names
                    )

                    # Try to extract column references
                    visitor = ExpressionVisitor(self.resolver, debug=False)
                    source_columns = visitor.visit(expression)
                    source_columns = deduplicate_columns(source_columns)

                    for source_col in source_columns:
                        target_col = ColumnRef(
                            table="__OUTPUT__",
                            column=alias_name,
                            alias=None,
                        )

                        # If expression matches GROUP BY (or alias is referenced), mark as group by
                        # Otherwise check if individual column is in GROUP BY
                        is_in_group_by = is_expr_in_group_by
                        if not is_in_group_by:
                            is_in_group_by = (source_col.table, source_col.column) in group_by_column_names

                        dependency = ColumnDependency(
                            source=source_col,
                            target=target_col,
                            expression_type=ExpressionType.COMPUTED,
                            expression=expr_sql,
                            confidence=1.0,
                            is_aggregate=False,
                            aggregate_function=None,
                            is_group_by=is_in_group_by,
                        )
                        dependencies.append(dependency)

            elif isinstance(projection, expressions.Column):
                # Unaliased column
                col_name = projection.name
                table_qualifier = None
                if projection.table:
                    if isinstance(projection.table, expressions.Identifier):
                        table_qualifier = projection.table.name
                    elif isinstance(projection.table, str):
                        table_qualifier = projection.table
                    elif hasattr(projection.table, "name"):
                        table_qualifier = projection.table.name

                col_ref = self.resolver.resolve_column(col_name, table_qualifier)
                if col_ref:
                    # Verify if in GROUP BY
                    is_in_group_by = (col_ref.table, col_ref.column) in group_by_column_names

                    target_col = ColumnRef(
                        table="__OUTPUT__",
                        column=col_name,
                        alias=None,
                    )

                    dependency = ColumnDependency(
                        source=col_ref,
                        target=target_col,
                        expression_type=ExpressionType.DIRECT,
                        expression=projection.sql() if hasattr(projection, "sql") else None,
                        confidence=1.0,
                        is_aggregate=False,
                        aggregate_function=None,
                        is_group_by=is_in_group_by,
                    )
                    dependencies.append(dependency)

            elif self._is_aggregate_function_type(projection):
                # Unaliased aggregate function
                agg_func_name = self._get_aggregate_function_name(projection)
                source_columns = self._extract_columns_from_aggregate(projection, scope)

                # Generate a name for the unaliased aggregate
                target_name = f"{agg_func_name.lower()}_{source_columns[0].column if source_columns else 'col'}"

                for source_col in source_columns:
                    target_col = ColumnRef(
                        table="__OUTPUT__",
                        column=target_name,
                        alias=None,
                    )

                    dependency = ColumnDependency(
                        source=source_col,
                        target=target_col,
                        expression_type=ExpressionType.AGGREGATION,
                        expression=projection.sql() if hasattr(projection, "sql") else None,
                        confidence=1.0,
                        is_aggregate=True,
                        aggregate_function=agg_func_name,
                        is_group_by=False,
                    )
                    dependencies.append(dependency)

        # 3. Process WHERE subqueries (keep existing logic)
        where_clause = select_node.args.get("where")
        if where_clause:
            self._analyze_where_subqueries(where_clause, scope)

        # 4. Process HAVING clause
        having_clause = select_node.args.get("having")
        if having_clause:
            self._analyze_having_clause(having_clause, scope)

        return dependencies

    def _analyze_having_clause(
        self,
        having_node: expressions.Expression,
        scope: Scope
    ) -> None:
        """
        Analyze HAVING clause.

        HAVING may contain:
        1. Aggregate functions (e.g., HAVING AVG(salary) > 50000)
        2. Group by column references
        3. SELECT column alias references

        This method extracts aggregate functions from HAVING to track lineage.
        HAVING doesn't produce new columns, but we need to analyze aggregates.
        """
        # Traverse HAVING AST to find aggregate functions
        for node in having_node.walk():
            if self._is_aggregate_function_type(node):
                # Extract columns from aggregate function
                # This ensures lineage is tracked even if not in SELECT
                self._extract_columns_from_aggregate(node, scope)
                # HAVING aggregates don't produce new columns, just track lineage

