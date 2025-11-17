"""
Tests for Statement Classifier system.

This module contains tests for StatementType, ClassifiedStatement,
StatementClassifier, and ScriptSplitter.
"""

import pytest
import sqlglot

from lineage_analyzer.exceptions import LineageError
from lineage_analyzer.models.classified_statement import ClassifiedStatement
from lineage_analyzer.models.statement_type import StatementType
from lineage_analyzer.parser.script_splitter import ScriptSplitter
from lineage_analyzer.parser.statement_classifier import StatementClassifier


class TestStatementType:
    """Tests for StatementType enum."""

    def test_is_supported(self):
        """Test is_supported method."""
        assert StatementType.SELECT.is_supported()
        assert StatementType.CREATE_TABLE_AS.is_supported()
        assert StatementType.INSERT_INTO_SELECT.is_supported()
        assert StatementType.CREATE_VIEW.is_supported()
        assert StatementType.CREATE_TEMP_TABLE.is_supported()
        assert StatementType.WITH_CTE.is_supported()
        assert not StatementType.UPDATE.is_supported()
        assert not StatementType.UNKNOWN.is_supported()
        assert not StatementType.CREATE_TABLE.is_supported()

    def test_creates_table(self):
        """Test creates_table method."""
        assert StatementType.CREATE_TABLE_AS.creates_table()
        assert StatementType.CREATE_TABLE.creates_table()
        assert StatementType.CREATE_TEMP_TABLE.creates_table()
        assert not StatementType.SELECT.creates_table()
        assert not StatementType.CREATE_VIEW.creates_table()

    def test_creates_view(self):
        """Test creates_view method."""
        assert StatementType.CREATE_VIEW.creates_view()
        assert not StatementType.CREATE_TABLE_AS.creates_view()
        assert not StatementType.SELECT.creates_view()

    def test_modifies_data(self):
        """Test modifies_data method."""
        assert StatementType.INSERT_INTO_SELECT.modifies_data()
        assert StatementType.UPDATE.modifies_data()
        assert StatementType.DELETE.modifies_data()
        assert StatementType.TRUNCATE.modifies_data()
        assert not StatementType.SELECT.modifies_data()
        assert not StatementType.CREATE_TABLE_AS.modifies_data()


class TestStatementClassifier:
    """Tests for StatementClassifier."""

    def setup_method(self):
        """Initialize before each test."""
        self.classifier = StatementClassifier()

    def _parse_and_classify(self, sql: str):
        """Helper method: parse and classify SQL."""
        ast = sqlglot.parse_one(sql)
        return self.classifier.classify(ast, sql)

    def test_classify_select(self):
        """Test classifying SELECT statement."""
        sql = "SELECT id, name FROM users"
        classified = self._parse_and_classify(sql)

        assert classified.statement_type == StatementType.SELECT
        assert classified.is_supported()
        assert classified.has_query()
        assert classified.query_ast is not None

    def test_classify_create_table_as(self):
        """Test classifying CREATE TABLE AS."""
        sql = "CREATE TABLE t1 AS SELECT id, name FROM users"
        classified = self._parse_and_classify(sql)

        assert classified.statement_type == StatementType.CREATE_TABLE_AS
        assert classified.is_supported()
        assert classified.target_table == "t1"
        assert classified.has_query()
        assert not classified.is_temporary

    def test_classify_create_temp_table(self):
        """Test classifying CREATE TEMPORARY TABLE."""
        sql = "CREATE TEMPORARY TABLE tmp AS SELECT * FROM users"
        classified = self._parse_and_classify(sql)

        assert classified.statement_type == StatementType.CREATE_TEMP_TABLE
        assert classified.is_supported()
        assert classified.target_table == "tmp"
        assert classified.is_temporary

    def test_classify_create_view(self):
        """Test classifying CREATE VIEW."""
        sql = "CREATE VIEW v1 AS SELECT id FROM users"
        classified = self._parse_and_classify(sql)

        assert classified.statement_type == StatementType.CREATE_VIEW
        assert classified.is_supported()
        assert classified.target_table == "v1"
        assert classified.has_query()

    def test_classify_insert_into_select(self):
        """Test classifying INSERT INTO SELECT."""
        sql = "INSERT INTO t1 SELECT id, name FROM users"
        classified = self._parse_and_classify(sql)

        assert classified.statement_type == StatementType.INSERT_INTO_SELECT
        assert classified.is_supported()
        assert classified.target_table == "t1"
        assert classified.has_query()

    def test_classify_insert_into_values(self):
        """Test classifying INSERT INTO VALUES (not supported)."""
        sql = "INSERT INTO t1 VALUES (1, 'test')"
        classified = self._parse_and_classify(sql)

        assert classified.statement_type == StatementType.UNSUPPORTED
        assert not classified.is_supported()

    def test_classify_with_cte(self):
        """Test classifying WITH CTE."""
        sql = "WITH cte AS (SELECT * FROM users) SELECT * FROM cte"
        classified = self._parse_and_classify(sql)

        assert classified.statement_type == StatementType.WITH_CTE
        assert classified.is_supported()
        assert classified.has_query()

    def test_classify_drop_table(self):
        """Test classifying DROP TABLE."""
        sql = "DROP TABLE t1"
        classified = self._parse_and_classify(sql)

        assert classified.statement_type == StatementType.DROP_TABLE
        assert classified.target_table == "t1"
        assert not classified.is_supported()

    def test_classify_update(self):
        """Test classifying UPDATE (not supported)."""
        sql = "UPDATE users SET name = 'test' WHERE id = 1"
        classified = self._parse_and_classify(sql)

        assert classified.statement_type == StatementType.UPDATE
        assert not classified.is_supported()

    def test_classify_create_table_without_as(self):
        """Test classifying pure CREATE TABLE (no AS SELECT)."""
        sql = "CREATE TABLE t1 (id INT, name VARCHAR(100))"
        classified = self._parse_and_classify(sql)

        assert classified.statement_type == StatementType.CREATE_TABLE
        assert classified.target_table == "t1"
        assert not classified.has_query()

    def test_classify_table_with_schema(self):
        """Test classifying table with schema prefix."""
        sql = "CREATE TABLE schema.t1 AS SELECT * FROM users"
        classified = self._parse_and_classify(sql)

        assert classified.statement_type == StatementType.CREATE_TABLE_AS
        assert "schema" in classified.target_table or "t1" in classified.target_table

    def test_statement_index(self):
        """Test statement_index is preserved."""
        sql = "SELECT * FROM users"
        classified = self._parse_and_classify(sql)

        assert classified.statement_index == 0

        # Test with custom index
        ast = sqlglot.parse_one(sql)
        classified = self.classifier.classify(ast, sql, statement_index=5)
        assert classified.statement_index == 5


