"""
Expression visitor for lineage analysis.

This module defines the ExpressionVisitor class, which uses the Visitor
pattern to traverse AST expression nodes and extract column dependencies.
"""

from __future__ import annotations

from typing import Any, Optional

import sqlglot
from sqlglot import expressions

from lineage_analyzer.analyzer.symbol_resolver import SymbolResolver
from lineage_analyzer.models.column import ColumnRef


class ExpressionVisitor:
    """Expression visitor that extracts column dependencies from AST.

    This class uses the Visitor pattern to traverse AST expression nodes
    and extract column dependencies. It handles various expression types
    including columns, aliases, binary operations, functions, and CASE
    expressions.

    Attributes:
        resolver: SymbolResolver used to resolve column references.
        columns: List of ColumnRef objects collected during traversal.

    Example:
        >>> resolver = SymbolResolver(scope, config)
        >>> visitor = ExpressionVisitor(resolver)
        >>> columns = visitor.visit(column_node)
        >>> len(columns) > 0
        True
    """

    def __init__(self, resolver: SymbolResolver, debug: bool = False) -> None:
        """Initialize an ExpressionVisitor.

        Args:
            resolver: SymbolResolver used to resolve column references.
            debug: If True, print debug information during traversal.
        """
        self.resolver = resolver
        self.columns: list[ColumnRef] = []
        self.debug = debug

    def visit(self, node: sqlglot.Expression) -> list[ColumnRef]:
        """Visit a node and return all columns it depends on.

        This method dispatches to the appropriate visit method based on
        the node type. It uses dynamic method lookup to find the
        appropriate handler.

        Args:
            node: sqlglot expression node to visit.

        Returns:
            List of ColumnRef objects that the node depends on.

        Example:
            >>> visitor = ExpressionVisitor(resolver)
            >>> columns = visitor.visit(column_node)
            >>> isinstance(columns, list)
            True
        """
        if node is None:
            return []

        node_type = type(node).__name__
        method_name = f"visit_{node_type}"
        visitor = getattr(self, method_name, self.generic_visit)

        if self.debug:
            print(f"Visiting {node_type}: {node}")

        result = visitor(node)

        # Reset columns list for next visit
        self.columns = []
        return result

    def visit_Column(self, node: expressions.Column) -> list[ColumnRef]:
        """Visit a column node (leaf node).

        This is the recursive termination condition. It resolves the
        column reference using the SymbolResolver.

        Special handling: If the column contains a Star node (SELECT table.*),
        it resolves all columns from that table.

        Args:
            node: sqlglot.expressions.Column node.

        Returns:
            List containing ColumnRef object(s). For Star columns, returns
            multiple ColumnRef objects.

        Example:
            >>> visitor = ExpressionVisitor(resolver)
            >>> col_node = sqlglot.parse_one("SELECT id").expressions[0]
            >>> columns = visitor.visit_Column(col_node)
            >>> len(columns) == 1
            True
        """
        try:
            # Check if this is a Star column (SELECT table.*)
            if hasattr(node, "this") and isinstance(node.this, expressions.Star):
                # This is SELECT table.*
                table_qualifier = None
                if node.table:
                    # Extract table qualifier from Identifier or string
                    if isinstance(node.table, expressions.Identifier):
                        table_qualifier = node.table.name
                    elif isinstance(node.table, str):
                        table_qualifier = node.table
                    elif hasattr(node.table, "this"):
                        table_qualifier = node.table.this
                
                # Resolve star column for this table
                if hasattr(self.resolver, "resolve_star_column"):
                    return self.resolver.resolve_star_column(table_qualifier)
                else:
                    return []
            
            # Regular column reference
            # Use enhanced method with inference and context if available
            if hasattr(self.resolver, "resolve_column_with_inference"):
                # Get SQL context for better error messages
                context = node.sql() if hasattr(node, "sql") else None
                # Extract table qualifier
                table_qualifier = None
                if node.table:
                    if isinstance(node.table, expressions.Identifier):
                        table_qualifier = node.table.name
                    elif isinstance(node.table, str):
                        table_qualifier = node.table
                    elif hasattr(node.table, "this"):
                        table_qualifier = node.table.this
                
                column_ref, _ = self.resolver.resolve_column_with_inference(
                    node.name, table_qualifier, context
                )
            else:
                # Fallback to original method
                column_ref = self.resolver.resolve_column_from_ast_node(node)
            return [column_ref]
        except Exception as e:
            # Log warning if column cannot be resolved
            if hasattr(self.resolver, "warnings"):
                self.resolver.warnings.add(
                    "WARNING",
                    f"Could not resolve column '{node.name if hasattr(node, 'name') else 'unknown'}': {e}",
                    node.sql() if hasattr(node, "sql") else None,
                )
            if self.debug:
                print(f"Error resolving column: {e}")
            return []

    def visit_Alias(self, node: expressions.Alias) -> list[ColumnRef]:
        """Visit an alias node: col AS alias_name.

        The alias doesn't affect dependencies, so we continue visiting
        the actual expression being aliased.

        Args:
            node: sqlglot.expressions.Alias node.

        Returns:
            List of ColumnRef objects from the aliased expression.

        Example:
            >>> visitor = ExpressionVisitor(resolver)
            >>> alias_node = sqlglot.parse_one("SELECT id AS user_id").expressions[0]
            >>> columns = visitor.visit_Alias(alias_node)
            >>> len(columns) == 1
            True
        """
        if node.this:
            return self.visit(node.this)
        return []

    def visit_Add(self, node: expressions.Add) -> list[ColumnRef]:
        """Visit an addition node: a + b."""
        return self._visit_binary(node)

    def visit_Sub(self, node: expressions.Sub) -> list[ColumnRef]:
        """Visit a subtraction node: a - b."""
        return self._visit_binary(node)

    def visit_Mul(self, node: expressions.Mul) -> list[ColumnRef]:
        """Visit a multiplication node: a * b."""
        return self._visit_binary(node)

    def visit_Div(self, node: expressions.Div) -> list[ColumnRef]:
        """Visit a division node: a / b."""
        return self._visit_binary(node)

    def visit_Mod(self, node: expressions.Mod) -> list[ColumnRef]:
        """Visit a modulo node: a % b."""
        return self._visit_binary(node)

    def visit_EQ(self, node: expressions.EQ) -> list[ColumnRef]:
        """Visit an equality node: a = b."""
        return self._visit_binary(node)

    def visit_NEQ(self, node: expressions.NEQ) -> list[ColumnRef]:
        """Visit a not-equal node: a != b."""
        return self._visit_binary(node)

    def visit_GT(self, node: expressions.GT) -> list[ColumnRef]:
        """Visit a greater-than node: a > b."""
        return self._visit_binary(node)

    def visit_GTE(self, node: expressions.GTE) -> list[ColumnRef]:
        """Visit a greater-than-or-equal node: a >= b."""
        return self._visit_binary(node)

    def visit_LT(self, node: expressions.LT) -> list[ColumnRef]:
        """Visit a less-than node: a < b."""
        return self._visit_binary(node)

    def visit_LTE(self, node: expressions.LTE) -> list[ColumnRef]:
        """Visit a less-than-or-equal node: a <= b."""
        return self._visit_binary(node)

    def visit_And(self, node: expressions.And) -> list[ColumnRef]:
        """Visit an AND node: a AND b."""
        return self._visit_binary(node)

    def visit_Or(self, node: expressions.Or) -> list[ColumnRef]:
        """Visit an OR node: a OR b."""
        return self._visit_binary(node)

    def _visit_binary(self, node: expressions.Binary) -> list[ColumnRef]:
        """Visit a binary operation node: a OP b.

        This method recursively visits both left and right sides of the
        binary operation.

        Args:
            node: sqlglot binary operation node (Add, Sub, Mul, Div, etc.).

        Returns:
            List of ColumnRef objects from both sides of the operation.

        Example:
            >>> visitor = ExpressionVisitor(resolver)
            >>> add_node = sqlglot.parse_one("SELECT a + b").expressions[0]
            >>> columns = visitor._visit_binary(add_node)
            >>> len(columns) >= 2
            True
        """
        columns: list[ColumnRef] = []

        # Visit left side
        if hasattr(node, "left") and node.left:
            columns.extend(self.visit(node.left))
        elif hasattr(node, "this") and node.this:
            columns.extend(self.visit(node.this))

        # Visit right side
        if hasattr(node, "right") and node.right:
            columns.extend(self.visit(node.right))
        elif hasattr(node, "expression") and node.expression:
            columns.extend(self.visit(node.expression))

        return columns

    def visit_Literal(self, node: expressions.Literal) -> list[ColumnRef]:
        """Visit a literal node: numbers, strings, etc.

        Literals don't have dependencies, so return an empty list.

        Args:
            node: sqlglot.expressions.Literal node.

        Returns:
            Empty list (literals have no dependencies).

        Example:
            >>> visitor = ExpressionVisitor(resolver)
            >>> lit_node = sqlglot.parse_one("SELECT 123").expressions[0]
            >>> columns = visitor.visit_Literal(lit_node)
            >>> len(columns) == 0
            True
        """
        return []

    def visit_Func(self, node: expressions.Func) -> list[ColumnRef]:
        """Visit a function call node: UPPER(name), COALESCE(a, b).

        This method recursively visits all arguments of the function.

        Args:
            node: sqlglot.expressions.Func node.

        Returns:
            List of ColumnRef objects from all function arguments.

        Example:
            >>> visitor = ExpressionVisitor(resolver)
            >>> func_node = sqlglot.parse_one("SELECT UPPER(name)").expressions[0]
            >>> columns = visitor.visit_Func(func_node)
            >>> len(columns) == 1
            True
        """
        columns: list[ColumnRef] = []

        # Visit function arguments
        if hasattr(node, "expressions") and node.expressions:
            for arg in node.expressions:
                columns.extend(self.visit(arg))
        elif hasattr(node, "args"):
            # Visit args dict
            for key, value in node.args.items():
                if key == "expressions" and isinstance(value, list):
                    for arg in value:
                        columns.extend(self.visit(arg))
                elif value is not None and not isinstance(value, (str, int, float, bool)):
                    # Skip non-expression arguments
                    if isinstance(value, list):
                        for item in value:
                            if not isinstance(item, (str, int, float, bool)):
                                columns.extend(self.visit(item))
                    else:
                        columns.extend(self.visit(value))

        return columns

    def visit_Case(self, node: expressions.Case) -> list[ColumnRef]:
        """Visit a CASE expression node.

        This method extracts columns from:
        1. All WHEN conditions
        2. All THEN results
        3. ELSE clause (if present)

        Args:
            node: sqlglot.expressions.Case node.

        Returns:
            List of ColumnRef objects from all CASE branches.

        Example:
            >>> sql = "SELECT CASE WHEN a > 0 THEN b ELSE c END"
            >>> ast = sqlglot.parse_one(sql)
            >>> visitor = ExpressionVisitor(resolver)
            >>> columns = visitor.visit_Case(ast.expressions[0].this)
            >>> len(columns) >= 3
            True
        """
        columns: list[ColumnRef] = []

        # Get the actual Case node (might be wrapped in Alias)
        case_node = node.this if (hasattr(node, "this") and node.this) else node

        # Visit all WHEN ... THEN ... branches
        # Check ifs in args first
        ifs_list = None
        if hasattr(case_node, "args") and "ifs" in case_node.args:
            ifs_list = case_node.args["ifs"]
        elif hasattr(case_node, "ifs") and case_node.ifs:
            ifs_list = case_node.ifs

        if ifs_list:
            for when_clause in ifs_list:
                # Visit WHEN condition
                if hasattr(when_clause, "this") and when_clause.this:
                    columns.extend(self.visit(when_clause.this))
                # Visit THEN result
                if hasattr(when_clause, "true") and when_clause.true:
                    columns.extend(self.visit(when_clause.true))
                elif hasattr(when_clause, "args") and "true" in when_clause.args:
                    columns.extend(self.visit(when_clause.args["true"]))

        # Visit ELSE clause
        default = None
        if hasattr(case_node, "args") and "default" in case_node.args:
            default = case_node.args.get("default")
        elif hasattr(case_node, "default") and case_node.default:
            default = case_node.default

        if default:
            columns.extend(self.visit(default))

        return columns

    def visit_Cast(self, node: expressions.Cast) -> list[ColumnRef]:
        """Visit a type cast node: CAST(col AS type).

        Only the expression being cast matters for dependencies.

        Args:
            node: sqlglot.expressions.Cast node.

        Returns:
            List of ColumnRef objects from the casted expression.

        Example:
            >>> visitor = ExpressionVisitor(resolver)
            >>> cast_node = sqlglot.parse_one("SELECT CAST(id AS INT)").expressions[0]
            >>> columns = visitor.visit_Cast(cast_node)
            >>> len(columns) == 1
            True
        """
        if hasattr(node, "this") and node.this:
            return self.visit(node.this)
        return []

    def visit_Paren(self, node: expressions.Paren) -> list[ColumnRef]:
        """Visit a parentheses node: (expression).

        Parentheses don't affect dependencies, so we continue visiting
        the inner expression.

        Args:
            node: sqlglot.expressions.Paren node.

        Returns:
            List of ColumnRef objects from the inner expression.

        Example:
            >>> visitor = ExpressionVisitor(resolver)
            >>> paren_node = sqlglot.parse_one("SELECT (id)").expressions[0]
            >>> columns = visitor.visit_Paren(paren_node)
            >>> len(columns) == 1
            True
        """
        if hasattr(node, "this") and node.this:
            return self.visit(node.this)
        return []

    def visit_Identifier(self, node: expressions.Identifier) -> list[ColumnRef]:
        """Visit an identifier node.

        Identifiers that are not columns (like function names) don't
        have dependencies. Only column identifiers matter.

        Args:
            node: sqlglot.expressions.Identifier node.

        Returns:
            Empty list (identifiers are not columns).

        Example:
            >>> visitor = ExpressionVisitor(resolver)
            >>> id_node = sqlglot.parse_one("SELECT UPPER").expressions[0]
            >>> columns = visitor.visit_Identifier(id_node)
            >>> len(columns) == 0
            True
        """
        return []

    def visit_Star(self, node: expressions.Star) -> list[ColumnRef]:
        """Visit a star node: SELECT * or SELECT table.*.

        This method handles SELECT * by resolving all columns from
        the scope. It requires schema information to expand the wildcard.

        Args:
            node: sqlglot.expressions.Star node.

        Returns:
            List of ColumnRef objects representing all columns.

        Example:
            >>> visitor = ExpressionVisitor(resolver)
            >>> star_node = sqlglot.parse_one("SELECT *").expressions[0]
            >>> columns = visitor.visit_Star(star_node)
            >>> len(columns) > 0
            True
        """
        # Star node doesn't have table info directly
        # Check if it's wrapped in a Column node (SELECT table.*)
        # This is handled in visit_Column instead
        # If we get here, it's a plain SELECT *
        if hasattr(self.resolver, "resolve_star_column"):
            return self.resolver.resolve_star_column()
        return []

    def generic_visit(self, node: sqlglot.Expression) -> list[ColumnRef]:
        """Generic visit method for unknown node types.

        This method handles unknown node types by trying to recursively
        visit node.this if it exists.

        Strategy:
        1. Try to recursively visit node.this (most nodes have this attribute)
        2. If that fails, log a warning and return empty list

        Args:
            node: sqlglot expression node of unknown type.

        Returns:
            List of ColumnRef objects (may be empty if node type is unsupported).

        Example:
            >>> visitor = ExpressionVisitor(resolver)
            >>> unknown_node = sqlglot.parse_one("SELECT NOW()").expressions[0]
            >>> columns = visitor.generic_visit(unknown_node)
            >>> isinstance(columns, list)
            True
        """
        if hasattr(node, "this") and node.this:
            return self.visit(node.this)

        # Try visiting expressions if present
        if hasattr(node, "expressions") and node.expressions:
            columns: list[ColumnRef] = []
            for expr in node.expressions:
                columns.extend(self.visit(expr))
            return columns

        # Log warning for unhandled node type
        if self.debug:
            print(f"Warning: Unhandled node type: {type(node).__name__}")

        return []

