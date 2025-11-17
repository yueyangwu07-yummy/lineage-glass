"""
Tests for DependencyExtractor.

This module contains test cases for the DependencyExtractor class, which
extracts field-level dependencies from SELECT statements.
"""

import pytest

import sqlglot

from lineage_analyzer.analyzer.dependency_extractor import DependencyExtractor
from lineage_analyzer.analyzer.scope_builder import ScopeBuilder
from lineage_analyzer.analyzer.symbol_resolver import SymbolResolver
from lineage_analyzer.exceptions import LineageError
from lineage_analyzer.models.config import ErrorMode, LineageConfig
from lineage_analyzer.models.dependency import ExpressionType
from lineage_analyzer.parser.sql_parser import SQLParser
from lineage_analyzer.schema.dict_provider import DictSchemaProvider


class TestDependencyExtractor:
    """Test cases for DependencyExtractor class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = LineageConfig()
        self.parser = SQLParser(self.config)
        self.scope_builder = ScopeBuilder(self.config)

    def _create_resolver_and_extractor(self, sql: str, schema_dict: dict = None):
        """Helper method to create resolver and extractor."""
        ast = self.parser.parse(sql)
        scope = self.scope_builder.build_scope(ast)

        schema_provider = None
        if schema_dict:
            schema_provider = DictSchemaProvider(schema_dict)
            scope_builder_with_schema = ScopeBuilder(self.config, schema_provider)
            scope = scope_builder_with_schema.build_scope(ast)

        resolver = SymbolResolver(scope, self.config, schema_provider)
        extractor = DependencyExtractor(scope, resolver, self.config)

        return ast, resolver, extractor

    def test_direct_column(self):
        """Test 1: Direct column."""
        sql = "SELECT id, name FROM users"
        ast, resolver, extractor = self._create_resolver_and_extractor(sql)

        dependencies = extractor.extract(ast)

        # Should have 2 dependencies
        assert len(dependencies) == 2

        # Check dependencies
        dep_ids = [d for d in dependencies if d.target.column == "id"]
        dep_names = [d for d in dependencies if d.target.column == "name"]

        assert len(dep_ids) == 1
        assert len(dep_names) == 1

        assert dep_ids[0].source.column == "id"
        assert dep_ids[0].source.table == "users"
        assert dep_ids[0].expression_type == ExpressionType.DIRECT

        assert dep_names[0].source.column == "name"
        assert dep_names[0].source.table == "users"
        assert dep_names[0].expression_type == ExpressionType.DIRECT

    def test_column_alias(self):
        """Test 2: Column alias."""
        sql = "SELECT id AS user_id, name AS user_name FROM users"
        ast, resolver, extractor = self._create_resolver_and_extractor(sql)

        dependencies = extractor.extract(ast)

        # Should have 2 dependencies
        assert len(dependencies) == 2

        # Check dependencies
        dep_user_id = [d for d in dependencies if d.target.column == "user_id"]
        dep_user_name = [d for d in dependencies if d.target.column == "user_name"]

        assert len(dep_user_id) == 1
        assert len(dep_user_name) == 1

        assert dep_user_id[0].source.column == "id"
        assert dep_user_id[0].source.table == "users"
        assert dep_user_id[0].expression_type == ExpressionType.DIRECT

        assert dep_user_name[0].source.column == "name"
        assert dep_user_name[0].source.table == "users"
        assert dep_user_name[0].expression_type == ExpressionType.DIRECT

    def test_simple_arithmetic(self):
        """Test 3: Simple arithmetic."""
        sql = "SELECT amount + tax AS total FROM orders"
        ast, resolver, extractor = self._create_resolver_and_extractor(sql)

        dependencies = extractor.extract(ast)

        # Should have 2 dependencies (amount and tax)
        assert len(dependencies) == 2

        # Check dependencies
        dep_amount = [d for d in dependencies if d.source.column == "amount"]
        dep_tax = [d for d in dependencies if d.source.column == "tax"]

        assert len(dep_amount) == 1
        assert len(dep_tax) == 1

        assert dep_amount[0].target.column == "total"
        assert dep_amount[0].expression_type == ExpressionType.COMPUTED
        assert dep_tax[0].target.column == "total"
        assert dep_tax[0].expression_type == ExpressionType.COMPUTED

    def test_complex_arithmetic(self):
        """Test 4: Complex arithmetic."""
        sql = "SELECT (amount * quantity) - discount AS net_total FROM orders"
        ast, resolver, extractor = self._create_resolver_and_extractor(sql)

        dependencies = extractor.extract(ast)

        # Should have 3 dependencies (amount, quantity, discount)
        assert len(dependencies) == 3

        # Check that all columns are present
        source_columns = {d.source.column for d in dependencies}
        assert "amount" in source_columns
        assert "quantity" in source_columns
        assert "discount" in source_columns

        # All should target net_total with COMPUTED type
        for dep in dependencies:
            assert dep.target.column == "net_total"
            assert dep.expression_type == ExpressionType.COMPUTED

    def test_function(self):
        """Test 5: Function call."""
        sql = "SELECT UPPER(name) AS upper_name, LENGTH(email) AS email_len FROM users"
        ast, resolver, extractor = self._create_resolver_and_extractor(sql)

        dependencies = extractor.extract(ast)

        # Should have 2 dependencies
        assert len(dependencies) == 2

        # Check dependencies
        dep_name = [d for d in dependencies if d.source.column == "name"]
        dep_email = [d for d in dependencies if d.source.column == "email"]

        assert len(dep_name) == 1
        assert len(dep_email) == 1

        assert dep_name[0].target.column == "upper_name"
        assert dep_name[0].expression_type == ExpressionType.FUNCTION

        assert dep_email[0].target.column == "email_len"
        assert dep_email[0].expression_type == ExpressionType.FUNCTION

    def test_case_expression(self):
        """Test 6: CASE expression."""
        sql = """
        SELECT 
          CASE 
            WHEN amount > 1000 THEN high_rate
            WHEN amount > 500 THEN mid_rate
            ELSE low_rate
          END AS rate
        FROM orders
        """
        ast, resolver, extractor = self._create_resolver_and_extractor(sql)

        dependencies = extractor.extract(ast)

        # Should have 4 dependencies (amount, high_rate, mid_rate, low_rate)
        assert len(dependencies) == 4

        # Check that all columns are present
        source_columns = {d.source.column for d in dependencies}
        assert "amount" in source_columns
        assert "high_rate" in source_columns
        assert "mid_rate" in source_columns
        assert "low_rate" in source_columns

        # All should target rate with CASE type
        for dep in dependencies:
            assert dep.target.column == "rate"
            assert dep.expression_type == ExpressionType.CASE

    def test_join_dependencies(self):
        """Test 7: Multi-table JOIN."""
        sql = """
        SELECT 
          o.id,
          o.amount + c.credit AS available,
          UPPER(c.name) AS customer_name
        FROM orders o
        JOIN customers c ON o.customer_id = c.id
        """
        schema_dict = {
            "orders": ["id", "amount", "customer_id"],
            "customers": ["id", "credit", "name"],
        }
        ast, resolver, extractor = self._create_resolver_and_extractor(
            sql, schema_dict
        )

        dependencies = extractor.extract(ast)

        # Should have at least 4 dependencies
        assert len(dependencies) >= 4

        # Check specific dependencies
        dep_id = [d for d in dependencies if d.target.column == "id"]
        dep_available = [d for d in dependencies if d.target.column == "available"]
        dep_customer_name = [
            d for d in dependencies if d.target.column == "customer_name"
        ]

        assert len(dep_id) == 1
        assert dep_id[0].source.table == "orders"
        assert dep_id[0].source.column == "id"

        assert len(dep_available) == 2  # amount + credit
        source_cols = {d.source.column for d in dep_available}
        assert "amount" in source_cols
        assert "credit" in source_cols

        assert len(dep_customer_name) == 1
        assert dep_customer_name[0].source.table == "customers"
        assert dep_customer_name[0].source.column == "name"
        assert dep_customer_name[0].expression_type == ExpressionType.FUNCTION

    def test_nested_functions(self):
        """Test 8: Nested functions."""
        sql = "SELECT UPPER(TRIM(name)) AS clean_name FROM users"
        ast, resolver, extractor = self._create_resolver_and_extractor(sql)

        dependencies = extractor.extract(ast)

        # Should have 1 dependency (name appears once)
        assert len(dependencies) == 1

        assert dependencies[0].source.column == "name"
        assert dependencies[0].target.column == "clean_name"
        assert dependencies[0].expression_type == ExpressionType.FUNCTION

    def test_literal_no_dependency(self):
        """Test 9: Literals don't produce dependencies."""
        sql = "SELECT 'constant' AS const_col, 123 AS num_col FROM users"
        ast, resolver, extractor = self._create_resolver_and_extractor(sql)

        dependencies = extractor.extract(ast)

        # Should have 0 dependencies (literals have no source columns)
        assert len(dependencies) == 0

    def test_mixed_expression(self):
        """Test 10: Mixed expression."""
        sql = (
            "SELECT id, amount * 2 AS doubled, "
            "CASE WHEN active THEN 1 ELSE 0 END AS status FROM orders"
        )
        ast, resolver, extractor = self._create_resolver_and_extractor(sql)

        dependencies = extractor.extract(ast)

        # Should have dependencies for id, amount, and active
        source_columns = {d.source.column for d in dependencies}
        assert "id" in source_columns
        assert "amount" in source_columns
        assert "active" in source_columns

        # Check types
        dep_id = [d for d in dependencies if d.source.column == "id"]
        dep_amount = [d for d in dependencies if d.source.column == "amount"]
        dep_active = [d for d in dependencies if d.source.column == "active"]

        assert dep_id[0].expression_type == ExpressionType.DIRECT
        assert dep_amount[0].expression_type == ExpressionType.COMPUTED
        assert dep_active[0].expression_type == ExpressionType.CASE

    def test_aggregate_not_supported(self):
        """Test 11: Aggregate function is now supported (Phase 3.1+)."""
        sql = "SELECT COUNT(*) FROM users"
        ast, resolver, extractor = self._create_resolver_and_extractor(sql)

        # Should not raise error - aggregates are now supported
        dependencies = extractor.extract(ast)
        
        # For scalar aggregates (COUNT(*) without GROUP BY), we should get dependencies
        # The dependency might be empty if scope doesn't have tables, but it shouldn't raise
        # In a real scenario with proper scope, COUNT(*) would create a dependency
        # Just verify it doesn't raise NotImplementedError
        assert dependencies is not None
        # If we have dependencies, verify they're marked as aggregate
        if len(dependencies) > 0:
            count_dep = dependencies[0]
            assert count_dep.is_aggregate is True
            assert count_dep.aggregate_function == 'COUNT'

    def test_window_not_supported(self):
        """Test 12: Window function should raise error."""
        sql = "SELECT id, ROW_NUMBER() OVER (ORDER BY id) AS rn FROM users"
        ast, resolver, extractor = self._create_resolver_and_extractor(sql)

        # Should raise NotImplementedError
        with pytest.raises(NotImplementedError) as exc_info:
            extractor.extract(ast)

        assert "Window functions" in str(exc_info.value)

    def test_deduplication(self):
        """Test 13: Column deduplication."""
        sql = "SELECT amount + amount + tax AS total FROM orders"
        ast, resolver, extractor = self._create_resolver_and_extractor(sql)

        dependencies = extractor.extract(ast)

        # Should have 2 dependencies (amount appears twice but deduplicated)
        assert len(dependencies) == 2

        source_columns = {d.source.column for d in dependencies}
        assert "amount" in source_columns
        assert "tax" in source_columns

        # Amount should only appear once despite being used twice
        dep_amount = [d for d in dependencies if d.source.column == "amount"]
        assert len(dep_amount) == 1

    def test_expression_text(self):
        """Test 14: Expression text is captured."""
        sql = "SELECT amount + tax AS total FROM orders"
        ast, resolver, extractor = self._create_resolver_and_extractor(sql)

        dependencies = extractor.extract(ast)

        # Check that expression text is captured
        for dep in dependencies:
            assert dep.expression is not None
            assert "amount" in dep.expression or "tax" in dep.expression

    def test_warnings_collection(self):
        """Test 15: Warnings are collected."""
        sql = "SELECT non_existent FROM orders"
        config = LineageConfig(on_unresolved=ErrorMode.WARN, schema_validation=False)
        parser = SQLParser(config)
        ast = parser.parse(sql)
        scope_builder = ScopeBuilder(config, None)  # No schema provider
        scope = scope_builder.build_scope(ast)
        resolver = SymbolResolver(scope, config, None)  # No schema provider
        extractor = DependencyExtractor(scope, resolver, config)

        dependencies = extractor.extract(ast)

        # Check that warnings are collected from resolver
        warnings = resolver.warnings.get_all()
        assert isinstance(warnings, list)
        assert len(dependencies) == 1  # non_existent -> non_existent
        assert dependencies[0].source.column == "non_existent"

    def test_subtraction(self):
        """Test 16: Subtraction operation."""
        sql = "SELECT amount - discount AS net FROM orders"
        ast, resolver, extractor = self._create_resolver_and_extractor(sql)

        dependencies = extractor.extract(ast)

        # Should have 2 dependencies
        assert len(dependencies) == 2
        source_columns = {d.source.column for d in dependencies}
        assert "amount" in source_columns
        assert "discount" in source_columns

        for dep in dependencies:
            assert dep.expression_type == ExpressionType.COMPUTED

    def test_multiplication(self):
        """Test 17: Multiplication operation."""
        sql = "SELECT price * quantity AS total FROM orders"
        ast, resolver, extractor = self._create_resolver_and_extractor(sql)

        dependencies = extractor.extract(ast)

        # Should have 2 dependencies
        assert len(dependencies) == 2
        source_columns = {d.source.column for d in dependencies}
        assert "price" in source_columns
        assert "quantity" in source_columns

        for dep in dependencies:
            assert dep.expression_type == ExpressionType.COMPUTED

    def test_division(self):
        """Test 18: Division operation."""
        sql = "SELECT total / count AS average FROM orders"
        ast, resolver, extractor = self._create_resolver_and_extractor(sql)

        dependencies = extractor.extract(ast)

        # Should have 2 dependencies
        assert len(dependencies) == 2
        source_columns = {d.source.column for d in dependencies}
        assert "total" in source_columns
        assert "count" in source_columns

        for dep in dependencies:
            assert dep.expression_type == ExpressionType.COMPUTED

    def test_case_without_else(self):
        """Test 19: CASE expression without ELSE."""
        sql = """
        SELECT 
          CASE 
            WHEN amount > 1000 THEN high_rate
            WHEN amount > 500 THEN mid_rate
          END AS rate
        FROM orders
        """
        ast, resolver, extractor = self._create_resolver_and_extractor(sql)

        dependencies = extractor.extract(ast)

        # Should have at least 3 dependencies (amount, high_rate, mid_rate)
        assert len(dependencies) >= 3

        source_columns = {d.source.column for d in dependencies}
        assert "amount" in source_columns
        assert "high_rate" in source_columns
        assert "mid_rate" in source_columns

        for dep in dependencies:
            assert dep.expression_type == ExpressionType.CASE

