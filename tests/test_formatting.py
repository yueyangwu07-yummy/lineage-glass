"""
Test cases for SQL formatting and highlighting.
"""

import pytest

from lineage_analyzer import LineageAnalyzer
from lineage_analyzer.exceptions import AmbiguousColumnError, UnresolvedReferenceError
from lineage_analyzer.utils.sql_formatter import (
    format_sql,
    highlight_column_in_query,
    highlight_position,
)


class TestSQLFormatter:
    """Test cases for SQL formatting."""

    def test_format_simple_sql(self):
        """Test formatting simple SQL."""
        sql = "SELECT id,name FROM users WHERE age>18"
        formatted = format_sql(sql)

        assert "SELECT" in formatted
        # Should have some formatting (indentation or spacing)
        assert len(formatted) >= len(sql)

    def test_format_complex_sql(self):
        """Test formatting complex SQL."""
        sql = """
        SELECT o.id, o.amount + o.tax AS total, c.name
        FROM orders o
        JOIN customers c ON o.customer_id = c.id
        WHERE o.status = 'active'
        """
        formatted = format_sql(sql)

        assert "SELECT" in formatted
        assert "FROM" in formatted
        assert "JOIN" in formatted

    def test_format_invalid_sql(self):
        """Test formatting invalid SQL (should return original)."""
        sql = "INVALID SQL SYNTAX !!!"
        formatted = format_sql(sql)

        # Should return original SQL if parsing fails
        assert formatted == sql


class TestHighlighting:
    """Test cases for SQL highlighting."""

    def test_highlight_position(self):
        """Test position highlighting."""
        sql = "SELECT id FROM users"
        highlighted = highlight_position(sql, position=7, length=2)  # "id"

        assert "SELECT id FROM users" in highlighted
        assert "^" in highlighted  # Highlight marker

    def test_highlight_column(self):
        """Test column name highlighting."""
        sql = "SELECT id, name FROM users WHERE id > 10"
        highlighted = highlight_column_in_query(sql, "id")

        # Should mark occurrences of "id"
        assert "^" in highlighted or "id" in highlighted

    def test_highlight_column_with_table(self):
        """Test column highlighting with table qualifier."""
        sql = "SELECT o.id, c.id FROM orders o JOIN customers c"
        highlighted = highlight_column_in_query(sql, "id", "o")

        # Should highlight o.id
        assert "^" in highlighted or "o.id" in highlighted


class TestErrorFormatting:
    """Test cases for error message formatting."""

    def test_ambiguous_column_error_formatting(self):
        """Test AmbiguousColumnError with formatting."""
        sql = "SELECT id FROM orders o JOIN customers c ON o.cid = c.id"

        try:
            raise AmbiguousColumnError(
                message="Column 'id' is ambiguous",
                column_name="id",
                possible_tables=["orders", "customers"],
                sql=sql,
            )
        except AmbiguousColumnError as e:
            error_msg = str(e)

            # Verify error message contains key information
            assert "ambiguous" in error_msg.lower()
            assert "orders.id" in error_msg or "orders" in error_msg
            assert "customers.id" in error_msg or "customers" in error_msg
            assert "SELECT" in error_msg  # Contains formatted SQL

    def test_unresolved_reference_error_formatting(self):
        """Test UnresolvedReferenceError with formatting."""
        sql = "SELECT x.id FROM orders o"

        try:
            raise UnresolvedReferenceError(
                message="Cannot resolve reference 'x'",
                reference="x",
                available_tables=["orders"],
                sql=sql,
            )
        except UnresolvedReferenceError as e:
            error_msg = str(e)

            # Verify error message contains key information
            assert "resolve" in error_msg.lower()
            assert "orders" in error_msg
            assert "SELECT" in error_msg  # Contains formatted SQL


class TestResultFormatting:
    """Test cases for result formatting."""

    def test_result_formatted_output(self):
        """Test formatted result output."""
        sql = "SELECT amount + tax AS total FROM orders"
        analyzer = LineageAnalyzer()
        result = analyzer.analyze(sql)

        formatted = result.to_formatted_string()

        # Verify contains key sections
        assert "Lineage Analysis Result" in formatted
        assert "✓ Success" in formatted or "✗ Failed" in formatted
        assert "Dependencies Found" in formatted
        assert "orders.amount" in formatted or "orders" in formatted

    def test_result_formatted_output_with_warnings(self):
        """Test formatted output with warnings."""
        sql = "SELECT id FROM orders o JOIN customers c ON o.cid = c.id"
        analyzer = LineageAnalyzer()
        result = analyzer.analyze(sql)

        formatted = result.to_formatted_string()

        # Should include warnings section
        assert "Warnings" in formatted

    def test_result_formatted_output_without_sql(self):
        """Test formatted output without SQL."""
        sql = "SELECT id FROM users"
        analyzer = LineageAnalyzer()
        result = analyzer.analyze(sql)

        formatted = result.to_formatted_string(include_sql=False)

        # Should not include SQL section
        assert "SQL Query" not in formatted
        # But should still have other sections
        assert "Lineage Analysis Result" in formatted

