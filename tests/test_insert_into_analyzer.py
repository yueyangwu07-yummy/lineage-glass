"""
Tests for INSERT INTO ... SELECT analyzer.

This module contains tests for InsertIntoAnalyzer and ScriptAnalyzer with INSERT INTO.
"""

import pytest
import sqlglot

from lineage_analyzer import (
    ColumnLineage,
    ColumnRef,
    DictSchemaProvider,
    ExpressionType,
    LineageConfig,
    LineageError,
    StatementClassifier,
    StatementType,
    TableDefinition,
    TableRegistry,
    TableType,
)
from lineage_analyzer.analyzer.insert_into_analyzer import InsertIntoAnalyzer
from lineage_analyzer.analyzer.script_analyzer import ScriptAnalyzer


class TestInsertIntoAnalyzer:
    """Tests for InsertIntoAnalyzer."""

    def setup_method(self):
        """Initialize before each test."""
        self.config = LineageConfig()
        self.registry = TableRegistry()

        # Register source tables
        self.registry.register_source_table(
            "orders", ["id", "amount", "tax"]
        )
        self.registry.register_source_table(
            "new_orders", ["id", "amount", "tax"]
        )

        # Create target table
        t1 = TableDefinition(name="t1", table_type=TableType.TABLE)
        t1.add_column(
            ColumnLineage(
                name="total",
                sources=[ColumnRef(table="orders", column="amount")],
            )
        )
        self.registry.register_table(t1)

        self.analyzer = InsertIntoAnalyzer(self.registry, self.config)
        self.classifier = StatementClassifier()

    def _parse_and_classify(self, sql: str):
        """Helper method."""
        ast = sqlglot.parse_one(sql)
        return self.classifier.classify(ast, sql)

    def test_simple_insert_into(self):
        """Test simple INSERT INTO."""
        sql = "INSERT INTO t1 SELECT amount FROM new_orders"
        classified = self._parse_and_classify(sql)

        self.analyzer.analyze(classified)

        # Verify t1.total now has two sources
        t1 = self.registry.get_table("t1")
        assert t1 is not None
        total_lineage = t1.get_column("total")
        assert total_lineage is not None

        assert len(total_lineage.sources) == 2
        source_tables = {s.table for s in total_lineage.sources}
        assert "orders" in source_tables
        assert "new_orders" in source_tables

    def test_insert_with_explicit_columns(self):
        """Test INSERT INTO with explicit column names."""
        # Create table with two columns
        t2 = TableDefinition(name="t2", table_type=TableType.TABLE)
        t2.add_column(ColumnLineage(name="col1", sources=[]))
        t2.add_column(ColumnLineage(name="col2", sources=[]))
        self.registry.register_table(t2)

        # Insert data (reversed column order)
        sql = "INSERT INTO t2 (col2, col1) SELECT amount, tax FROM orders"
        classified = self._parse_and_classify(sql)

        self.analyzer.analyze(classified)

        # Verify column matching is correct
        t2 = self.registry.get_table("t2")
        assert t2 is not None

        col1_lineage = t2.get_column("col1")
        assert col1_lineage is not None
        assert col1_lineage.sources[0].column == "tax"  # col1 corresponds to tax (second)

        col2_lineage = t2.get_column("col2")
        assert col2_lineage is not None
        assert col2_lineage.sources[0].column == "amount"  # col2 corresponds to amount (first)

    def test_insert_into_nonexistent_table(self):
        """Test inserting into non-existent table."""
        sql = "INSERT INTO nonexistent SELECT amount FROM orders"
        classified = self._parse_and_classify(sql)

        with pytest.raises(LineageError, match="does not exist"):
            self.analyzer.analyze(classified)

    def test_insert_column_count_mismatch(self):
        """Test column count mismatch."""
        # t1 has only 1 column
        sql = "INSERT INTO t1 SELECT amount, tax FROM orders"  # 2 columns
        classified = self._parse_and_classify(sql)

        with pytest.raises(LineageError, match="count mismatch"):
            self.analyzer.analyze(classified)

    def test_insert_nonexistent_column(self):
        """Test specifying non-existent column."""
        sql = "INSERT INTO t1 (nonexistent) SELECT amount FROM orders"
        classified = self._parse_and_classify(sql)

        with pytest.raises(LineageError, match="does not exist in table"):
            self.analyzer.analyze(classified)

    def test_confidence_decrease_after_merge(self):
        """Test confidence decreases after merge."""
        sql = "INSERT INTO t1 SELECT amount FROM new_orders"
        classified = self._parse_and_classify(sql)

        # Record confidence before insert
        t1_before = self.registry.get_table("t1")
        assert t1_before is not None
        confidence_before = t1_before.get_column("total").confidence

        self.analyzer.analyze(classified)

        # Verify confidence decreased
        t1_after = self.registry.get_table("t1")
        assert t1_after is not None
        confidence_after = t1_after.get_column("total").confidence

        assert confidence_after < confidence_before


