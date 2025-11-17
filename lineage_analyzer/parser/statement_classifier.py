"""
Statement classifier for SQL statements.

This module defines the StatementClassifier class, which identifies and classifies
different types of SQL statements, extracting key information such as table names
and query parts.
"""

from typing import Optional

import sqlglot
from sqlglot import expressions

from lineage_analyzer.exceptions import LineageError
from lineage_analyzer.models.classified_statement import ClassifiedStatement
from lineage_analyzer.models.statement_type import StatementType


class StatementClassifier:
    """SQL statement classifier.

    Responsibilities:
    1. Identify SQL statement types
    2. Extract key information (table names, query parts, etc.)
    3. Wrap as ClassifiedStatement objects

    Usage:
        classifier = StatementClassifier()
        classified = classifier.classify(ast, raw_sql)

        if classified.is_supported():
            # Perform lineage analysis
            ...
    """

    def classify(
        self,
        ast: sqlglot.Expression,
        raw_sql: str,
        statement_index: int = 0,
    ) -> ClassifiedStatement:
        """Classify a SQL statement.

        Args:
            ast: sqlglot AST object.
            raw_sql: Original SQL text.
            statement_index: Position of statement in script.

        Returns:
            ClassifiedStatement object.

        Raises:
            LineageError: If statement type cannot be identified.
        """
        # Get AST node type
        ast_type = type(ast).__name__

        # === SELECT statement ===
        if ast_type == "Select":
            # Check if it contains CTE (WITH clause)
            if self._has_cte(ast):
                return ClassifiedStatement(
                    statement_type=StatementType.WITH_CTE,
                    ast=ast,
                    raw_sql=raw_sql,
                    query_ast=ast,  # Entire statement is a query
                    statement_index=statement_index,
                )
            else:
                return ClassifiedStatement(
                    statement_type=StatementType.SELECT,
                    ast=ast,
                    raw_sql=raw_sql,
                    query_ast=ast,
                    statement_index=statement_index,
                )

        # === CREATE TABLE AS ===
        elif ast_type == "Create":
            # Check if it's CREATE TABLE AS SELECT
            if self._is_create_table_as(ast):
                table_name = self._extract_table_name(ast)
                query_ast = self._extract_query_from_create(ast)
                is_temp = self._is_temporary(ast)

                return ClassifiedStatement(
                    statement_type=(
                        StatementType.CREATE_TEMP_TABLE
                        if is_temp
                        else StatementType.CREATE_TABLE_AS
                    ),
                    ast=ast,
                    raw_sql=raw_sql,
                    target_table=table_name,
                    query_ast=query_ast,
                    is_temporary=is_temp,
                    statement_index=statement_index,
                )

            # Check if it's CREATE VIEW
            elif self._is_create_view(ast):
                view_name = self._extract_table_name(ast)
                query_ast = self._extract_query_from_create(ast)

                return ClassifiedStatement(
                    statement_type=StatementType.CREATE_VIEW,
                    ast=ast,
                    raw_sql=raw_sql,
                    target_table=view_name,
                    query_ast=query_ast,
                    statement_index=statement_index,
                )

            # Pure CREATE TABLE (no AS SELECT)
            else:
                table_name = self._extract_table_name(ast)
                return ClassifiedStatement(
                    statement_type=StatementType.CREATE_TABLE,
                    ast=ast,
                    raw_sql=raw_sql,
                    target_table=table_name,
                    statement_index=statement_index,
                )

        # === INSERT INTO ... SELECT ===
        elif ast_type == "Insert":
            # Check if it contains SELECT (not VALUES)
            if self._has_select_clause(ast):
                table_name = self._extract_insert_table_name(ast)
                query_ast = self._extract_query_from_insert(ast)

                return ClassifiedStatement(
                    statement_type=StatementType.INSERT_INTO_SELECT,
                    ast=ast,
                    raw_sql=raw_sql,
                    target_table=table_name,
                    query_ast=query_ast,
                    statement_index=statement_index,
                )
            else:
                # INSERT INTO ... VALUES (not supported)
                return ClassifiedStatement(
                    statement_type=StatementType.UNSUPPORTED,
                    ast=ast,
                    raw_sql=raw_sql,
                    statement_index=statement_index,
                    metadata={"reason": "INSERT INTO ... VALUES is not supported"},
                )

        # === DROP TABLE ===
        elif ast_type == "Drop":
            table_name = self._extract_drop_table_name(ast)
            return ClassifiedStatement(
                statement_type=StatementType.DROP_TABLE,
                ast=ast,
                raw_sql=raw_sql,
                target_table=table_name,
                statement_index=statement_index,
            )

        # === UPDATE ===
        elif ast_type == "Update":
            return ClassifiedStatement(
                statement_type=StatementType.UPDATE,
                ast=ast,
                raw_sql=raw_sql,
                statement_index=statement_index,
                metadata={"reason": "UPDATE statements not supported in v1.0"},
            )

        # === DELETE ===
        elif ast_type == "Delete":
            return ClassifiedStatement(
                statement_type=StatementType.DELETE,
                ast=ast,
                raw_sql=raw_sql,
                statement_index=statement_index,
                metadata={"reason": "DELETE statements not supported in v1.0"},
            )

        # === UNKNOWN ===
        else:
            return ClassifiedStatement(
                statement_type=StatementType.UNKNOWN,
                ast=ast,
                raw_sql=raw_sql,
                statement_index=statement_index,
                metadata={"ast_type": ast_type},
            )

    # ========== Helper methods ==========

    def _has_cte(self, ast: sqlglot.Expression) -> bool:
        """Check if SELECT contains WITH clause (CTE).

        Args:
            ast: SELECT AST node.

        Returns:
            True if SELECT contains CTE, False otherwise.
        """
        # In sqlglot, CTE is in ast.args.get('with')
        return ast.args.get("with") is not None

    def _is_create_table_as(self, ast: sqlglot.Expression) -> bool:
        """Check if it's CREATE TABLE AS SELECT.

        Args:
            ast: CREATE AST node.

        Returns:
            True if it's CREATE TABLE AS SELECT, False otherwise.
        """
        # Check if there's an 'expression' parameter (i.e., AS SELECT part)
        # Also check that it's not a VIEW
        kind = ast.args.get("kind")
        if kind and kind.upper() == "VIEW":
            return False
        return ast.args.get("expression") is not None

    def _is_create_view(self, ast: sqlglot.Expression) -> bool:
        """Check if it's CREATE VIEW.

        Args:
            ast: CREATE AST node.

        Returns:
            True if it's CREATE VIEW, False otherwise.
        """
        # In sqlglot, kind parameter identifies the creation type
        kind = ast.args.get("kind")
        return kind and kind.upper() == "VIEW"

    def _is_temporary(self, ast: sqlglot.Expression) -> bool:
        """Check if it's a temporary table.

        Args:
            ast: CREATE AST node.

        Returns:
            True if it's a temporary table, False otherwise.
        """
        # In sqlglot, temporary tables are identified by TemporaryProperty in properties
        properties = ast.args.get("properties")
        if properties and hasattr(properties, "expressions"):
            for prop in properties.expressions:
                if isinstance(prop, expressions.TemporaryProperty):
                    return True
        return False

    def _has_select_clause(self, insert_ast: sqlglot.Expression) -> bool:
        """Check if INSERT contains SELECT (not VALUES).

        Args:
            insert_ast: INSERT AST node.

        Returns:
            True if INSERT contains SELECT, False otherwise.
        """
        expression = insert_ast.args.get("expression")
        return expression and isinstance(expression, expressions.Select)

    def _extract_table_name(self, create_ast: sqlglot.Expression) -> str:
        """Extract table name from CREATE statement.

        Args:
            create_ast: CREATE AST node.

        Returns:
            Table name as string.
        """
        # In sqlglot, table name is in 'this' parameter
        table_expr = create_ast.this
        if isinstance(table_expr, expressions.Table):
            # Handle schema.table format
            parts = []
            if table_expr.catalog:
                parts.append(table_expr.catalog)
            if table_expr.db:
                parts.append(table_expr.db)
            if table_expr.name:
                parts.append(table_expr.name)
            return ".".join(parts) if parts else str(table_expr)
        elif isinstance(table_expr, expressions.Schema):
            # For CREATE TABLE without AS, this is a Schema
            # Extract table name from the schema
            table = table_expr.this
            if isinstance(table, expressions.Table):
                parts = []
                if table.catalog:
                    parts.append(table.catalog)
                if table.db:
                    parts.append(table.db)
                if table.name:
                    parts.append(table.name)
                return ".".join(parts) if parts else str(table)
            return str(table) if table else str(table_expr)
        return str(table_expr)

    def _extract_insert_table_name(self, insert_ast: sqlglot.Expression) -> str:
        """Extract table name from INSERT statement.

        Args:
            insert_ast: INSERT AST node.

        Returns:
            Table name as string.
        """
        table_expr = insert_ast.this
        
        # If it's a Schema (with explicit columns), extract table from this.this
        if isinstance(table_expr, expressions.Schema):
            table_expr = table_expr.this
        
        if isinstance(table_expr, expressions.Table):
            # Handle schema.table format
            parts = []
            if table_expr.catalog:
                parts.append(table_expr.catalog)
            if table_expr.db:
                parts.append(table_expr.db)
            if table_expr.name:
                parts.append(table_expr.name)
            return ".".join(parts) if parts else str(table_expr)
        return str(table_expr)

    def _extract_drop_table_name(self, drop_ast: sqlglot.Expression) -> Optional[str]:
        """Extract table name from DROP statement.

        Args:
            drop_ast: DROP AST node.

        Returns:
            Table name as string, or None if not found.
        """
        # In sqlglot, DROP table name is in 'this' parameter
        table_expr = drop_ast.this
        if isinstance(table_expr, expressions.Table):
            parts = []
            if table_expr.catalog:
                parts.append(table_expr.catalog)
            if table_expr.db:
                parts.append(table_expr.db)
            if table_expr.name:
                parts.append(table_expr.name)
            return ".".join(parts) if parts else str(table_expr)
        return str(table_expr) if table_expr else None

    def _extract_query_from_create(
        self, create_ast: sqlglot.Expression
    ) -> Optional[sqlglot.Expression]:
        """Extract SELECT part from CREATE TABLE AS / CREATE VIEW.

        Args:
            create_ast: CREATE AST node.

        Returns:
            SELECT AST expression, or None if not found.
        """
        # AS SELECT part is in 'expression' parameter
        return create_ast.args.get("expression")

    def _extract_query_from_insert(
        self, insert_ast: sqlglot.Expression
    ) -> Optional[sqlglot.Expression]:
        """Extract SELECT part from INSERT INTO SELECT.

        Args:
            insert_ast: INSERT AST node.

        Returns:
            SELECT AST expression, or None if not found.
        """
        return insert_ast.args.get("expression")

