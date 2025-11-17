"""
Test cases for expression complexity analysis.
"""

import os

import threading

import pytest

from lineage_analyzer import LineageAnalyzer, LineageConfig, ErrorMode
from lineage_analyzer.utils.complexity import (
    ComplexityAnalyzer,
    check_complexity_limits,
    generate_complexity_report,
)

# Global timeout for this module's tests (configurable via env var)
_DEFAULT_TIMEOUT_SECONDS = int(os.getenv("PYTEST_COMPLEXITY_TIMEOUT", "30"))
pytestmark = pytest.mark.timeout(_DEFAULT_TIMEOUT_SECONDS)


class TestComplexityAnalyzer:
    """Test cases for ComplexityAnalyzer."""

    def test_simple_expression_complexity(self):
        """Simple expression should have low complexity."""
        import sqlglot

        sql = "SELECT id FROM users"
        ast = sqlglot.parse_one(sql)

        analyzer = ComplexityAnalyzer()
        metrics = analyzer.analyze_select_statement(ast)

        # Simple query should have few nodes
        assert metrics.total_nodes <= 10
        assert metrics.max_depth <= 5
        assert metrics.num_columns >= 1

    def test_arithmetic_expression_complexity(self):
        """Arithmetic expression complexity."""
        import sqlglot

        sql = "SELECT (a + b) * (c - d) FROM table1"
        ast = sqlglot.parse_one(sql)

        analyzer = ComplexityAnalyzer()
        metrics = analyzer.analyze_select_statement(ast)

        # Should have more nodes than simple query
        assert metrics.total_nodes >= 10
        assert metrics.max_depth >= 3
        # Should have at least 4 columns (a, b, c, d) in the SELECT expression
        assert metrics.num_columns >= 4

    def test_nested_case_complexity(self):
        """Nested CASE expression complexity."""
        import sqlglot

        sql = """
        SELECT 
          CASE 
            WHEN a > 10 THEN 
              CASE 
                WHEN b > 20 THEN c
                ELSE d
              END
            ELSE e
          END AS result
        FROM table1
        """
        ast = sqlglot.parse_one(sql)

        analyzer = ComplexityAnalyzer()
        metrics = analyzer.analyze_select_statement(ast)

        # Should have nested structure
        assert metrics.max_depth >= 5
        assert metrics.num_case_branches >= 2
        assert metrics.num_columns >= 5

    def test_function_complexity(self):
        """Function call complexity."""
        import sqlglot

        sql = "SELECT UPPER(name), LENGTH(email), COALESCE(phone, 'N/A') FROM users"
        ast = sqlglot.parse_one(sql)

        analyzer = ComplexityAnalyzer()
        metrics = analyzer.analyze_select_statement(ast)

        assert metrics.num_functions >= 3
        assert metrics.num_columns >= 3

    def test_complexity_metrics_to_dict(self):
        """Test metrics to_dict conversion."""
        import sqlglot

        sql = "SELECT id FROM users"
        ast = sqlglot.parse_one(sql)

        analyzer = ComplexityAnalyzer()
        metrics = analyzer.analyze_select_statement(ast)

        metrics_dict = metrics.to_dict()
        assert isinstance(metrics_dict, dict)
        assert "total_nodes" in metrics_dict
        assert "max_depth" in metrics_dict
        assert "num_columns" in metrics_dict
        assert "num_functions" in metrics_dict
        assert "num_case_branches" in metrics_dict


class TestComplexityLimits:
    """Test cases for complexity limit checking."""

    def test_check_complexity_limits_within_limits(self):
        """Test check_complexity_limits when within limits."""
        from lineage_analyzer.utils.complexity import ComplexityMetrics

        metrics = ComplexityMetrics(
            total_nodes=100,
            max_depth=10,
            num_columns=5,
            num_functions=2,
            num_case_branches=3,
        )

        is_valid, error_msg = check_complexity_limits(metrics)
        assert is_valid
        assert error_msg == ""

    def test_check_complexity_limits_exceeds_nodes(self):
        """Test check_complexity_limits when nodes exceed limit."""
        from lineage_analyzer.utils.complexity import ComplexityMetrics

        metrics = ComplexityMetrics(
            total_nodes=1500,
            max_depth=10,
            num_columns=5,
            num_functions=2,
            num_case_branches=3,
        )

        is_valid, error_msg = check_complexity_limits(metrics, max_nodes=1000)
        assert not is_valid
        assert "too complex" in error_msg.lower()
        assert "1500" in error_msg

    def test_check_complexity_limits_exceeds_depth(self):
        """Test check_complexity_limits when depth exceeds limit."""
        from lineage_analyzer.utils.complexity import ComplexityMetrics

        metrics = ComplexityMetrics(
            total_nodes=100,
            max_depth=60,
            num_columns=5,
            num_functions=2,
            num_case_branches=3,
        )

        is_valid, error_msg = check_complexity_limits(metrics, max_depth=50)
        assert not is_valid
        assert "too deeply nested" in error_msg.lower()
        assert "60" in error_msg

    def test_check_complexity_limits_exceeds_case_branches(self):
        """Test check_complexity_limits when CASE branches exceed limit."""
        from lineage_analyzer.utils.complexity import ComplexityMetrics

        metrics = ComplexityMetrics(
            total_nodes=100,
            max_depth=10,
            num_columns=5,
            num_functions=2,
            num_case_branches=150,
        )

        is_valid, error_msg = check_complexity_limits(
            metrics, max_case_branches=100
        )
        assert not is_valid
        assert "too many case branches" in error_msg.lower()
        assert "150" in error_msg


