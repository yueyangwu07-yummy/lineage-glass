"""
Edge cases and error handling tests.

This module contains tests for edge cases and error handling scenarios.
"""

import pytest

from lineage_analyzer import DictSchemaProvider, LineageError, ScriptAnalyzer


class TestEdgeCases:
    """Edge case tests."""

    def test_empty_script(self):
        """Test empty script."""
        analyzer = ScriptAnalyzer()

        with pytest.raises(Exception):  # Should raise error
            analyzer.analyze_script("")

    def test_invalid_sql(self):
        """Test invalid SQL."""
        analyzer = ScriptAnalyzer()

        with pytest.raises(Exception):
            analyzer.analyze_script("INVALID SQL SYNTAX;")

    def test_table_name_case_sensitivity(self):
        """Test table name case sensitivity."""
        script = """
        CREATE TABLE MyTable AS SELECT val FROM source;
        CREATE TABLE another AS SELECT val FROM MYTABLE;
        """

        schema = DictSchemaProvider({"source": ["val"]})
        analyzer = ScriptAnalyzer(schema_provider=schema)
        result = analyzer.analyze_script(script)

        # Table names should be case-insensitive (normalized to lowercase)
        assert result.get_table("mytable") is not None
        assert result.get_table("MYTABLE") is not None
        assert result.get_table("MyTable") is not None

    def test_missing_source_table(self):
        """Test missing source table."""
        script = """
        CREATE TABLE t1 AS SELECT amount FROM nonexistent_table;
        """

        analyzer = ScriptAnalyzer()
        # Should handle gracefully (may warn or error depending on config)
        result = analyzer.analyze_script(script)

        # Table should still be created (with warnings)
        t1 = result.get_table("t1")
        assert t1 is not None

    def test_duplicate_table_creation(self):
        """Test duplicate table creation."""
        script = """
        CREATE TABLE t1 AS SELECT val FROM source;
        CREATE TABLE t1 AS SELECT val FROM source;
        """

        schema = DictSchemaProvider({"source": ["val"]})
        analyzer = ScriptAnalyzer(schema_provider=schema)
        result = analyzer.analyze_script(script)

        # Should handle duplicate (may warn)
        t1 = result.get_table("t1")
        assert t1 is not None

    def test_insert_into_nonexistent_table(self):
        """Test INSERT INTO nonexistent table."""
        script = """
        INSERT INTO nonexistent_table SELECT val FROM source;
        """

        schema = DictSchemaProvider({"source": ["val"]})
        analyzer = ScriptAnalyzer(schema_provider=schema)

        # Should fail (returns error in analysis_results)
        result = analyzer.analyze_script(script)
        # Check that there's an error in the results
        has_error = any(
            not r.get("success", True) for r in result.analysis_results
        )
        assert has_error, "Should have error for INSERT INTO nonexistent table"

    def test_column_count_mismatch(self):
        """Test column count mismatch in INSERT."""
        script = """
        CREATE TABLE t1 AS SELECT col1, col2 FROM source;
        INSERT INTO t1 SELECT col1 FROM source;
        """

        schema = DictSchemaProvider({"source": ["col1", "col2"]})
        analyzer = ScriptAnalyzer(schema_provider=schema)

        # Should fail (returns error in analysis_results)
        result = analyzer.analyze_script(script)
        # Check that there's an error in the results
        has_error = any(
            not r.get("success", True) for r in result.analysis_results
        )
        assert has_error, "Should have error for column count mismatch"
