"""
Advanced tests for SymbolResolver enhancements.

This module contains test cases for enhanced SymbolResolver functionality,
including confidence calculation, error messages, SELECT *, and USING clauses.
"""

import pytest

from lineage_analyzer.analyzer.scope_builder import ScopeBuilder
from lineage_analyzer.analyzer.symbol_resolver import SymbolResolver
from lineage_analyzer.exceptions import (
    AmbiguousColumnError,
    SchemaValidationError,
    UnresolvedReferenceError,
)
from lineage_analyzer.models.config import ErrorMode, LineageConfig
from lineage_analyzer.models.table import TableRef
from lineage_analyzer.parser.sql_parser import SQLParser
from lineage_analyzer.schema.dict_provider import DictSchemaProvider


class TestSymbolResolverAdvanced:
    """Advanced test cases for SymbolResolver."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up common components for tests."""
        self.config = LineageConfig()
        self.parser = SQLParser(self.config)
        self.schema_dict = {
            "orders": ["id", "amount", "tax", "customer_id"],
            "customers": ["id", "name", "email", "customer_id"],
        }
        self.schema_provider = DictSchemaProvider(self.schema_dict)

    def _create_resolver(self, sql: str, schema_dict: dict = None, config: LineageConfig = None):
        """Helper to create resolver for a SQL query.
        
        Args:
            sql: SQL query string
            schema_dict: Schema dictionary. If None, uses default schema_dict.
                        To explicitly use no schema, pass an empty dict {}.
            config: LineageConfig. If None, uses default config.
        """
        if config is None:
            config = self.config

        ast = self.parser.parse(sql)
        # Handle schema_dict: None means use default, {} means no schema
        if schema_dict == {}:
            schema_provider = None
        elif schema_dict is None:
            schema_provider = DictSchemaProvider(self.schema_dict)
        else:
            schema_provider = DictSchemaProvider(schema_dict)
        scope_builder = ScopeBuilder(config, schema_provider)
        scope = scope_builder.build_scope(ast)
        resolver = SymbolResolver(scope, config, schema_provider)
        return resolver, scope

    # === Basic Functionality Tests ===

    def test_resolve_with_explicit_prefix(self):
        """Test: Explicit table prefix should always succeed."""
        sql = "SELECT o.id, o.amount FROM orders o"
        resolver, _ = self._create_resolver(sql)

        col_ref, confidence = resolver.resolve_column_with_inference("id", "o")
        assert col_ref.table == "orders"
        assert col_ref.column == "id"
        assert confidence >= 0.95  # Explicit prefix, high confidence

    def test_resolve_single_table_no_prefix(self):
        """Test: Single table without prefix, auto inference."""
        sql = "SELECT id, amount FROM orders"
        resolver, _ = self._create_resolver(sql)

        col_ref, confidence = resolver.resolve_column_with_inference("id")
        assert col_ref.table == "orders"
        assert col_ref.column == "id"
        assert confidence == 1.0  # Single table, high confidence

    # === Ambiguity Handling Tests ===

    def test_ambiguous_column_strict_mode(self):
        """Test: Ambiguous column + strict mode -> raise exception."""
        sql = "SELECT id FROM orders o JOIN customers c ON o.customer_id = c.id"
        config = LineageConfig(strict_mode=True, on_ambiguity=ErrorMode.FAIL)
        resolver, _ = self._create_resolver(sql, config=config)

        with pytest.raises(AmbiguousColumnError) as exc_info:
            resolver.resolve_column_with_inference("id", context=sql)

        error_msg = str(exc_info.value)
        assert "ambiguous" in error_msg.lower()
        assert "orders" in error_msg or "customers" in error_msg

    def test_ambiguous_column_warn_mode(self):
        """Test: Ambiguous column + warn mode -> use first table + warning."""
        sql = "SELECT id FROM orders o JOIN customers c ON o.customer_id = c.id"
        config = LineageConfig(on_ambiguity=ErrorMode.WARN)
        resolver, _ = self._create_resolver(sql, config=config)

        col_ref, confidence = resolver.resolve_column_with_inference("id", context=sql)

        # Should return first table (orders)
        assert col_ref.table == "orders"
        assert col_ref.column == "id"
        assert confidence < 1.0  # Ambiguous, lower confidence

        # Should have warnings
        warnings = resolver.warnings.get_all()
        assert len(warnings) > 0
        assert any("ambiguous" in w.message.lower() for w in warnings)

    def test_ambiguous_with_schema_resolves(self):
        """Test: With schema, ambiguity may be resolved."""
        schema = {
            "orders": ["id", "amount"],
            "customers": ["customer_id", "name"],  # No id
        }
        sql = "SELECT id FROM orders o JOIN customers c ON o.customer_id = c.customer_id"
        resolver, _ = self._create_resolver(sql, schema_dict=schema)

        col_ref, confidence = resolver.resolve_column_with_inference("id")
        assert col_ref.table == "orders"  # Only orders has id
        assert col_ref.column == "id"
        assert confidence == 1.0  # Schema match, high confidence

    # === Schema Validation Tests ===

    def test_column_not_in_schema_validation_on(self):
        """Test: Column not in schema + validation on -> raise exception."""
        schema = {"orders": ["id", "amount"]}
        config = LineageConfig(schema_validation=True)
        sql = "SELECT non_existent FROM orders"
        resolver, _ = self._create_resolver(sql, schema_dict=schema, config=config)

        with pytest.raises(SchemaValidationError):
            resolver.resolve_column_with_inference("non_existent", context=sql)

    def test_column_not_in_schema_validation_off(self):
        """Test: Column not in schema + validation off -> continue + warning."""
        schema = {"orders": ["id", "amount"]}
        config = LineageConfig(schema_validation=False)
        sql = "SELECT non_existent FROM orders"
        resolver, _ = self._create_resolver(sql, schema_dict=schema, config=config)

        col_ref, confidence = resolver.resolve_column_with_inference("non_existent", context=sql)

        assert col_ref.table == "orders"
        assert col_ref.column == "non_existent"
        assert confidence == 0.3  # Schema says column doesn't exist

        # Should have warnings
        warnings = resolver.warnings.get_all()
        assert len(warnings) > 0
        assert any("not found in schema" in w.message.lower() for w in warnings)

    # === Special Syntax Tests ===

    def test_select_star_with_schema(self):
        """Test: SELECT * with schema."""
        schema = {"orders": ["id", "amount", "tax"]}
        config = LineageConfig(expand_wildcards=True)
        sql = "SELECT * FROM orders"
        resolver, _ = self._create_resolver(sql, schema_dict=schema, config=config)

        columns = resolver.resolve_star_column()
        assert len(columns) == 3
        column_names = {col.column for col in columns}
        assert column_names == {"id", "amount", "tax"}

    def test_select_star_without_schema(self):
        """Test: SELECT * without schema -> return empty or error."""
        sql = "SELECT * FROM orders"
        config = LineageConfig(expand_wildcards=True)
        resolver, _ = self._create_resolver(sql, schema_dict={}, config=config)

        # Without schema, resolve_star_column should raise SchemaValidationError
        # if expand_wildcards is True
        with pytest.raises(SchemaValidationError):
            resolver.resolve_star_column()

    def test_select_star_without_schema_no_expand(self):
        """Test: SELECT * without schema and expand_wildcards=False -> return empty."""
        sql = "SELECT * FROM orders"
        config = LineageConfig(expand_wildcards=False)
        resolver, _ = self._create_resolver(sql, schema_dict={}, config=config)

        # Without schema and expand_wildcards=False, should return empty list
        columns = resolver.resolve_star_column()
        assert columns == []

    def test_table_star(self):
        """Test: SELECT table.* syntax."""
        schema = {"orders": ["id", "amount"], "customers": ["id", "name"]}
        sql = "SELECT o.*, c.name FROM orders o JOIN customers c ON o.customer_id = c.id"
        resolver, _ = self._create_resolver(sql, schema_dict=schema)

        columns = resolver.resolve_star_column("o")
        assert len(columns) == 2
        column_names = {col.column for col in columns}
        assert column_names == {"id", "amount"}
        assert all(col.table == "orders" for col in columns)

    def test_join_using_clause(self):
        """Test: JOIN ... USING clause."""
        sql = "SELECT customer_id FROM orders o JOIN customers c USING (customer_id)"
        resolver, _ = self._create_resolver(sql)

        columns = resolver.handle_using_clause(["customer_id"])
        assert "customer_id" in columns
        # Should resolve from first table (orders)
        assert columns["customer_id"].table == "orders"

    # === Error Message Tests ===

    def test_error_message_quality(self):
        """Test: Verify error message quality."""
        sql = "SELECT id FROM orders o JOIN customers c ON o.customer_id = c.id"
        config = LineageConfig(on_ambiguity=ErrorMode.FAIL)
        resolver, _ = self._create_resolver(sql, config=config)

        try:
            resolver.resolve_column_with_inference("id", context=sql)
            pytest.fail("Should have raised AmbiguousColumnError")
        except AmbiguousColumnError as e:
            error_msg = str(e)
            assert "ambiguous" in error_msg.lower()
            assert "orders" in error_msg or "customers" in error_msg

    def test_invalid_table_qualifier(self):
        """Test: Invalid table qualifier."""
        sql = "SELECT x.id FROM orders o"
        resolver, _ = self._create_resolver(sql)

        with pytest.raises(UnresolvedReferenceError) as exc_info:
            resolver.resolve_column_with_inference("id", "x", context=sql)

        error_msg = str(exc_info.value)
        assert "not found" in error_msg.lower()
        assert "x" in error_msg

    # === Confidence Tests ===

    def test_confidence_levels(self):
        """Test: Verify confidence levels for different scenarios."""
        test_cases = [
            # (sql, column, table_qualifier, expected_min_confidence)
            ("SELECT o.id FROM orders o", "id", "o", 0.95),  # Explicit prefix
            ("SELECT id FROM orders", "id", None, 1.0),  # Single table
        ]

        for sql, column, table_qualifier, expected_min in test_cases:
            resolver, _ = self._create_resolver(sql)
            _, confidence = resolver.resolve_column_with_inference(
                column, table_qualifier
            )
            assert confidence >= expected_min, f"Failed for {sql}"

    # === Edge Case Tests ===

    def test_mixed_qualified_unqualified(self):
        """Test: Mixed qualified and unqualified columns."""
        sql = "SELECT o.id, amount FROM orders o"
        resolver, _ = self._create_resolver(sql)

        # Qualified column
        col1, conf1 = resolver.resolve_column_with_inference("id", "o")
        assert col1.table == "orders"
        assert conf1 >= 0.95

        # Unqualified column
        col2, conf2 = resolver.resolve_column_with_inference("amount")
        assert col2.table == "orders"
        assert conf2 >= 0.95  # Single table, high confidence

    def test_warning_collector_methods(self):
        """Test: Warning collector enhanced methods."""
        from lineage_analyzer.utils.warnings import WarningCollector

        collector = WarningCollector()

        # Test add_ambiguity_warning
        collector.add_ambiguity_warning("id", ["orders", "customers"], "orders")
        assert len(collector.get_all()) == 1

        # Test add_schema_missing_warning
        collector.add_schema_missing_warning("non_existent", "orders")
        assert len(collector.get_all()) == 2

        # Test add_inference_warning
        collector.add_inference_warning("id", "orders", 0.6)
        assert len(collector.get_all()) == 3

        # Test get_summary
        summary = collector.get_summary()
        assert summary["WARNING"] >= 2
        assert summary["INFO"] >= 1

    def test_table_resolution_order(self):
        """Test: Table resolution order."""
        sql = "SELECT id FROM orders o JOIN customers c ON o.customer_id = c.id"
        resolver, _ = self._create_resolver(sql)

        order = resolver._get_table_resolution_order()
        assert len(order) >= 2
        assert "orders" in order
        assert "customers" in order
        # orders should come before customers (FROM clause order)
        assert order.index("orders") < order.index("customers")

    def test_calculate_confidence(self):
        """Test: Confidence calculation."""
        sql = "SELECT id FROM orders"
        resolver, _ = self._create_resolver(sql)

        # Test different resolution methods
        confidence_explicit = resolver._calculate_confidence("explicit", True, False)
        assert confidence_explicit == 1.0

        confidence_single = resolver._calculate_confidence("single_table", False, False)
        assert confidence_single == 1.0

        confidence_fallback = resolver._calculate_confidence("first_table", True, False)
        assert confidence_fallback == 0.3

        confidence_ambiguous = resolver._calculate_confidence("first_table", False, True)
        assert confidence_ambiguous == 0.5

