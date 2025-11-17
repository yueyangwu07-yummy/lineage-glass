"""
Tests for CREATE TABLE AS analyzer.

This module contains tests for CreateTableAnalyzer and ScriptAnalyzer.
"""

import pytest
import sqlglot

from lineage_analyzer import (
    ColumnRef,
    DictSchemaProvider,
    ExpressionType,
    LineageConfig,
    LineageError,
    StatementClassifier,
    StatementType,
    TableRegistry,
    TableType,
)
from lineage_analyzer.analyzer.create_table_analyzer import CreateTableAnalyzer
from lineage_analyzer.analyzer.script_analyzer import ScriptAnalyzer


class TestCreateTableAnalyzer:
    """Tests for CreateTableAnalyzer."""

    def setup_method(self):
        """Initialize before each test."""
        self.config = LineageConfig()
        self.registry = TableRegistry()

        # Register source tables
        self.registry.register_source_table(
            "orders", ["id", "user_id", "amount", "tax"]
        )
        self.registry.register_source_table("users", ["id", "name", "email"])

        self.analyzer = CreateTableAnalyzer(self.registry, self.config)
        self.classifier = StatementClassifier()

    def _parse_and_classify(self, sql: str):
        """Helper method."""
        ast = sqlglot.parse_one(sql)
        return self.classifier.classify(ast, sql)

    def test_simple_create_table_as(self):
        """Test simple CREATE TABLE AS."""
        sql = "CREATE TABLE t1 AS SELECT id, user_id FROM orders"
        classified = self._parse_and_classify(sql)

        table_def = self.analyzer.analyze(classified)

        # Verify table definition
        assert table_def.name == "t1"
        assert table_def.table_type == TableType.TABLE
        assert not table_def.is_source_table

        # Verify columns
        assert table_def.has_column("id")
        assert table_def.has_column("user_id")

        # Verify lineage
        id_lineage = table_def.get_column("id")
        assert id_lineage is not None
        assert len(id_lineage.sources) == 1
        assert id_lineage.sources[0].table == "orders"
        assert id_lineage.sources[0].column == "id"

    def test_create_table_with_expression(self):
        """Test CREATE TABLE AS with expression."""
        sql = "CREATE TABLE t1 AS SELECT amount + tax AS total FROM orders"
        classified = self._parse_and_classify(sql)

        table_def = self.analyzer.analyze(classified)

        # Verify total column
        assert table_def.has_column("total")
        total_lineage = table_def.get_column("total")
        assert total_lineage is not None

        # total comes from two source columns
        assert len(total_lineage.sources) == 2
        source_columns = {s.column for s in total_lineage.sources}
        assert "amount" in source_columns
        assert "tax" in source_columns

        # Verify expression type
        assert total_lineage.expression_type == ExpressionType.COMPUTED

    def test_create_temp_table(self):
        """Test CREATE TEMPORARY TABLE."""
        sql = "CREATE TEMPORARY TABLE tmp AS SELECT id FROM users"
        classified = self._parse_and_classify(sql)

        table_def = self.analyzer.analyze(classified)

        assert table_def.name == "tmp"
        assert table_def.table_type == TableType.TEMP_TABLE
        assert classified.is_temporary

    def test_create_table_with_join(self):
        """Test CREATE TABLE AS with JOIN."""
        sql = """
        CREATE TABLE user_orders AS
        SELECT 
            u.name,
            o.amount
        FROM users u
        JOIN orders o ON u.id = o.user_id
        """
        classified = self._parse_and_classify(sql)

        table_def = self.analyzer.analyze(classified)

        # Verify columns
        assert table_def.has_column("name")
        assert table_def.has_column("amount")

        # Verify lineage
        name_lineage = table_def.get_column("name")
        assert name_lineage is not None
        assert len(name_lineage.sources) == 1
        assert name_lineage.sources[0].table == "users"

        amount_lineage = table_def.get_column("amount")
        assert amount_lineage is not None
        assert len(amount_lineage.sources) == 1
        assert amount_lineage.sources[0].table == "orders"

    def test_table_registered_in_registry(self):
        """Test that table is correctly registered in Registry."""
        sql = "CREATE TABLE t1 AS SELECT id FROM orders"
        classified = self._parse_and_classify(sql)

        self.analyzer.analyze(classified)

        # Verify Registry has this table
        assert self.registry.has_table("t1")
        retrieved = self.registry.get_table("t1")
        assert retrieved is not None
        assert retrieved.name == "t1"

    def test_invalid_statement_type_raises_error(self):
        """Test that invalid statement type raises error."""
        sql = "SELECT id FROM orders"
        classified = self._parse_and_classify(sql)

        with pytest.raises(LineageError, match="only handles table/view creation"):
            self.analyzer.analyze(classified)


class TestScriptAnalyzer:
    """Tests for ScriptAnalyzer (end-to-end)."""

    def test_single_create_table(self):
        """Test single CREATE TABLE AS."""
        script = "CREATE TABLE t1 AS SELECT id, amount FROM orders"

        # Provide schema
        schema = DictSchemaProvider({"orders": ["id", "amount", "tax"]})
        analyzer = ScriptAnalyzer(schema_provider=schema)

        result = analyzer.analyze_script(script)

        # Verify result
        assert len(result.get_all_tables()) >= 1  # At least t1

        t1 = result.get_table("t1")
        assert t1 is not None
        assert t1.has_column("id")
        assert t1.has_column("amount")

    def test_multiple_create_tables(self):
        """Test multiple CREATE TABLE AS (chained dependencies)."""
        script = """
        CREATE TABLE t1 AS SELECT id, amount FROM orders;
        CREATE TABLE t2 AS SELECT id, amount * 2 AS doubled FROM t1;
        """

        schema = DictSchemaProvider({"orders": ["id", "amount"]})
        analyzer = ScriptAnalyzer(schema_provider=schema)

        result = analyzer.analyze_script(script)

        # Verify both tables are created
        assert result.get_table("t1") is not None
        assert result.get_table("t2") is not None

        # Verify t2 lineage (should trace back to t1)
        t2 = result.get_table("t2")
        assert t2 is not None
        doubled_lineage = t2.get_column("doubled")
        assert doubled_lineage is not None

        # doubled comes from t1.amount
        assert len(doubled_lineage.sources) == 1
        assert doubled_lineage.sources[0].table == "t1"
        assert doubled_lineage.sources[0].column == "amount"

    def test_mixed_statements(self):
        """Test mixed statements (CREATE + SELECT)."""
        script = """
        CREATE TABLE t1 AS SELECT id FROM orders;
        SELECT * FROM t1;
        """

        schema = DictSchemaProvider({"orders": ["id", "amount"]})
        analyzer = ScriptAnalyzer(schema_provider=schema)

        result = analyzer.analyze_script(script)

        # Verify t1 is created
        assert result.get_table("t1") is not None

        # Verify both statements are processed
        assert len(result.statements) == 2
        assert result.statements[0].statement_type == StatementType.CREATE_TABLE_AS
        assert result.statements[1].statement_type == StatementType.SELECT

    def test_create_view(self):
        """Test CREATE VIEW."""
        script = "CREATE VIEW v1 AS SELECT id, name FROM users"

        schema = DictSchemaProvider({"users": ["id", "name", "email"]})
        analyzer = ScriptAnalyzer(schema_provider=schema)

        result = analyzer.analyze_script(script)

        # Verify view is created (stored as table in registry)
        view = result.get_table("v1")
        assert view is not None
        assert view.has_column("id")
        assert view.has_column("name")

