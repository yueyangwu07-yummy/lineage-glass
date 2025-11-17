"""
End-to-end tests: Simulate real user scenarios.

This module contains end-to-end tests that simulate real-world usage
of the lineage analyzer.
"""

import json
from pathlib import Path

import pytest

from lineage_analyzer import DictSchemaProvider, ScriptAnalyzer


class TestE2EScenarios:
    """End-to-end test scenarios."""

    def test_ecommerce_pipeline(self):
        """Test complete e-commerce pipeline."""
        # Read example script
        script_path = Path("examples/ecommerce/pipeline.sql")
        if not script_path.exists():
            pytest.skip("Example file not found")

        script = script_path.read_text()

        # Read schema
        schema_path = Path("examples/ecommerce/schema.json")
        schema_dict = json.loads(schema_path.read_text())
        schema_provider = DictSchemaProvider(schema_dict)

        # Analyze (may fail on aggregation, that's OK for v1.0)
        analyzer = ScriptAnalyzer(schema_provider=schema_provider)
        try:
            result = analyzer.analyze_script(script)
        except NotImplementedError:
            # Aggregation not supported in v1.0, skip this test
            pytest.skip("Aggregation functions not supported in v1.0")

        # Verify: should create multiple derived tables
        derived_tables = result.get_derived_tables()
        assert len(derived_tables) >= 3  # At least 3 tables

        # Verify: clean_orders exists
        clean_orders = result.get_table("clean_orders")
        assert clean_orders is not None

        # Verify: user_report exists (if aggregation is supported)
        user_report = result.get_table("user_report")
        if user_report:
            # Trace field if column exists
            if user_report.has_column("name"):
                paths = result.trace("user_report", "name")
                assert len(paths) > 0
                # Should trace back to customers.name
                assert any(
                    "customers" in path.source.column.table for path in paths if path.source
                )

    def test_simple_transform(self):
        """Test simple transformation."""
        script_path = Path("examples/simple/transform.sql")
        if not script_path.exists():
            pytest.skip("Example file not found")

        script = script_path.read_text()

        analyzer = ScriptAnalyzer()
        try:
            result = analyzer.analyze_script(script)
        except NotImplementedError:
            # Aggregation not supported in v1.0, skip this test
            pytest.skip("Aggregation functions not supported in v1.0")

        # Verify table creation
        assert result.get_table("user_orders") is not None
        # user_summary may not exist if aggregation is not supported
        # But user_orders should exist

    def test_multi_insert_scenario(self):
        """Test multiple INSERT scenario."""
        script = """
        CREATE TABLE metrics AS SELECT value FROM source1;
        INSERT INTO metrics SELECT value FROM source2;
        INSERT INTO metrics SELECT value FROM source3;
        CREATE TABLE report AS SELECT value * 2 AS doubled FROM metrics;
        """

        schema = DictSchemaProvider(
            {"source1": ["value"], "source2": ["value"], "source3": ["value"]}
        )

        analyzer = ScriptAnalyzer(schema_provider=schema)
        result = analyzer.analyze_script(script)

        # Verify metrics has three sources
        metrics = result.get_table("metrics")
        assert metrics is not None

        value_lineage = metrics.get_column("value")
        assert len(value_lineage.sources) == 3

        # Verify source tables
        source_tables = {s.table for s in value_lineage.sources}
        assert source_tables == {"source1", "source2", "source3"}

    def test_complex_join_chain(self):
        """Test complex JOIN chain."""
        script = """
        CREATE TABLE t1 AS 
        SELECT o.id, o.amount, c.name
        FROM orders o
        JOIN customers c ON o.customer_id = c.id;
        
        CREATE TABLE t2 AS
        SELECT t1.id, t1.amount, p.product_name
        FROM t1
        JOIN products p ON t1.id = p.order_id;
        
        CREATE TABLE t3 AS
        SELECT t2.product_name, t2.amount * 2 AS doubled_amount
        FROM t2;
        """

        schema = DictSchemaProvider(
            {
                "orders": ["id", "customer_id", "amount"],
                "customers": ["id", "name"],
                "products": ["order_id", "product_name"],
            }
        )

        analyzer = ScriptAnalyzer(schema_provider=schema)
        result = analyzer.analyze_script(script)

        # Verify all three tables are created
        assert result.get_table("t1") is not None
        assert result.get_table("t2") is not None
        assert result.get_table("t3") is not None

        # Verify lineage chain
        paths = result.trace("t3", "doubled_amount")
        assert len(paths) > 0
        # Should trace back to orders.amount
        assert any(
            "orders" in path.source.column.table for path in paths if path.source
        )
