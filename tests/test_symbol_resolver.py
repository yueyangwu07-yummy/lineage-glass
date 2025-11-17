"""
Tests for SymbolResolver.

This module contains test cases for the SymbolResolver class, which
resolves column references to fully qualified table.column form.
"""

import pytest

import sqlglot

from lineage_analyzer.analyzer.scope_builder import ScopeBuilder
from lineage_analyzer.analyzer.symbol_resolver import SymbolResolver
from lineage_analyzer.exceptions import (
    AmbiguousColumnError,
    SchemaValidationError,
    UnresolvedReferenceError,
)
from lineage_analyzer.models.column import ColumnRef
from lineage_analyzer.models.config import ErrorMode, LineageConfig
from lineage_analyzer.models.table import TableRef
from lineage_analyzer.parser.sql_parser import SQLParser
from lineage_analyzer.schema.dict_provider import DictSchemaProvider


class TestSymbolResolver:
    """Test cases for SymbolResolver class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = LineageConfig()
        self.parser = SQLParser(self.config)
        self.scope_builder = ScopeBuilder(self.config)

    def test_resolve_column_with_table_prefix_alias(self):
        """Test 1: Column with table prefix (alias)."""
        sql = "SELECT o.id FROM orders o"
        ast = self.parser.parse(sql)
        scope = self.scope_builder.build_scope(ast)
        resolver = SymbolResolver(scope, self.config)

        # Resolve column with table prefix
        column_ref = resolver.resolve_column("id", "o")

        # Verify result
        assert column_ref.table == "orders"
        assert column_ref.column == "id"
        assert column_ref.database is None
        assert column_ref.schema is None

    def test_resolve_column_without_table_prefix_single_table(self):
        """Test 2: Column without table prefix, single table."""
        sql = "SELECT id FROM orders"
        ast = self.parser.parse(sql)
        scope = self.scope_builder.build_scope(ast)
        resolver = SymbolResolver(scope, self.config)

        # Resolve column without table prefix
        column_ref = resolver.resolve_column("id")

        # Verify result
        assert column_ref.table == "orders"
        assert column_ref.column == "id"

    def test_resolve_column_without_table_prefix_multiple_tables_with_schema(
        self,
    ):
        """Test 3: Column without table prefix, multiple tables, with schema."""
        sql = (
            "SELECT customer_id FROM orders o "
            "JOIN customers c ON o.cid = c.id"
        )
        ast = self.parser.parse(sql)
        scope = self.scope_builder.build_scope(ast)

        # Create schema provider
        schema_dict = {
            "orders": ["id", "customer_id", "amount"],
            "customers": ["id", "name"],
        }
        schema_provider = DictSchemaProvider(schema_dict)

        # Create resolver with schema
        resolver = SymbolResolver(scope, self.config, schema_provider)

        # Resolve column without table prefix
        column_ref = resolver.resolve_column("customer_id")

        # Verify result - should resolve to orders table
        assert column_ref.table == "orders"
        assert column_ref.column == "customer_id"

    def test_resolve_column_ambiguous_strict_mode(self):
        """Test 4: Ambiguous column name, strict_mode=True."""
        sql = "SELECT id FROM orders o JOIN customers c ON o.cid = c.id"
        ast = self.parser.parse(sql)
        scope = self.scope_builder.build_scope(ast)

        # Create schema provider
        schema_dict = {
            "orders": ["id", "amount"],
            "customers": ["id", "name"],
        }
        schema_provider = DictSchemaProvider(schema_dict)

        # Create resolver with schema and strict mode
        config = LineageConfig(strict_mode=True, on_ambiguity=ErrorMode.FAIL)
        resolver = SymbolResolver(scope, config, schema_provider)

        # Resolve column without table prefix - should raise error
        with pytest.raises(AmbiguousColumnError) as exc_info:
            resolver.resolve_column("id")

        assert "ambiguous" in str(exc_info.value).lower()
        assert exc_info.value.column_name == "id"

    def test_resolve_column_ambiguous_warn_mode(self):
        """Test 5: Ambiguous column name, on_ambiguity=WARN."""
        sql = "SELECT id FROM orders o JOIN customers c ON o.cid = c.id"
        ast = self.parser.parse(sql)
        scope = self.scope_builder.build_scope(ast)

        # Create schema provider
        schema_dict = {
            "orders": ["id", "amount"],
            "customers": ["id", "name"],
        }
        schema_provider = DictSchemaProvider(schema_dict)

        # Create resolver with schema and WARN mode
        config = LineageConfig(on_ambiguity=ErrorMode.WARN)
        resolver = SymbolResolver(scope, config, schema_provider)

        # Resolve column without table prefix
        column_ref = resolver.resolve_column("id")

        # Verify result - should use first table
        assert column_ref.table in ["orders", "customers"]
        assert column_ref.column == "id"

        # Verify warning was added
        warnings = resolver.warnings.get_by_level("WARNING")
        assert len(warnings) > 0
        assert "ambiguous" in warnings[0].message.lower()

    def test_resolve_column_invalid_table_prefix(self):
        """Test 6: Invalid table prefix."""
        sql = "SELECT x.id FROM orders o"
        ast = self.parser.parse(sql)
        scope = self.scope_builder.build_scope(ast)
        resolver = SymbolResolver(scope, self.config)

        # Resolve column with invalid table prefix - should raise error
        with pytest.raises(UnresolvedReferenceError) as exc_info:
            resolver.resolve_column("id", "x")

        assert "not found" in str(exc_info.value).lower()
        assert exc_info.value.reference == "x"

    def test_resolve_column_schema_validation_failed(self):
        """Test 7: Schema validation failed."""
        sql = "SELECT non_existent FROM orders"
        ast = self.parser.parse(sql)
        scope = self.scope_builder.build_scope(ast)

        # Create schema provider
        schema_dict = {
            "orders": ["id", "amount"],
        }
        schema_provider = DictSchemaProvider(schema_dict)

        # Create resolver with schema validation enabled
        config = LineageConfig(schema_validation=True)
        resolver = SymbolResolver(scope, config, schema_provider)

        # Resolve column without table prefix - should raise error
        with pytest.raises(SchemaValidationError) as exc_info:
            resolver.resolve_column("non_existent")

        assert "does not exist" in str(exc_info.value).lower()
        assert exc_info.value.column_name == "non_existent"

    def test_resolve_column_from_ast_node(self):
        """Test 8: Resolve column from AST node."""
        sql = "SELECT o.id FROM orders o"
        ast = self.parser.parse(sql)
        scope = self.scope_builder.build_scope(ast)
        resolver = SymbolResolver(scope, self.config)

        # Get column node from AST
        column_node = ast.expressions[0]

        # Resolve column from AST node
        column_ref = resolver.resolve_column_from_ast_node(column_node)

        # Verify result
        assert column_ref.table == "orders"
        assert column_ref.column == "id"

    def test_resolve_column_require_table_prefix(self):
        """Test 9: Require table prefix."""
        sql = "SELECT id FROM orders"
        ast = self.parser.parse(sql)
        scope = self.scope_builder.build_scope(ast)

        # Create resolver with require_table_prefix=True
        config = LineageConfig(require_table_prefix=True)
        resolver = SymbolResolver(scope, config)

        # Resolve column without table prefix - should raise error
        with pytest.raises(AmbiguousColumnError) as exc_info:
            resolver.resolve_column("id")

        assert "requires a table prefix" in str(exc_info.value).lower()
        assert exc_info.value.column_name == "id"

    def test_resolve_column_ignore_mode(self):
        """Test 10: Ambiguous column name, on_ambiguity=IGNORE."""
        sql = "SELECT id FROM orders o JOIN customers c ON o.cid = c.id"
        ast = self.parser.parse(sql)
        scope = self.scope_builder.build_scope(ast)

        # Create schema provider
        schema_dict = {
            "orders": ["id", "amount"],
            "customers": ["id", "name"],
        }
        schema_provider = DictSchemaProvider(schema_dict)

        # Create resolver with schema and IGNORE mode
        config = LineageConfig(on_ambiguity=ErrorMode.IGNORE)
        resolver = SymbolResolver(scope, config, schema_provider)

        # Resolve column without table prefix
        column_ref = resolver.resolve_column("id")

        # Verify result - should use first table
        assert column_ref.table in ["orders", "customers"]
        assert column_ref.column == "id"

        # Verify no warnings were added
        warnings = resolver.warnings.get_by_level("WARNING")
        assert len(warnings) == 0

    def test_resolve_column_with_schema_and_alias(self):
        """Test 11: Column with schema and alias."""
        sql = "SELECT id FROM public.orders o"
        ast = self.parser.parse(sql)
        scope = self.scope_builder.build_scope(ast)
        resolver = SymbolResolver(scope, self.config)

        # Resolve column with table prefix
        column_ref = resolver.resolve_column("id", "o")

        # Verify result
        assert column_ref.table == "orders"
        assert column_ref.schema == "public"
        assert column_ref.column == "id"

    def test_resolve_column_multiple_tables_no_schema(self):
        """Test 12: Multiple tables, no schema."""
        sql = "SELECT id FROM orders o JOIN customers c ON o.cid = c.id"
        ast = self.parser.parse(sql)
        scope = self.scope_builder.build_scope(ast)

        # Create resolver without schema
        config = LineageConfig(on_ambiguity=ErrorMode.FAIL)
        resolver = SymbolResolver(scope, config)

        # Resolve column without table prefix - should raise error
        with pytest.raises(AmbiguousColumnError) as exc_info:
            resolver.resolve_column("id")

        assert "ambiguous" in str(exc_info.value).lower()
        assert exc_info.value.column_name == "id"

    def test_resolve_column_schema_validation_disabled(self):
        """Test 13: Schema validation disabled."""
        sql = "SELECT non_existent FROM orders"
        ast = self.parser.parse(sql)
        scope = self.scope_builder.build_scope(ast)

        # Create schema provider
        schema_dict = {
            "orders": ["id", "amount"],
        }
        schema_provider = DictSchemaProvider(schema_dict)

        # Create resolver with schema validation disabled
        config = LineageConfig(schema_validation=False)
        resolver = SymbolResolver(scope, config, schema_provider)

        # Resolve column without table prefix - should not raise error
        column_ref = resolver.resolve_column("non_existent")

        # Verify result - should use orders table
        assert column_ref.table == "orders"
        assert column_ref.column == "non_existent"

        # Verify warning was added
        warnings = resolver.warnings.get_by_level("WARNING")
        assert len(warnings) > 0
        assert "not found in schema" in warnings[0].message.lower()

    def test_resolve_column_table_name_not_alias(self):
        """Test 14: Table name instead of alias."""
        sql = "SELECT orders.id FROM orders"
        ast = self.parser.parse(sql)
        scope = self.scope_builder.build_scope(ast)
        resolver = SymbolResolver(scope, self.config)

        # Resolve column with table name (not alias)
        column_ref = resolver.resolve_column("id", "orders")

        # Verify result
        assert column_ref.table == "orders"
        assert column_ref.column == "id"

    def test_warning_collector(self):
        """Test 15: Warning collector functionality."""
        from lineage_analyzer.utils.warnings import WarningCollector

        collector = WarningCollector()

        # Add warnings
        collector.add("WARNING", "Test warning")
        collector.add("ERROR", "Test error")
        collector.add("INFO", "Test info")

        # Verify warnings
        assert len(collector.get_all()) == 3
        assert collector.has_errors() is True

        # Verify warnings by level
        warnings = collector.get_by_level("WARNING")
        assert len(warnings) == 1
        assert warnings[0].message == "Test warning"

        errors = collector.get_by_level("ERROR")
        assert len(errors) == 1
        assert errors[0].message == "Test error"

        # Clear warnings
        collector.clear()
        assert len(collector.get_all()) == 0
        assert collector.has_errors() is False