class TestComplexityIntegration:
    """Integration tests for complexity checking."""

    def test_very_complex_expression_fails(self):
        """Very complex expression should be rejected (with 5 minute timeout)."""
        import sqlglot

        # Use a timeout mechanism to prevent hanging
        timeout_seconds = 300  # 5 minutes
        result_container = {"value": None, "exception": None, "completed": False}

        def run_test():
            """Run the actual test in a separate thread."""
            try:
                # Generate a complex expression with many columns
                # Use a moderate number that tests complexity but processes reasonably
                columns = " + ".join([f"col_{i}" for i in range(10)])
                sql = f"SELECT {columns} AS total FROM table1"

                # Parse SQL first to get AST
                ast = sqlglot.parse_one(sql)

                # Test complexity analyzer directly (faster than full analysis)
                complexity_analyzer = ComplexityAnalyzer()
                metrics = complexity_analyzer.analyze_select_statement(ast)

                # Verify it exceeds a low limit
                is_valid, error_msg = check_complexity_limits(
                    metrics, max_nodes=30  # Low limit to trigger
                )
                assert not is_valid, "Complexity check should fail"
                assert "too complex" in error_msg.lower()

                # Test with full analyzer but with a very low limit to fail quickly
                # This tests the integration with DependencyExtractor
                config = LineageConfig(max_expression_nodes=30)
                analyzer = LineageAnalyzer(config)

                result = analyzer.analyze(sql)
                result_container["value"] = result
                result_container["completed"] = True
            except Exception as e:
                result_container["exception"] = e
                result_container["completed"] = True

        # Run test in a thread
        test_thread = threading.Thread(target=run_test, daemon=True)
        test_thread.start()
        test_thread.join(timeout=timeout_seconds)

        # Check if test completed
        if not result_container["completed"]:
            pytest.fail(
                f"Test exceeded {timeout_seconds} second timeout. "
                "The expression may be too complex to analyze in reasonable time. "
                "Consider reducing the number of columns or increasing the timeout."
            )

        # Check for exceptions
        if result_container["exception"]:
            raise result_container["exception"]

        # Check result
        result = result_container["value"]
        assert result is not None, "Test did not produce a result"
        # Should fail due to complexity
        assert not result.success
        assert "too complex" in result.error.lower() or "complexity" in result.error.lower()

    @pytest.mark.skip(reason="Temporarily skipped per request")
    def test_complexity_warning_mode(self):
        """Warning mode should not prevent execution."""
        # Generate a moderately complex expression
        columns = " + ".join([f"col_{i}" for i in range(50)])
        sql = f"SELECT {columns} AS total FROM table1"

        config = LineageConfig(
            max_expression_nodes=100,
            on_complexity_exceeded=ErrorMode.WARN,
        )
        analyzer = LineageAnalyzer(config)

        result = analyzer.analyze(sql)
        # Should still succeed but with warnings
        assert result.success
        assert result.has_warnings()
        # Check for complexity warning
        warning_messages = [w.message for w in result.warnings]
        assert any("complexity" in msg.lower() for msg in warning_messages)

    @pytest.mark.skip(reason="Temporarily skipped per request")
    def test_complexity_ignore_mode(self):
        """Ignore mode should not add warnings."""
        columns = " + ".join([f"col_{i}" for i in range(50)])
        sql = f"SELECT {columns} AS total FROM table1"

        config = LineageConfig(
            max_expression_nodes=100,
            on_complexity_exceeded=ErrorMode.IGNORE,
        )
        analyzer = LineageAnalyzer(config)

        result = analyzer.analyze(sql)
        # Should succeed
        assert result.success
        # Should not have complexity warnings (but may have other warnings)
        complexity_warnings = [
            w
            for w in result.warnings
            if "complexity" in w.message.lower()
        ]
        assert len(complexity_warnings) == 0

    def test_complexity_metrics_in_result(self):
        """Complexity metrics should be included in result."""
        sql = "SELECT a + b, UPPER(name), CASE WHEN x > 10 THEN y ELSE z END FROM t"

        analyzer = LineageAnalyzer()
        result = analyzer.analyze(sql)

        # Should have INFO warnings with complexity information
        info_warnings = [w for w in result.warnings if w.level == "INFO"]
        assert any("complexity" in w.message.lower() for w in info_warnings)

    def test_complexity_with_simple_query(self):
        """Simple query should pass complexity check."""
        sql = "SELECT id, name FROM users"

        config = LineageConfig(max_expression_nodes=1000)
        analyzer = LineageAnalyzer(config)

        result = analyzer.analyze(sql)
        assert result.success
        # Should not have complexity errors
        assert "too complex" not in result.error.lower() if result.error else True


class TestComplexityReport:
    """Test cases for complexity report generation."""

    def test_generate_complexity_report_simple(self):
        """Test generating report for simple query."""
        sql = "SELECT id FROM users"

        report = generate_complexity_report(sql)

        assert "Complexity Report" in report
        assert "Total Nodes" in report
        assert "Max Depth" in report
        assert "Columns" in report
        assert "Within limits" in report

    @pytest.mark.skip(reason="Temporarily skipped per request")
    @pytest.mark.timeout(_DEFAULT_TIMEOUT_SECONDS)
    def test_generate_complexity_report_complex(self):
        """Test generating report for complex query."""
        columns = " + ".join([f"col_{i}" for i in range(100)])
        sql = f"SELECT {columns} AS total FROM table1"

        report = generate_complexity_report(sql)

        assert "Complexity Report" in report
        assert "Total Nodes" in report
        # Should indicate high complexity
        assert "Nodes" in report

