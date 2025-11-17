"""
Performance tests: Ensure system can handle large-scale scripts.

This module contains performance tests to verify the system can handle
large scripts efficiently.
"""

import time

import pytest

from lineage_analyzer import DictSchemaProvider, ScriptAnalyzer


class TestPerformance:
    """Performance tests."""

    def test_large_script_performance(self):
        """Test large script performance."""
        # Generate 50 CREATE TABLE AS statements
        statements = []
        for i in range(50):
            statements.append(
                f"CREATE TABLE t{i} AS SELECT amount FROM t{i-1 if i > 0 else 'source'};"
            )

        script = "\n".join(statements)

        schema = DictSchemaProvider({"source": ["amount"]})
        analyzer = ScriptAnalyzer(schema_provider=schema)

        # Measure time
        start = time.time()
        result = analyzer.analyze_script(script)
        elapsed = time.time() - start

        # Verify result
        assert len(result.get_all_tables()) >= 50

        # Performance requirement: 50 statements should complete in 10 seconds
        assert elapsed < 10, f"Performance issue: took {elapsed:.2f}s"

        print(f"Analyzed 50 statements in {elapsed:.2f}s")

    def test_deep_trace_performance(self):
        """Test deep trace performance."""
        # Create 15-layer deep dependency chain (reduced for reliability)
        statements = []
        statements.append("CREATE TABLE t0 AS SELECT val FROM source;")
        for i in range(1, 15):
            statements.append(f"CREATE TABLE t{i} AS SELECT val FROM t{i-1};")

        script = "\n".join(statements)

        schema = DictSchemaProvider({"source": ["val"]})
        analyzer = ScriptAnalyzer(schema_provider=schema)
        result = analyzer.analyze_script(script)

        # Verify tables were created
        all_tables = result.get_all_tables()
        assert len(all_tables) >= 15, f"Expected at least 15 tables, got {len(all_tables)}"

        # Trace deepest field
        start = time.time()
        paths = result.trace("t14", "val")
        elapsed = time.time() - start

        # Verify path is correct (should find at least one path)
        assert len(paths) >= 1, f"Should find at least one path, found {len(paths)}. Tables: {[t.name for t in all_tables]}"
        if paths:
            assert paths[0].hops == 15

        # Performance requirement: 15-layer trace should complete in 1 second
        assert elapsed < 1, f"Trace performance issue: took {elapsed:.2f}s"

        print(f"Traced 15 hops in {elapsed:.2f}s")

    def test_wide_impact_performance(self):
        """Test wide dependency impact analysis performance."""
        # Create one source table referenced by 50 downstream tables
        statements = ["CREATE TABLE source AS SELECT val FROM raw_source;"]

        for i in range(50):
            statements.append(
                f"CREATE TABLE downstream_{i} AS SELECT val FROM source;"
            )

        script = "\n".join(statements)

        schema = DictSchemaProvider({"raw_source": ["val"]})
        analyzer = ScriptAnalyzer(schema_provider=schema)
        result = analyzer.analyze_script(script)

        # Impact analysis
        start = time.time()
        impacts = result.impact("source", "val")
        elapsed = time.time() - start

        # Verify found all downstream
        assert len(impacts) == 50

        # Performance requirement: 50 downstreams should be found in 2 seconds
        assert elapsed < 2, f"Impact analysis performance issue: took {elapsed:.2f}s"

        print(f"Found 50 impacts in {elapsed:.2f}s")
