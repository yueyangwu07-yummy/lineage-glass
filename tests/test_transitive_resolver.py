"""
Tests for transitive lineage resolver.

This module contains tests for TransitiveLineageResolver and ScriptAnalysisResult
query interfaces.
"""

import pytest

from lineage_analyzer import (
    ColumnLineage,
    ColumnRef,
    DictSchemaProvider,
    ExpressionType,
    LineageConfig,
    LineageError,
    TableDefinition,
    TableRegistry,
    TableType,
)
from lineage_analyzer.analyzer.script_analyzer import ScriptAnalyzer
from lineage_analyzer.resolver.transitive_resolver import TransitiveLineageResolver


class TestTransitiveLineageResolver:
    """Tests for TransitiveLineageResolver."""

    def setup_method(self):
        """Create test data."""
        self.registry = TableRegistry()

        # Register source table
        self.registry.register_source_table("orders", ["amount", "tax"])

        # Create derived table chain: orders → t1 → t2 → t3
        # t1: SELECT amount FROM orders
        t1 = TableDefinition(name="t1", table_type=TableType.TABLE)
        t1.add_column(
            ColumnLineage(
                name="amount",
                sources=[ColumnRef(table="orders", column="amount")],
            )
        )
        self.registry.register_table(t1)

        # t2: SELECT amount * 2 AS doubled FROM t1
        t2 = TableDefinition(name="t2", table_type=TableType.TABLE)
        t2.add_column(
            ColumnLineage(
                name="doubled",
                sources=[ColumnRef(table="t1", column="amount")],
                expression="amount * 2",
                expression_type=ExpressionType.COMPUTED,
            )
        )
        self.registry.register_table(t2)

        # t3: SELECT doubled + 100 AS final FROM t2
        t3 = TableDefinition(name="t3", table_type=TableType.TABLE)
        t3.add_column(
            ColumnLineage(
                name="final",
                sources=[ColumnRef(table="t2", column="doubled")],
                expression="doubled + 100",
                expression_type=ExpressionType.COMPUTED,
            )
        )
        self.registry.register_table(t3)

        self.resolver = TransitiveLineageResolver(self.registry)

    def test_trace_to_source_single_hop(self):
        """Test single-hop tracing."""
        paths = self.resolver.trace_to_source("t1", "amount")

        assert len(paths) == 1
        path = paths[0]

        # Verify path: t1.amount ← orders.amount
        assert path.hops == 1
        assert path.target is not None
        assert path.target.column.table == "t1"
        assert path.source is not None
        assert path.source.column.table == "orders"
        assert path.source.is_source()

    def test_trace_to_source_multi_hop(self):
        """Test multi-hop tracing."""
        paths = self.resolver.trace_to_source("t3", "final")

        assert len(paths) == 1
        path = paths[0]

        # Verify path: t3.final ← t2.doubled ← t1.amount ← orders.amount
        assert path.hops == 3
        assert len(path.nodes) == 4

        # Verify each node
        assert path.nodes[0].column.table == "t3"
        assert path.nodes[1].column.table == "t2"
        assert path.nodes[2].column.table == "t1"
        assert path.nodes[3].column.table == "orders"

        # Verify source
        assert path.source.is_source()

    def test_trace_nonexistent_table(self):
        """Test tracing non-existent table."""
        with pytest.raises(LineageError, match="not found"):
            self.resolver.trace_to_source("nonexistent", "col")

    def test_trace_nonexistent_column(self):
        """Test tracing non-existent column."""
        with pytest.raises(LineageError, match="not found"):
            self.resolver.trace_to_source("t1", "nonexistent")

    def test_find_impact_no_downstream(self):
        """Test impact analysis: no downstream."""
        impacts = self.resolver.find_impact("t3", "final")

        # t3.final has no downstream
        assert len(impacts) == 0

    def test_find_impact_with_downstream(self):
        """Test impact analysis: with downstream."""
        impacts = self.resolver.find_impact("orders", "amount")

        # orders.amount affects t1.amount, t2.doubled, t3.final
        assert len(impacts) == 3

        impacted_columns = {f"{ref.table}.{ref.column}" for ref in impacts}
        assert "t1.amount" in impacted_columns
        assert "t2.doubled" in impacted_columns
        assert "t3.final" in impacted_columns

    def test_explain_calculation(self):
        """Test explain calculation chain."""
        explanation = self.resolver.explain_calculation("t3", "final")

        # Verify contains key information
        assert "t3.final" in explanation
        assert "t2.doubled" in explanation
        assert "t1.amount" in explanation
        assert "orders.amount" in explanation
        assert "doubled + 100" in explanation
        assert "amount * 2" in explanation

    def test_get_all_source_tables(self):
        """Test get all source tables."""
        source_tables = self.resolver.get_all_source_tables("t3", "final")

        assert len(source_tables) == 1
        assert "orders" in source_tables

    def test_multiple_sources(self):
        """Test field with multiple sources."""
        # Create a table with multiple sources
        t4 = TableDefinition(name="t4", table_type=TableType.TABLE)
        t4.add_column(
            ColumnLineage(
                name="total",
                sources=[
                    ColumnRef(table="orders", column="amount"),
                    ColumnRef(table="orders", column="tax"),
                ],
                expression="amount + tax",
                expression_type=ExpressionType.COMPUTED,
            )
        )
        self.registry.register_table(t4)

        paths = self.resolver.trace_to_source("t4", "total")

        # Should have two paths (one to amount, one to tax)
        assert len(paths) == 2

    def test_path_to_string(self):
        """Test path string representation."""
        paths = self.resolver.trace_to_source("t2", "doubled")
        assert len(paths) == 1

        path_str = paths[0].to_string()
        assert "t2.doubled" in path_str
        assert "t1.amount" in path_str
        assert "orders.amount" in path_str

    def test_path_to_dict(self):
        """Test path dictionary conversion."""
        paths = self.resolver.trace_to_source("t2", "doubled")
        assert len(paths) == 1

        path_dict = paths[0].to_dict()
        assert "path" in path_dict
        assert "hops" in path_dict
        assert "nodes" in path_dict
        assert path_dict["hops"] == 2


