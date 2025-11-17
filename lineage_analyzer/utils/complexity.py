"""
Expression complexity analyzer for lineage analysis.

This module provides functionality to analyze and limit the complexity
of SQL expressions to prevent performance issues and stack overflow.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import sqlglot
from sqlglot import expressions


@dataclass
class ComplexityMetrics:
    """Expression complexity metrics."""

    total_nodes: int  # AST node count
    max_depth: int  # Maximum nesting depth
    num_columns: int  # Column reference count
    num_functions: int  # Function call count
    num_case_branches: int  # CASE branch count

    def is_too_complex(
        self, max_nodes: int = 1000, max_depth: int = 50
    ) -> bool:
        """Check if expression is too complex.

        Args:
            max_nodes: Maximum allowed nodes.
            max_depth: Maximum allowed depth.

        Returns:
            True if expression exceeds limits.
        """
        return self.total_nodes > max_nodes or self.max_depth > max_depth

    def to_dict(self) -> dict[str, int]:
        """Convert to dictionary.

        Returns:
            Dictionary representation of metrics.
        """
        return {
            "total_nodes": self.total_nodes,
            "max_depth": self.max_depth,
            "num_columns": self.num_columns,
            "num_functions": self.num_functions,
            "num_case_branches": self.num_case_branches,
        }


class ComplexityAnalyzer:
    """Expression complexity analyzer.

    Used to quickly assess SQL complexity before parsing.
    """

    def __init__(self) -> None:
        """Initialize complexity analyzer."""
        self.metrics = ComplexityMetrics(
            total_nodes=0,
            max_depth=0,
            num_columns=0,
            num_functions=0,
            num_case_branches=0,
        )
        self._current_depth = 0

    def analyze_expression(
        self, expr_node: sqlglot.Expression
    ) -> ComplexityMetrics:
        """Analyze complexity of a single expression.

        Args:
            expr_node: sqlglot expression node.

        Returns:
            ComplexityMetrics object.
        """
        self._reset()
        self._visit(expr_node, depth=0)
        return self.metrics

    def analyze_select_statement(
        self, ast: sqlglot.Expression
    ) -> ComplexityMetrics:
        """Analyze complexity of entire SELECT statement.

        Args:
            ast: sqlglot SELECT statement AST.

        Returns:
            ComplexityMetrics object (sum of all SELECT expressions).
        """
        self._reset()

        # Analyze all SELECT expressions
        if hasattr(ast, "selects") and ast.selects:
            for expr in ast.selects:
                self._visit(expr, depth=0)
        elif hasattr(ast, "expressions") and ast.expressions:
            # Fallback: try expressions attribute
            for expr in ast.expressions:
                self._visit(expr, depth=0)
        else:
            # If no selects found, analyze the whole AST
            self._visit(ast, depth=0)

        return self.metrics

    def _visit(self, node: Any, depth: int) -> None:
        """Recursively visit AST nodes and collect complexity metrics.

        Args:
            node: AST node.
            depth: Current depth.
        """
        if node is None:
            return

        # Update metrics
        self.metrics.total_nodes += 1
        self.metrics.max_depth = max(self.metrics.max_depth, depth)

        # Identify specific node types
        node_type = type(node).__name__

        # Special-case CASE first (it subclasses Func in sqlglot)
        if node_type == "Case":
            # Count CASE branches
            if hasattr(node, "args") and "ifs" in node.args:
                self.metrics.num_case_branches += len(node.args["ifs"])
            elif hasattr(node, "ifs") and node.ifs:
                self.metrics.num_case_branches += len(node.ifs)

        # Check if it's a function call (after handling CASE)
        elif isinstance(node, expressions.Func):
            self.metrics.num_functions += 1

        elif node_type == "Column":
            self.metrics.num_columns += 1

        elif node_type == "If":
            # Some sqlglot versions represent CASE branches as separate If nodes.
            # Count each If as one CASE branch to ensure nested CASE structures are reflected.
            self.metrics.num_case_branches += 1

        # Recursively visit child nodes
        if hasattr(node, "args"):
            for arg_value in node.args.values():
                if arg_value is None:
                    continue

                if isinstance(arg_value, list):
                    for item in arg_value:
                        self._visit(item, depth + 1)
                else:
                    self._visit(arg_value, depth + 1)

        # Handle common attributes: node.this, node.expression, node.left, node.right
        if hasattr(node, "this") and node.this:
            self._visit(node.this, depth + 1)

        if hasattr(node, "expression") and node.expression:
            self._visit(node.expression, depth + 1)

        if hasattr(node, "left") and node.left:
            self._visit(node.left, depth + 1)

        if hasattr(node, "right") and node.right:
            self._visit(node.right, depth + 1)

        # Handle expressions list (for function arguments, etc.)
        if hasattr(node, "expressions") and node.expressions:
            for expr in node.expressions:
                self._visit(expr, depth + 1)

    def _reset(self) -> None:
        """Reset metrics."""
        self.metrics = ComplexityMetrics(
            total_nodes=0,
            max_depth=0,
            num_columns=0,
            num_functions=0,
            num_case_branches=0,
        )
        self._current_depth = 0


def check_complexity_limits(
    metrics: ComplexityMetrics,
    max_nodes: int = 1000,
    max_depth: int = 50,
    max_case_branches: int = 100,
) -> tuple[bool, str]:
    """Check if complexity exceeds limits.

    Args:
        metrics: Complexity metrics.
        max_nodes: Maximum node count.
        max_depth: Maximum depth.
        max_case_branches: Maximum CASE branches.

    Returns:
        Tuple of (is_valid, error_message).
        - is_valid: True if within limits.
        - error_message: Error message if exceeded.
    """
    if metrics.total_nodes > max_nodes:
        return False, (
            f"Expression too complex: {metrics.total_nodes} nodes "
            f"(limit: {max_nodes}). Consider simplifying the query."
        )

    if metrics.max_depth > max_depth:
        return False, (
            f"Expression too deeply nested: {metrics.max_depth} levels "
            f"(limit: {max_depth}). Consider breaking into smaller queries."
        )

    if metrics.num_case_branches > max_case_branches:
        return False, (
            f"Too many CASE branches: {metrics.num_case_branches} "
            f"(limit: {max_case_branches}). Consider using lookup tables."
        )

    return True, ""


def generate_complexity_report(sql: str) -> str:
    """Generate a readable complexity report.

    Args:
        sql: SQL statement.

    Returns:
        Formatted report text.

    Example output:
        Complexity Report
        =================
        Total Nodes: 45
        Max Depth: 8
        Columns: 12
        Functions: 3
        CASE Branches: 5

        Verdict: ✓ Within limits
    """
    from lineage_analyzer.models.config import LineageConfig
    from lineage_analyzer.parser.sql_parser import SQLParser

    parser = SQLParser(LineageConfig())
    ast = parser.parse(sql)

    analyzer = ComplexityAnalyzer()
    metrics = analyzer.analyze_select_statement(ast)

    is_valid, error_msg = check_complexity_limits(metrics)

    verdict = (
        "✓ Within limits" if is_valid else f"✗ Too complex: {error_msg}"
    )

    return f"""
Complexity Report
=================
Total Nodes: {metrics.total_nodes}
Max Depth: {metrics.max_depth}
Columns: {metrics.num_columns}
Functions: {metrics.num_functions}
CASE Branches: {metrics.num_case_branches}

Verdict: {verdict}
""".strip()

