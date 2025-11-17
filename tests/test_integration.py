"""
Integration tests for lineage analyzer.

This module contains end-to-end integration tests for the lineage analyzer,
testing the complete analysis workflow from SQL input to dependency output.
"""

import pytest

from lineage_analyzer import LineageAnalyzer
from lineage_analyzer.exceptions import LineageError
from lineage_analyzer.models.config import LineageConfig
from lineage_analyzer.models.dependency import ExpressionType
from lineage_analyzer.schema.dict_provider import DictSchemaProvider


class TestIntegration:
    """Integration tests for LineageAnalyzer."""

    def setup_method(self):
        """Set up test fixtures."""
        self.analyzer = LineageAnalyzer()

    def test_e2e_simple_query(self):
        """Test 1: Simple query."""
        sql = "SELECT id, name FROM users"
        result = self.analyzer.analyze(sql)

        assert result.success
        assert len(result.dependencies) == 2
        assert result.get_source_tables() == ["users"]
        assert set(result.get_target_columns()) == {"id", "name"}

    def test_e2e_with_schema(self):
        """Test 2: Query with schema validation."""
        schema = {"orders": ["id", "amount", "tax"]}
        analyzer = LineageAnalyzer(
            schema_provider=DictSchemaProvider(schema)
        )

        sql = "SELECT amount + tax AS total FROM orders"
        result = analyzer.analyze(sql)

        assert result.success
        assert len(result.dependencies) == 2
        source_columns = {dep.source.column for dep in result.dependencies}
        assert "amount" in source_columns
        assert "tax" in source_columns

    def test_e2e_join_query(self):
        """Test 3: JOIN query."""
        sql = """
        SELECT 
            o.id,
            o.amount * (1 - c.discount) AS final_price
        FROM orders o
        JOIN customers c ON o.customer_id = c.id
        """

        result = self.analyzer.analyze(sql)

        assert result.success
        source_tables = result.get_source_tables()
        assert "orders" in source_tables
        assert "customers" in source_tables

        # Check dependencies
        dep_ids = [d for d in result.dependencies if d.target.column == "id"]
        dep_final_price = [
            d for d in result.dependencies if d.target.column == "final_price"
        ]

        assert len(dep_ids) == 1
        assert dep_ids[0].source.table == "orders"
        assert dep_ids[0].source.column == "id"

        assert len(dep_final_price) == 2  # amount, discount (from customers)
        source_cols = {d.source.column for d in dep_final_price}
        assert "amount" in source_cols
        assert "discount" in source_cols

    def test_e2e_to_graph(self):
        """Test 4: Graph conversion."""
        sql = "SELECT amount + tax AS total FROM orders"
        result = self.analyzer.analyze(sql)

        assert result.success

        graph = result.to_graph()
        assert graph.graph.number_of_nodes() == 3  # amount, tax, total

        upstream = graph.get_upstream_columns("total")
        assert len(upstream) == 2

        # Check graph statistics
        stats = graph.get_statistics()
        assert stats["total_nodes"] == 3
        assert stats["source_nodes"] == 2
        assert stats["target_nodes"] == 1
        assert stats["total_edges"] == 2

    def test_e2e_batch_analysis(self):
        """Test 5: Batch analysis."""
        sqls = [
            "SELECT id FROM users",
            "SELECT amount FROM orders",
        ]

        results = self.analyzer.analyze_batch(sqls)

        assert len(results) == 2
        assert all(r.success for r in results)
        assert len(results[0].dependencies) == 1
        assert len(results[1].dependencies) == 1

    def test_e2e_error_handling(self):
        """Test 6: Error handling."""
        # Use a truly unsupported feature (window functions) for error testing
        sql = "SELECT id, ROW_NUMBER() OVER (ORDER BY id) AS rn FROM users"

        result = self.analyzer.analyze(sql)

        assert not result.success
        assert result.error is not None
        assert "not supported" in result.error.lower() or "window" in result.error.lower()

    def test_e2e_to_json(self):
        """Test 7: JSON output."""
        sql = "SELECT id, name FROM users"
        result = self.analyzer.analyze(sql)

        assert result.success

        json_str = result.to_json()
        assert "dependencies" in json_str
        assert "tables" in json_str
        assert "success" in json_str

        # Parse JSON to verify structure
        import json

        data = json.loads(json_str)
        assert data["success"] is True
        assert len(data["dependencies"]) == 2
        assert "users" in data["tables"]

    def test_e2e_to_dict(self):
        """Test 8: Dictionary output."""
        sql = "SELECT id, name FROM users"
        result = self.analyzer.analyze(sql)

        assert result.success

        data = result.to_dict()
        assert data["success"] is True
        assert len(data["dependencies"]) == 2
        assert "users" in data["tables"]
        assert isinstance(data["warnings"], list)

    def test_e2e_get_dependencies_for_target(self):
        """Test 9: Get dependencies for target column."""
        sql = "SELECT amount + tax AS total, amount * 2 AS doubled FROM orders"
        result = self.analyzer.analyze(sql)

        assert result.success

        deps_total = result.get_dependencies_for_target("total")
        assert len(deps_total) == 2
        source_cols = {d.source.column for d in deps_total}
        assert "amount" in source_cols
        assert "tax" in source_cols

        deps_doubled = result.get_dependencies_for_target("doubled")
        assert len(deps_doubled) == 1
        assert deps_doubled[0].source.column == "amount"

    def test_e2e_has_warnings(self):
        """Test 10: Warning detection."""
        sql = "SELECT id FROM users"
        result = self.analyzer.analyze(sql)

        assert result.success
        assert not result.has_warnings()
        assert not result.has_errors()

    def test_e2e_complex_expression(self):
        """Test 11: Complex expression."""
        sql = """
        SELECT 
            id,
            amount * (1 - discount) AS net_amount,
            CASE 
                WHEN amount > 1000 THEN 'high'
                ELSE 'low'
            END AS category
        FROM orders
        """

        result = self.analyzer.analyze(sql)

        assert result.success
        assert len(result.dependencies) >= 4

        # Check expression types
        dep_ids = [d for d in result.dependencies if d.target.column == "id"]
        dep_net_amount = [
            d for d in result.dependencies if d.target.column == "net_amount"
        ]
        dep_category = [
            d for d in result.dependencies if d.target.column == "category"
        ]

        assert len(dep_ids) == 1
        assert dep_ids[0].expression_type == ExpressionType.DIRECT

        assert len(dep_net_amount) == 2  # amount, discount
        assert all(
            d.expression_type == ExpressionType.COMPUTED for d in dep_net_amount
        )

        assert len(dep_category) >= 1  # amount (in WHEN condition)
        assert all(d.expression_type == ExpressionType.CASE for d in dep_category)

    def test_e2e_function_expression(self):
        """Test 12: Function expression."""
        sql = "SELECT UPPER(name) AS upper_name, LENGTH(email) AS email_len FROM users"
        result = self.analyzer.analyze(sql)

        assert result.success
        assert len(result.dependencies) == 2

        dep_name = [d for d in result.dependencies if d.source.column == "name"]
        dep_email = [d for d in result.dependencies if d.source.column == "email"]

        assert len(dep_name) == 1
        assert dep_name[0].expression_type == ExpressionType.FUNCTION

        assert len(dep_email) == 1
        assert dep_email[0].expression_type == ExpressionType.FUNCTION

    def test_e2e_graph_upstream_downstream(self):
        """Test 13: Graph upstream/downstream queries."""
        sql = "SELECT amount + tax AS total FROM orders"
        result = self.analyzer.analyze(sql)

        assert result.success

        graph = result.to_graph()

        # Test upstream
        upstream = graph.get_upstream_columns("total")
        assert len(upstream) == 2
        assert any("amount" in col for col in upstream)
        assert any("tax" in col for col in upstream)

        # Test downstream
        downstream = graph.get_downstream_columns("orders", "amount")
        assert "total" in downstream

    def test_e2e_invalid_sql(self):
        """Test 14: Invalid SQL handling."""
        sql = "SELECT * FROM"  # Invalid SQL

        result = self.analyzer.analyze(sql)

        assert not result.success
        assert result.error is not None

    def test_e2e_non_select_statement(self):
        """Test 15: Non-SELECT statement."""
        sql = "INSERT INTO users VALUES (1, 'test')"

        result = self.analyzer.analyze(sql)

        assert not result.success
        assert result.error is not None
        assert "not supported" in result.error.lower() or "SELECT" in result.error

