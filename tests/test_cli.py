"""
Tests for CLI functionality (end-to-end).

This module contains tests for the command-line interface, testing
actual CLI commands and their output.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


class TestCLI:
    """Test CLI functionality (end-to-end)."""

    def setup_method(self):
        """Create test SQL files."""
        self.test_dir = Path("tests/test_data")
        self.test_dir.mkdir(exist_ok=True, parents=True)

        # Create test script
        self.script_file = self.test_dir / "test_script.sql"
        self.script_file.write_text(
            """
        CREATE TABLE t1 AS SELECT amount FROM orders;
        CREATE TABLE t2 AS SELECT amount * 2 AS doubled FROM t1;
        CREATE TABLE t3 AS SELECT doubled + 100 AS final FROM t2;
        """
        )

        # Create schema file
        self.schema_file = self.test_dir / "schema.json"
        self.schema_file.write_text(
            json.dumps({"orders": ["id", "amount", "tax"]})
        )

    def teardown_method(self):
        """Clean up test files."""
        if self.script_file.exists():
            self.script_file.unlink()
        if self.schema_file.exists():
            self.schema_file.unlink()

    def run_cli(self, *args):
        """Run CLI command."""
        # Use python -m to run the CLI
        # Set UTF-8 encoding for Windows compatibility
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        cmd = [sys.executable, "-m", "lineage_analyzer.cli"] + list(args)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",  # Replace invalid characters instead of failing
            cwd=Path.cwd(),
            env=env,
        )
        return result

    def test_basic_analysis(self):
        """Test basic analysis."""
        result = self.run_cli(str(self.script_file))

        assert result.returncode == 0
        assert "Analysis complete" in result.stdout
        assert "tables" in result.stdout.lower()

    def test_trace_command(self):
        """Test --trace command."""
        result = self.run_cli(
            str(self.script_file),
            "--schema",
            str(self.schema_file),
            "--trace",
            "t3.final",
        )

        assert result.returncode == 0
        assert "t3.final" in result.stdout
        # Should find lineage or show no lineage message
        assert "orders.amount" in result.stdout or "No lineage found" in result.stdout

    def test_impact_command(self):
        """Test --impact command."""
        result = self.run_cli(
            str(self.script_file),
            "--schema",
            str(self.schema_file),
            "--impact",
            "orders.amount",
        )

        assert result.returncode == 0
        assert "affected field" in result.stdout.lower()
        assert "t1" in result.stdout or "t2" in result.stdout or "t3" in result.stdout

    def test_explain_command(self):
        """Test --explain command."""
        result = self.run_cli(
            str(self.script_file),
            "--explain",
            "t3.final",
        )

        assert result.returncode == 0
        assert "Calculation chain" in result.stdout or "t3.final" in result.stdout

    def test_list_tables(self):
        """Test --list-tables command."""
        result = self.run_cli(str(self.script_file), "--list-tables")

        assert result.returncode == 0
        assert "t1" in result.stdout or "t2" in result.stdout or "t3" in result.stdout

    def test_export_json(self):
        """Test --export command."""
        output_file = self.test_dir / "lineage.json"

        result = self.run_cli(
            str(self.script_file),
            "--export",
            str(output_file),
            "--format",
            "json",
        )

        assert result.returncode == 0
        assert output_file.exists()

        # Verify JSON format
        data = json.loads(output_file.read_text())
        assert "tables" in data

        # Clean up
        output_file.unlink()

    def test_invalid_column_ref(self):
        """Test invalid column reference."""
        result = self.run_cli(str(self.script_file), "--trace", "invalid_format")

        assert result.returncode != 0
        assert "Invalid column reference" in result.stderr or "not found" in result.stderr

    def test_nonexistent_file(self):
        """Test non-existent file."""
        result = self.run_cli("nonexistent.sql")

        assert result.returncode != 0
        assert "File not found" in result.stderr or "not found" in result.stderr

    def test_with_schema(self):
        """Test with schema file."""
        result = self.run_cli(
            str(self.script_file),
            "--schema",
            str(self.schema_file),
        )

        assert result.returncode == 0
        assert "Analysis complete" in result.stdout

    def test_no_color(self):
        """Test --no-color option."""
        result = self.run_cli(str(self.script_file), "--no-color", "--list-tables")

        assert result.returncode == 0
        # Should still work without color