class TestScriptAnalysisResultQueries:
    """Tests for ScriptAnalysisResult query interfaces (end-to-end)."""

    def test_end_to_end_trace(self):
        """End-to-end test: from script to trace."""
        script = """
        CREATE TABLE t1 AS SELECT amount FROM orders;
        CREATE TABLE t2 AS SELECT amount * 2 AS doubled FROM t1;
        CREATE TABLE t3 AS SELECT doubled + 100 AS final FROM t2;
        """

        schema = DictSchemaProvider({"orders": ["amount", "tax"]})
        analyzer = ScriptAnalyzer(schema_provider=schema)
        result = analyzer.analyze_script(script)

        # Use convenient interface to trace
        paths = result.trace("t3", "final")

        assert len(paths) == 1
        assert paths[0].hops == 3
        assert paths[0].source is not None
        assert paths[0].source.column.table == "orders"

    def test_end_to_end_impact(self):
        """End-to-end test: impact analysis."""
        script = """
        CREATE TABLE t1 AS SELECT amount FROM orders;
        CREATE TABLE t2 AS SELECT amount * 2 AS doubled FROM t1;
        """

        schema = DictSchemaProvider({"orders": ["amount"]})
        analyzer = ScriptAnalyzer(schema_provider=schema)
        result = analyzer.analyze_script(script)

        # Impact analysis
        impacts = result.impact("orders", "amount")

        assert len(impacts) == 2  # t1.amount, t2.doubled

    def test_end_to_end_explain(self):
        """End-to-end test: explain calculation."""
        script = """
        CREATE TABLE t1 AS SELECT amount + tax AS total FROM orders;
        CREATE TABLE t2 AS SELECT total * 2 AS doubled FROM t1;
        """

        schema = DictSchemaProvider({"orders": ["amount", "tax"]})
        analyzer = ScriptAnalyzer(schema_provider=schema)
        result = analyzer.analyze_script(script)

        # Explain calculation
        explanation = result.explain("t2", "doubled")

        # Verify contains key information
        assert "t2.doubled" in explanation
        assert "t1.total" in explanation
        assert "orders.amount" in explanation
        assert "orders.tax" in explanation

    def test_with_insert_statements(self):
        """Test script with INSERT statements."""
        script = """
        CREATE TABLE t1 AS SELECT amount FROM orders;
        INSERT INTO t1 SELECT amount FROM new_orders;
        CREATE TABLE t2 AS SELECT amount * 2 AS doubled FROM t1;
        """

        schema = DictSchemaProvider(
            {"orders": ["amount"], "new_orders": ["amount"]}
        )
        analyzer = ScriptAnalyzer(schema_provider=schema)
        result = analyzer.analyze_script(script)

        # Trace t2.doubled
        paths = result.trace("t2", "doubled")

        # Should have two paths (one through orders, one through new_orders)
        assert len(paths) == 2

        source_tables = {path.source.column.table for path in paths if path.source}
        assert "orders" in source_tables
        assert "new_orders" in source_tables

    def test_cycle_detection(self):
        """Test cycle detection (should not infinite loop)."""
        # Create a potential cycle: t1 → t2 → t1
        # Note: This shouldn't happen in real SQL, but we should handle it
        t1 = TableDefinition(name="t1", table_type=TableType.TABLE)
        t1.add_column(
            ColumnLineage(
                name="col1",
                sources=[ColumnRef(table="t2", column="col2")],
            )
        )
        self.registry = TableRegistry()
        self.registry.register_table(t1)

        t2 = TableDefinition(name="t2", table_type=TableType.TABLE)
        t2.add_column(
            ColumnLineage(
                name="col2",
                sources=[ColumnRef(table="t1", column="col1")],
            )
        )
        self.registry.register_table(t2)

        resolver = TransitiveLineageResolver(self.registry)

        # Should not infinite loop
        paths = resolver.trace_to_source("t1", "col1", max_depth=10)
        # Should return empty or limited paths due to cycle detection
        assert isinstance(paths, list)

