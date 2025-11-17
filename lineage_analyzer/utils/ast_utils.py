"""
AST utility functions for SQL parsing.

This module provides utility functions for working with sqlglot AST objects,
including functions to extract clauses, check statement types, and parse
table references.
"""

from typing import Optional, Tuple

import sqlglot
from sqlglot import expressions


def is_select_statement(ast: sqlglot.Expression) -> bool:
    """Check if the AST represents a SELECT statement.

    This function checks whether the given AST node is a SELECT statement
    by examining its expression type.

    Args:
        ast: sqlglot AST expression to check.

    Returns:
        True if the AST is a SELECT statement, False otherwise.

    Example:
        >>> sql = "SELECT id FROM users"
        >>> ast = sqlglot.parse_one(sql)
        >>> is_select_statement(ast)
        True
        >>> sql = "INSERT INTO users VALUES (1)"
        >>> ast = sqlglot.parse_one(sql)
        >>> is_select_statement(ast)
        False
    """
    return isinstance(ast, expressions.Select)


def get_from_clause(ast: sqlglot.Expression) -> Optional[sqlglot.Expression]:
    """Extract the FROM clause from a SELECT statement.

    This function extracts the FROM clause from a SELECT statement AST.
    The FROM clause contains the base table reference.

    Args:
        ast: sqlglot SELECT statement AST.

    Returns:
        The FROM clause expression if found, None otherwise.

    Raises:
        ValueError: If the AST is not a SELECT statement.

    Example:
        >>> sql = "SELECT id FROM users"
        >>> ast = sqlglot.parse_one(sql)
        >>> from_clause = get_from_clause(ast)
        >>> from_clause is not None
        True
    """
    if not is_select_statement(ast):
        raise ValueError("AST must be a SELECT statement")

    select_expr = ast
    # Access 'from' from args dict
    from_clause = select_expr.args.get("from")
    return from_clause


def get_select_expressions(ast: sqlglot.Expression) -> list[sqlglot.Expression]:
    """Extract SELECT expressions from a SELECT statement.

    This function extracts all expressions in the SELECT clause, including
    column references, functions, and computed expressions.

    Args:
        ast: sqlglot SELECT statement AST.

    Returns:
        List of expressions in the SELECT clause.

    Raises:
        ValueError: If the AST is not a SELECT statement.

    Example:
        >>> sql = "SELECT id, name, COUNT(*) FROM users"
        >>> ast = sqlglot.parse_one(sql)
        >>> exprs = get_select_expressions(ast)
        >>> len(exprs) == 3
        True
    """
    if not is_select_statement(ast):
        raise ValueError("AST must be a SELECT statement")

    select_expr = ast
    # Access expressions from args dict
    expressions_list = select_expr.args.get("expressions", [])
    return list(expressions_list) if expressions_list else []


def extract_table_name(table_node: sqlglot.Expression) -> Tuple[str, Optional[str]]:
    """Extract table name and alias from a table node.

    This function extracts the real table name and alias from a table
    reference node in the AST. It handles various table reference formats,
    including qualified names (schema.table), aliases, and subqueries.

    Args:
        table_node: sqlglot table reference node (Table, Alias, TableAlias, etc.).

    Returns:
        Tuple of (real_table_name, alias), where alias may be None.

    Raises:
        ValueError: If the table node cannot be parsed.
        NotImplementedError: If subqueries are encountered.

    Example:
        >>> sql = "SELECT * FROM users u"
        >>> ast = sqlglot.parse_one(sql)
        >>> from_clause = get_from_clause(ast)
        >>> table_node = from_clause.this
        >>> name, alias = extract_table_name(table_node)
        >>> name == "users"
        True
        >>> alias == "u"
        True
    """
    # Handle Table node with alias (e.g., "users u" or "users AS u")
    if isinstance(table_node, expressions.Table):
        table_name = table_node.name
        alias = None
        
        # Extract alias from TableAlias if present
        if table_node.alias:
            if isinstance(table_node.alias, expressions.TableAlias):
                alias = table_node.alias.this.name
            elif isinstance(table_node.alias, expressions.Identifier):
                alias = table_node.alias.name
            elif isinstance(table_node.alias, str):
                alias = table_node.alias
        
        # Handle qualified names (schema.table)
        if table_node.db:
            if table_node.catalog:
                # catalog.schema.table
                table_name = f"{table_node.catalog}.{table_node.db}.{table_name}"
            else:
                # schema.table
                table_name = f"{table_node.db}.{table_name}"
        
        return (table_name, alias)

    # Handle Alias node (wraps table)
    if isinstance(table_node, expressions.Alias):
        alias = table_node.alias
        if isinstance(alias, expressions.Identifier):
            alias = alias.name
        elif isinstance(alias, str):
            alias = alias
        else:
            alias = None
        
        # Get the actual table from the aliased expression
        actual_table = table_node.this
        if isinstance(actual_table, expressions.Table):
            table_name = actual_table.name
            # Handle qualified names (schema.table)
            if actual_table.db:
                if actual_table.catalog:
                    # catalog.schema.table
                    table_name = f"{actual_table.catalog}.{actual_table.db}.{table_name}"
                else:
                    # schema.table
                    table_name = f"{actual_table.db}.{table_name}"
            return (table_name, alias)
        elif isinstance(actual_table, expressions.Identifier):
            # Simple identifier with alias
            return (actual_table.name, alias)
        else:
            # Subquery or other complex expression
            raise ValueError(
                f"Unsupported table expression type in Alias: {type(actual_table).__name__}"
            )

    # Handle Identifier node (simple table name)
    if isinstance(table_node, expressions.Identifier):
        return (table_node.name, None)

    # Handle subquery (not supported in v0.1)
    if isinstance(table_node, expressions.Subquery):
        raise NotImplementedError(
            "Subqueries in FROM clause are not supported in v0.1"
        )

    # Unsupported node type
    raise ValueError(
        f"Unsupported table node type: {type(table_node).__name__}. "
        f"Only Table, Alias, TableAlias, and Identifier nodes are supported."
    )


def split_qualified_name(name: str) -> Tuple[Optional[str], Optional[str], str]:
    """Split a qualified table name into database, schema, and table.

    This function splits a qualified table name (e.g., "db.schema.table"
    or "schema.table") into its components.

    Args:
        name: Qualified table name string.

    Returns:
        Tuple of (database, schema, table), where database and schema may be None.

    Example:
        >>> split_qualified_name("public.orders")
        (None, 'public', 'orders')
        >>> split_qualified_name("prod.public.orders")
        ('prod', 'public', 'orders')
        >>> split_qualified_name("orders")
        (None, None, 'orders')
    """
    parts = name.split(".")
    if len(parts) == 1:
        return (None, None, parts[0])
    elif len(parts) == 2:
        return (None, parts[0], parts[1])
    elif len(parts) == 3:
        return (parts[0], parts[1], parts[2])
    else:
        # More than 3 parts - treat first as catalog, second as schema, rest as table
        return (parts[0], parts[1], ".".join(parts[2:]))