class TestScriptSplitter:
    """Tests for ScriptSplitter."""

    def setup_method(self):
        """Initialize before each test."""
        self.splitter = ScriptSplitter()

    def test_split_single_statement(self):
        """Test splitting single statement."""
        script = "SELECT * FROM users"
        statements = self.splitter.split(script)

        assert len(statements) == 1
        ast, sql = statements[0]
        assert isinstance(ast, sqlglot.expressions.Select)

    def test_split_multiple_statements(self):
        """Test splitting multiple statements."""
        script = """
        SELECT * FROM users;
        SELECT * FROM orders;
        SELECT * FROM products;
        """
        statements = self.splitter.split(script)

        assert len(statements) == 3
        for ast, sql in statements:
            assert isinstance(ast, sqlglot.expressions.Select)

    def test_split_mixed_statements(self):
        """Test splitting mixed statement types."""
        script = """
        CREATE TABLE t1 AS SELECT * FROM users;
        INSERT INTO t1 SELECT * FROM new_users;
        SELECT * FROM t1;
        """
        statements = self.splitter.split(script)

        assert len(statements) == 3

        # Verify types
        assert isinstance(statements[0][0], sqlglot.expressions.Create)
        assert isinstance(statements[1][0], sqlglot.expressions.Insert)
        assert isinstance(statements[2][0], sqlglot.expressions.Select)

    def test_split_empty_script(self):
        """Test splitting empty script."""
        # sqlglot.parse() returns empty list for empty string, not an error
        # So we check that it raises LineageError
        with pytest.raises(LineageError):
            self.splitter.split("")

    def test_split_with_comments(self):
        """Test splitting script with comments."""
        script = """
        -- This is a comment
        SELECT * FROM users;
        /* Multi-line
           comment */
        SELECT * FROM orders;
        """
        statements = self.splitter.split(script)

        # Comments are automatically ignored by sqlglot
        assert len(statements) == 2

    def test_split_preserving_original(self):
        """Test split_preserving_original method."""
        script = "SELECT * FROM users; SELECT * FROM orders;"
        statements = self.splitter.split_preserving_original(script)

        assert len(statements) == 2
        for ast, sql in statements:
            assert isinstance(ast, sqlglot.expressions.Select)
            assert len(sql) > 0

