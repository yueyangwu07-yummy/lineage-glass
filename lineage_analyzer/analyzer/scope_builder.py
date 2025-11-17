"""
Scope builder implementation.

This module defines the ScopeBuilder class, which builds Scope objects
from sqlglot AST by extracting table references and column information.
"""

from __future__ import annotations

from typing import Optional

import sqlglot
from sqlglot import expressions

from lineage_analyzer.exceptions import (
    AmbiguousColumnError,
    LineageError,
    UnresolvedReferenceError,
)
from lineage_analyzer.models.column import ColumnRef
from lineage_analyzer.models.config import ErrorMode, LineageConfig
from lineage_analyzer.models.scope import Scope
from lineage_analyzer.models.table import TableRef
from lineage_analyzer.registry.table_registry import TableRegistry
from lineage_analyzer.schema.provider import SchemaProvider
from lineage_analyzer.utils.ast_utils import (
    extract_table_name,
    get_from_clause,
    split_qualified_name,
)


class ScopeBuilder:
    """Builds Scope objects from SQL AST.

    This class extracts table references and column information from a
    sqlglot AST and builds a Scope object that tracks available tables
    and columns for lineage analysis.

    Attributes:
        config: LineageConfig object containing builder configuration.
        schema: Optional SchemaProvider for schema validation and column
            information. If provided, columns will be pre-registered in
            the scope.

    Example:
        >>> config = LineageConfig()
        >>> builder = ScopeBuilder(config)
        >>> sql = "SELECT id FROM users"
        >>> ast = sqlglot.parse_one(sql)
        >>> scope = builder.build_scope(ast)
        >>> len(scope.tables) > 0
        True
    """

    def __init__(
        self,
        config: LineageConfig,
        schema_provider: Optional[SchemaProvider] = None,
        registry: Optional[TableRegistry] = None,
    ) -> None:
        """Initialize a ScopeBuilder with configuration.

        Args:
            config: LineageConfig object containing builder configuration.
            schema_provider: Optional SchemaProvider for schema validation.
            registry: Optional TableRegistry to query table definitions.
        """
        self.config = config
        self.schema = schema_provider
        self.registry = registry

    def build_scope(self, ast: sqlglot.Expression) -> Scope:
        """Build a Scope object from an AST.

        This method extracts table references from the FROM clause and
        builds a Scope object that tracks available tables and columns.
        It handles table aliases, JOINs, and schema information.

        Steps:
        1. Extract FROM clause from AST
        2. Extract base table from FROM clause
        3. Extract all JOINs from SELECT statement
        4. Create TableRef objects for each table
        5. Register tables in Scope (handling aliases)
        6. If schema_provider is available, pre-register columns

        Args:
            ast: sqlglot AST expression (must be a SELECT statement).

        Returns:
            Scope object containing table and column information.

        Raises:
            LineageError: If the AST is invalid or table extraction fails.
            ValueError: If the AST is not a SELECT statement.

        Example:
            >>> config = LineageConfig()
            >>> builder = ScopeBuilder(config)
            >>> sql = "SELECT id FROM users u"
            >>> ast = sqlglot.parse_one(sql)
            >>> scope = builder.build_scope(ast)
            >>> "u" in scope.tables
            True
            >>> "users" in scope.tables
            True
        """
        scope = Scope()

        # Extract FROM clause
        from_clause = get_from_clause(ast)
        if from_clause is None:
            # No FROM clause (e.g., SELECT 1)
            return scope

        # Extract base table from FROM clause
        table_refs: list[TableRef] = []
        
        # Extract base table
        if from_clause.this:
            table_ref = self._create_table_ref(from_clause.this)
            table_refs.append(table_ref)

        # Extract JOINs from SELECT statement
        joins = ast.args.get("joins", [])
        for join_node in joins:
            if isinstance(join_node, expressions.Join):
                # Extract table from JOIN
                if join_node.this:
                    join_table_ref = self._create_table_ref(join_node.this)
                    table_refs.append(join_table_ref)

        # Register tables in scope
        seen_aliases: set[str] = set()
        for table_ref in table_refs:
            # Check for alias conflicts
            if table_ref.alias:
                if table_ref.alias in seen_aliases:
                    error_msg = (
                        f"Duplicate table alias '{table_ref.alias}' found. "
                        f"Table: {table_ref.to_qualified_name()}"
                    )
                    if self.config.on_ambiguity == ErrorMode.FAIL:
                        raise AmbiguousColumnError(error_msg, table_ref.alias)
                    elif self.config.on_ambiguity == ErrorMode.WARN:
                        # Warn but continue (in real implementation, log warning)
                        pass
                    # IGNORE mode: continue without error

                seen_aliases.add(table_ref.alias)

            # Register table in scope
            scope.register_table(table_ref)

            # Pre-register columns from Registry or Schema Provider
            self._preregister_columns(scope, table_ref)

        return scope

    def build_from_clause_scope(
        self,
        ast: sqlglot.Expression,
        parent_scope: Optional[Scope] = None,
    ) -> Scope:
        """Build a Scope object from an AST with optional parent scope.

        This method is similar to build_scope but allows specifying a parent
        scope for nested queries (e.g., correlated subqueries).

        Args:
            ast: sqlglot AST expression (must be a SELECT statement).
            parent_scope: Optional parent scope for nested query contexts.

        Returns:
            Scope object containing table and column information, with
            parent_scope set if provided.

        Example:
            >>> config = LineageConfig()
            >>> builder = ScopeBuilder(config)
            >>> sql = "SELECT id FROM users u"
            >>> ast = sqlglot.parse_one(sql)
            >>> parent = Scope()
            >>> scope = builder.build_from_clause_scope(ast, parent_scope=parent)
            >>> scope.parent == parent
            True
        """
        scope = Scope(parent=parent_scope)

        # Extract FROM clause
        from_clause = get_from_clause(ast)
        if from_clause is None:
            # No FROM clause (e.g., SELECT 1)
            return scope

        # Extract base table from FROM clause
        table_refs: list[TableRef] = []
        
        # Extract base table
        if from_clause.this:
            table_ref = self._create_table_ref(from_clause.this)
            table_refs.append(table_ref)

        # Extract JOINs from SELECT statement
        joins = ast.args.get("joins", [])
        for join_node in joins:
            if isinstance(join_node, expressions.Join):
                # Extract table from JOIN
                if join_node.this:
                    join_table_ref = self._create_table_ref(join_node.this)
                    table_refs.append(join_table_ref)

        # Register tables in scope
        seen_aliases: set[str] = set()
        for table_ref in table_refs:
            # Check for alias conflicts
            if table_ref.alias:
                if table_ref.alias in seen_aliases:
                    error_msg = (
                        f"Duplicate table alias '{table_ref.alias}' found. "
                        f"Table: {table_ref.to_qualified_name()}"
                    )
                    if self.config.on_ambiguity == ErrorMode.FAIL:
                        raise AmbiguousColumnError(error_msg, table_ref.alias)
                    elif self.config.on_ambiguity == ErrorMode.WARN:
                        # Warn but continue (in real implementation, log warning)
                        pass
                    # IGNORE mode: continue without error

                seen_aliases.add(table_ref.alias)

            # Register table in scope
            scope.register_table(table_ref)

            # Pre-register columns from Registry or Schema Provider
            self._preregister_columns(scope, table_ref)

        return scope

    def _create_table_ref(self, table_node: sqlglot.Expression) -> TableRef:
        """Create a TableRef object from a table node.

        This method creates a TableRef object from a sqlglot table node,
        handling qualified names, aliases, and schema information.

        Args:
            table_node: sqlglot table node (Table, Alias, etc.).

        Returns:
            TableRef object representing the table.

        Raises:
            LineageError: If the table node cannot be parsed.
            NotImplementedError: If subqueries are encountered.

        Example:
            >>> sql = "SELECT * FROM public.orders o"
            >>> ast = sqlglot.parse_one(sql)
            >>> from_clause = get_from_clause(ast)
            >>> builder = ScopeBuilder(LineageConfig())
            >>> table_ref = builder._create_table_ref(from_clause.expressions[0])
            >>> table_ref.table == "orders"
            True
            >>> table_ref.schema == "public"
            True
        """
        # Handle subqueries and aliased subqueries first
        if isinstance(table_node, expressions.Subquery):
            # Local import to avoid circular dependency at module load time
            from lineage_analyzer.analyzer.subquery_analyzer import SubqueryAnalyzer
            alias_name = None
            if table_node.alias:
                if isinstance(table_node.alias, expressions.TableAlias):
                    alias_name = table_node.alias.this.name
                elif isinstance(table_node.alias, expressions.Identifier):
                    alias_name = table_node.alias.name
                elif isinstance(table_node.alias, str):
                    alias_name = table_node.alias
            if not alias_name:
                raise LineageError("Derived table (subquery) must have an alias")

            # Analyze the subquery as a derived table and register it
            sub_analyzer = SubqueryAnalyzer(self.registry, self.config, self.schema)
            sub_analyzer.analyze_derived_table(table_node, alias_name)

            # Return a TableRef pointing to the derived table by its alias
            return TableRef(
                table=alias_name,
                alias=alias_name,
                is_subquery=True,
            )

        if isinstance(table_node, expressions.Alias) and isinstance(
            table_node.this, expressions.Subquery
        ):
            from lineage_analyzer.analyzer.subquery_analyzer import SubqueryAnalyzer
            # Extract alias
            alias_expr = table_node.alias
            alias_name = None
            if isinstance(alias_expr, expressions.Identifier):
                alias_name = alias_expr.name
            elif isinstance(alias_expr, str):
                alias_name = alias_expr
            elif isinstance(alias_expr, expressions.TableAlias):
                alias_name = alias_expr.this.name
            if not alias_name:
                raise LineageError("Derived table (subquery) must have an alias")

            # Analyze the subquery and register
            sub_analyzer = SubqueryAnalyzer(self.registry, self.config, self.schema)
            sub_analyzer.analyze_derived_table(table_node.this, alias_name)

            return TableRef(
                table=alias_name,
                alias=alias_name,
                is_subquery=True,
            )

        try:
            table_name, alias = extract_table_name(table_node)
        except NotImplementedError as e:
            # Re-raise NotImplementedError for subqueries
            raise NotImplementedError(
                f"Subqueries in FROM clause are not supported in v0.1. "
                f"Error: {str(e)}"
            ) from e
        except ValueError as e:
            raise LineageError(
                f"Failed to extract table name from node: {str(e)}. "
                f"Node type: {type(table_node).__name__}"
            ) from e

        # Split qualified name into database, schema, table
        database, schema, table = split_qualified_name(table_name)

        # Create TableRef
        return TableRef(
            table=table,
            database=database,
            schema=schema,
            alias=alias,
            is_subquery=False,
        )

    def _preregister_columns(self, scope: Scope, table_ref: TableRef) -> None:
        """Pre-register table columns in scope.

        Priority:
        1. Registry (if table is defined in script)
        2. Schema Provider (if user provided schema)
        3. Skip (cannot know columns, infer at runtime)

        Args:
            scope: Scope object to register columns in.
            table_ref: TableRef object representing the table.
        """
        table_name = table_ref.table

        # 1. Try to get from Registry
        if self.registry:
            table_def = self.registry.get_table(table_name)
            if table_def:
                # Register all columns from this table
                for col_name in table_def.columns.keys():
                    column_ref = ColumnRef(
                        table=table_ref.table,
                        column=col_name,
                        database=table_ref.database,
                        schema=table_ref.schema,
                    )
                    scope.register_column(column_ref)
                return

        # 2. Try to get from Schema Provider
        if self.schema:
            # Get qualified table name
            qualified_table_name = table_ref.to_qualified_name()

            # Get columns from schema provider
            try:
                columns = self.schema.get_table_columns(qualified_table_name)
                for column_name in columns:
                    column_ref = ColumnRef(
                        table=table_ref.table,
                        column=column_name,
                        database=table_ref.database,
                        schema=table_ref.schema,
                    )
                    scope.register_column(column_ref)
                return
            except Exception:
                pass  # Schema doesn't have this table

        # 3. Cannot get column information, skip
        # Will be resolved on-demand in Symbol Resolver

    def _extract_join_conditions(
        self, ast: sqlglot.Expression
    ) -> list[tuple[ColumnRef, ColumnRef]]:
        """Extract JOIN ON conditions as column pairs.

        This method extracts JOIN ON conditions from the AST and returns
        them as pairs of ColumnRef objects. This is an optional feature
        for Phase 4 and currently returns an empty list.

        Args:
            ast: sqlglot AST expression.

        Returns:
            List of tuples containing (source_column, target_column) pairs.
            Currently returns an empty list (to be implemented in Phase 4).

        Example:
            >>> sql = "SELECT * FROM orders o JOIN customers c ON o.id = c.id"
            >>> ast = sqlglot.parse_one(sql)
            >>> builder = ScopeBuilder(LineageConfig())
            >>> conditions = builder._extract_join_conditions(ast)
            >>> isinstance(conditions, list)
            True
        """
        # TODO: Implement in Phase 4
        # This method should extract JOIN ON conditions and return them
        # as pairs of ColumnRef objects
        return []