class TestScriptAnalyzerWithInsert:
    """Tests for ScriptAnalyzer handling INSERT INTO (end-to-end)."""

    def test_create_and_insert(self):
        """Test CREATE + INSERT combination."""
        script = """
        CREATE TABLE t1 AS SELECT amount FROM orders;
        INSERT INTO t1 SELECT amount FROM new_orders;
        """

        schema = DictSchemaProvider(
            {"orders": ["amount"], "new_orders": ["amount"]}
        )

        analyzer = ScriptAnalyzer(schema_provider=schema)
        result = analyzer.analyze_script(script)

        # Verify t1 exists
        t1 = result.get_table("t1")
        assert t1 is not None

        # Verify amount column has two sources
        amount_lineage = t1.get_column("amount")
        assert amount_lineage is not None
        assert len(amount_lineage.sources) == 2

        source_tables = {s.table for s in amount_lineage.sources}
        assert "orders" in source_tables
        assert "new_orders" in source_tables

    def test_multiple_inserts(self):
        """Test multiple INSERT INTO statements."""
        script = """
        CREATE TABLE t1 AS SELECT amount FROM orders;
        INSERT INTO t1 SELECT amount FROM new_orders;
        INSERT INTO t1 SELECT amount FROM additional_orders;
        """

        schema = DictSchemaProvider(
            {
                "orders": ["amount"],
                "new_orders": ["amount"],
                "additional_orders": ["amount"],
            }
        )

        analyzer = ScriptAnalyzer(schema_provider=schema)
        result = analyzer.analyze_script(script)

        # Verify t1.amount has three sources
        t1 = result.get_table("t1")
        assert t1 is not None
        amount_lineage = t1.get_column("amount")
        assert amount_lineage is not None
        assert len(amount_lineage.sources) == 3

    def test_insert_with_expression(self):
        """Test INSERT with expression transformation."""
        script = """
        CREATE TABLE t1 AS SELECT amount + tax AS total FROM orders;
        INSERT INTO t1 SELECT amount * 2 AS total FROM new_orders;
        """

        schema = DictSchemaProvider(
            {"orders": ["amount", "tax"], "new_orders": ["amount"]}
        )

        analyzer = ScriptAnalyzer(schema_provider=schema)
        result = analyzer.analyze_script(script)

        # Verify t1.total has multiple sources
        t1 = result.get_table("t1")
        assert t1 is not None
        total_lineage = t1.get_column("total")
        assert total_lineage is not None
        assert len(total_lineage.sources) >= 2

    def test_insert_with_explicit_columns(self):
        """Test INSERT INTO with explicit column names."""
        script = """
        CREATE TABLE t1 AS SELECT amount AS col1, tax AS col2 FROM orders;
        INSERT INTO t1 (col2, col1) SELECT tax, amount FROM new_orders;
        """

        schema = DictSchemaProvider(
            {"orders": ["amount", "tax"], "new_orders": ["amount", "tax"]}
        )

        analyzer = ScriptAnalyzer(schema_provider=schema)
        result = analyzer.analyze_script(script)

        # Verify columns are matched correctly
        t1 = result.get_table("t1")
        assert t1 is not None

        col1_lineage = t1.get_column("col1")
        assert col1_lineage is not None
        # col1 should have sources from both orders.amount and new_orders.amount
        assert len(col1_lineage.sources) >= 1

        col2_lineage = t1.get_column("col2")
        assert col2_lineage is not None
        # col2 should have sources from both orders.tax and new_orders.tax
        assert len(col2_lineage.sources) >= 1

