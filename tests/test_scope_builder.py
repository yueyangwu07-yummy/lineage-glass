"""
Tests for ScopeBuilder.

This module contains test cases for the ScopeBuilder class, which
builds Scope objects from SQL AST.
"""

import pytest

import sqlglot

from lineage_analyzer.analyzer.scope_builder import ScopeBuilder
from lineage_analyzer.exceptions import AmbiguousColumnError, LineageError
from lineage_analyzer.models.config import ErrorMode, LineageConfig
from lineage_analyzer.models.table import TableRef
from lineage_analyzer.parser.sql_parser import SQLParser
from lineage_analyzer.schema.dict_provider import DictSchemaProvider


class TestScopeBuilder:
    """Test cases for ScopeBuilder class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = LineageConfig()
        self.parser = SQLParser(self.config)
        self.builder = ScopeBuilder(self.config)

    def test_single_table_no_alias(self):
        """Test 1: Single table without alias."""
        sql = "SELECT id, name FROM users"
        ast = self.parser.parse(sql)
        scope = self.builder.build_scope(ast)

        # Check that users table is registered
        assert "users" in scope.tables
        assert len(scope.tables) == 1

        # Check table reference
        table_ref = scope.resolve_table("users")
        assert table_ref is not None
        assert table_ref.table == "users"
        assert table_ref.alias is None

    def test_single_table_with_alias(self):
        """Test 2: Single table with alias."""
        sql = "SELECT u.id, u.name FROM users u"
        ast = self.parser.parse(sql)
        scope = self.builder.build_scope(ast)

        # Check that both table name and alias are registered
        assert "users" in scope.tables
        assert "u" in scope.tables
        assert len(scope.tables) == 2

        # Check table reference by alias
        table_ref = scope.resolve_table("u")
        assert table_ref is not None
        assert table_ref.table == "users"
        assert table_ref.alias == "u"

        # Check table reference by name
        table_ref = scope.resolve_table("users")
        assert table_ref is not None
        assert table_ref.table == "users"
        assert table_ref.alias == "u"

    def test_two_table_join(self):
        """Test 3: Two tables with JOIN."""
        sql = "SELECT o.id, c.name FROM orders o JOIN customers c ON o.customer_id = c.id"
        ast = self.parser.parse(sql)
        scope = self.builder.build_scope(ast)

        # Check that both tables are registered
        assert "orders" in scope.tables
        assert "o" in scope.tables
        assert "customers" in scope.tables
        assert "c" in scope.tables
        assert len(scope.tables) == 4

        # Check orders table
        orders_ref = scope.resolve_table("o")
        assert orders_ref is not None
        assert orders_ref.table == "orders"
        assert orders_ref.alias == "o"

        # Check customers table
        customers_ref = scope.resolve_table("c")
        assert customers_ref is not None
        assert customers_ref.table == "customers"
        assert customers_ref.alias == "c"

    def test_three_table_join(self):
        """Test 4: Three tables with JOIN."""
        sql = (
            "SELECT o.id, c.name, p.title "
            "FROM orders o "
            "JOIN customers c ON o.cid = c.id "
            "JOIN products p ON o.pid = p.id"
        )
        ast = self.parser.parse(sql)
        scope = self.builder.build_scope(ast)

        # Check that all three tables are registered
        assert "orders" in scope.tables
        assert "o" in scope.tables
        assert "customers" in scope.tables
        assert "c" in scope.tables
        assert "products" in scope.tables
        assert "p" in scope.tables
        assert len(scope.tables) == 6

        # Check orders table
        orders_ref = scope.resolve_table("o")
        assert orders_ref is not None
        assert orders_ref.table == "orders"
        assert orders_ref.alias == "o"

        # Check customers table
        customers_ref = scope.resolve_table("c")
        assert customers_ref is not None
        assert customers_ref.table == "customers"
        assert customers_ref.alias == "c"

        # Check products table
        products_ref = scope.resolve_table("p")
        assert products_ref is not None
        assert products_ref.table == "products"
        assert products_ref.alias == "p"

    def test_table_with_schema(self):
        """Test 5: Table with schema."""
        sql = "SELECT id FROM public.orders"
        ast = self.parser.parse(sql)
        scope = self.builder.build_scope(ast)

        # Check that table is registered
        assert "orders" in scope.tables
        assert len(scope.tables) == 1

        # Check table reference
        table_ref = scope.resolve_table("orders")
        assert table_ref is not None
        assert table_ref.table == "orders"
        assert table_ref.schema == "public"
        assert table_ref.database is None

    def test_table_alias_conflict_fail(self):
        """Test 6: Table alias conflict with FAIL mode."""
        sql = "SELECT * FROM orders o JOIN products o ON o.id = o.id"
        ast = self.parser.parse(sql)

        # Config with FAIL mode for ambiguity
        config = LineageConfig(on_ambiguity=ErrorMode.FAIL)
        builder = ScopeBuilder(config)

        # Should raise AmbiguousColumnError
        with pytest.raises(AmbiguousColumnError) as exc_info:
            builder.build_scope(ast)

        assert "Duplicate table alias" in str(exc_info.value)
        assert exc_info.value.column_name == "o"

    def test_table_alias_conflict_warn(self):
        """Test 7: Table alias conflict with WARN mode."""
        sql = "SELECT * FROM orders o JOIN products o ON o.id = o.id"
        ast = self.parser.parse(sql)

        # Config with WARN mode for ambiguity
        config = LineageConfig(on_ambiguity=ErrorMode.WARN)
        builder = ScopeBuilder(config)

        # Should not raise error, but continue with warning
        scope = builder.build_scope(ast)
        assert len(scope.tables) > 0

    def test_table_alias_conflict_ignore(self):
        """Test 8: Table alias conflict with IGNORE mode."""
        sql = "SELECT * FROM orders o JOIN products o ON o.id = o.id"
        ast = self.parser.parse(sql)

        # Config with IGNORE mode for ambiguity
        config = LineageConfig(on_ambiguity=ErrorMode.IGNORE)
        builder = ScopeBuilder(config)

        # Should not raise error
        scope = builder.build_scope(ast)
        assert len(scope.tables) > 0

    def test_table_with_schema_provider(self):
        """Test 9: Table with schema provider."""
        sql = "SELECT id, name FROM users"
        ast = self.parser.parse(sql)

        # Create schema provider
        schema_dict = {
            "users": ["id", "name", "email"],
        }
        schema_provider = DictSchemaProvider(schema_dict)

        # Build scope with schema provider
        builder = ScopeBuilder(self.config, schema_provider)
        scope = builder.build_scope(ast)

        # Check that columns are registered
        assert "id" in scope.columns
        assert "name" in scope.columns
        assert "email" in scope.columns

        # Check column references
        id_cols = scope.find_column("id")
        assert len(id_cols) == 1
        assert id_cols[0].table == "users"
        assert id_cols[0].column == "id"

    def test_table_with_schema_and_alias(self):
        """Test 10: Table with schema and alias."""
        sql = "SELECT id FROM public.orders o"
        ast = self.parser.parse(sql)
        scope = self.builder.build_scope(ast)

        # Check that both table name and alias are registered
        assert "orders" in scope.tables
        assert "o" in scope.tables
        assert len(scope.tables) == 2

        # Check table reference by alias
        table_ref = scope.resolve_table("o")
        assert table_ref is not None
        assert table_ref.table == "orders"
        assert table_ref.schema == "public"
        assert table_ref.alias == "o"

    def test_no_from_clause(self):
        """Test 11: SELECT without FROM clause."""
        sql = "SELECT 1, 2, 3"
        ast = self.parser.parse(sql)
        scope = self.builder.build_scope(ast)

        # Should have no tables
        assert len(scope.tables) == 0

    def test_invalid_sql(self):
        """Test 12: Invalid SQL should raise error."""
        config = LineageConfig()
        parser = SQLParser(config)

        # Invalid SQL
        sql = "SELECT * FROM"
        with pytest.raises(LineageError):
            parser.parse(sql)

    def test_non_select_statement(self):
        """Test 13: Non-SELECT statement should raise error."""
        config = LineageConfig()
        parser = SQLParser(config)

        # Non-SELECT SQL
        sql = "INSERT INTO users VALUES (1, 'test')"
        with pytest.raises(NotImplementedError):
            parser.parse(sql)

    def test_join_with_as_keyword(self):
        """Test 14: JOIN with AS keyword."""
        sql = "SELECT o.id FROM orders AS o JOIN customers AS c ON o.id = c.id"
        ast = self.parser.parse(sql)
        scope = self.builder.build_scope(ast)

        # Check that both tables are registered
        assert "orders" in scope.tables
        assert "o" in scope.tables
        assert "customers" in scope.tables
        assert "c" in scope.tables

        # Check table references
        orders_ref = scope.resolve_table("o")
        assert orders_ref is not None
        assert orders_ref.table == "orders"
        assert orders_ref.alias == "o"

        customers_ref = scope.resolve_table("c")
        assert customers_ref is not None
        assert customers_ref.table == "customers"
        assert customers_ref.alias == "c"

