"""
Command-line interface for lineage analyzer v1.0.

This module provides a command-line interface for the lineage analyzer,
allowing users to analyze SQL scripts from the command line with support
for trace, impact analysis, and explanation features.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from lineage_analyzer import (
    DictSchemaProvider,
    ErrorMode,
    LineageConfig,
    ScriptAnalyzer,
)
from lineage_analyzer.exceptions import LineageError

# Try to import color library (optional)
try:
    from colorama import Fore, Style, init

    init(autoreset=True)
    HAS_COLOR = True
except ImportError:
    HAS_COLOR = False
    # Define empty color constants
    class Fore:
        RED = GREEN = YELLOW = BLUE = CYAN = MAGENTA = WHITE = RESET = ""

    class Style:
        BRIGHT = DIM = RESET_ALL = ""


def print_success(msg: str) -> None:
    """Print success message."""
    try:
        if HAS_COLOR:
            print(f"{Fore.GREEN}✓ {msg}{Style.RESET_ALL}")
        else:
            print(f"[OK] {msg}")
    except UnicodeEncodeError:
        # Fallback for Windows console encoding issues
        if HAS_COLOR:
            print(f"{Fore.GREEN}[OK] {msg}{Style.RESET_ALL}")
        else:
            print(f"[OK] {msg}")


def print_error(msg: str) -> None:
    """Print error message."""
    try:
        if HAS_COLOR:
            print(f"{Fore.RED}✗ {msg}{Style.RESET_ALL}", file=sys.stderr)
        else:
            print(f"[ERROR] {msg}", file=sys.stderr)
    except UnicodeEncodeError:
        # Fallback for Windows console encoding issues
        if HAS_COLOR:
            print(f"{Fore.RED}[ERROR] {msg}{Style.RESET_ALL}", file=sys.stderr)
        else:
            print(f"[ERROR] {msg}", file=sys.stderr)


def print_warning(msg: str) -> None:
    """Print warning message."""
    try:
        if HAS_COLOR:
            print(f"{Fore.YELLOW}⚠ {msg}{Style.RESET_ALL}")
        else:
            print(f"[WARN] {msg}")
    except UnicodeEncodeError:
        # Fallback for Windows console encoding issues
        if HAS_COLOR:
            print(f"{Fore.YELLOW}[WARN] {msg}{Style.RESET_ALL}")
        else:
            print(f"[WARN] {msg}")


def print_info(msg: str) -> None:
    """Print info message."""
    if HAS_COLOR:
        print(f"{Fore.CYAN}{msg}{Style.RESET_ALL}")
    else:
        print(msg)


def main() -> None:
    """
    CLI main entry point.

    Supported commands:
        # Basic analysis
        lineage-analyzer script.sql

        # Trace field to source
        lineage-analyzer script.sql --trace table.column

        # Impact analysis
        lineage-analyzer script.sql --impact table.column

        # Explain calculation
        lineage-analyzer script.sql --explain table.column

        # Export full lineage graph
        lineage-analyzer script.sql --export lineage.json

        # Multiple output formats
        lineage-analyzer script.sql --format table
        lineage-analyzer script.sql --format json
        lineage-analyzer script.sql --format pretty
    """
    parser = argparse.ArgumentParser(
        prog="lineage-analyzer",
        description="SQL Field-Level Lineage Analyzer - v1.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze a SQL script
  %(prog)s script.sql

  # Trace a field to its sources
  %(prog)s script.sql --trace report.revenue

  # Impact analysis
  %(prog)s script.sql --impact orders.amount

  # Explain calculation chain
  %(prog)s script.sql --explain dashboard.total_sales

  # Export full lineage graph
  %(prog)s script.sql --export lineage.json --format json

  # With schema validation
  %(prog)s script.sql --schema schema.json --strict
        """,
    )

    # === Input parameters ===
    input_group = parser.add_argument_group("Input Options")
    input_group.add_argument("sql_file", help="SQL script file to analyze")
    input_group.add_argument(
        "--schema", "-s", help="Schema definition file (JSON format)"
    )

    # === Query parameters ===
    query_group = parser.add_argument_group("Query Options")
    query_group.add_argument(
        "--trace",
        "-t",
        metavar="TABLE.COLUMN",
        help="Trace a field to its source tables (e.g., 'report.revenue')",
    )
    query_group.add_argument(
        "--impact",
        "-i",
        metavar="TABLE.COLUMN",
        help="Find all downstream fields affected by this column",
    )
    query_group.add_argument(
        "--explain",
        "-e",
        metavar="TABLE.COLUMN",
        help="Explain the calculation chain of a field",
    )
    query_group.add_argument(
        "--list-tables",
        action="store_true",
        help="List all tables in the script",
    )

    # === Output parameters ===
    output_group = parser.add_argument_group("Output Options")
    output_group.add_argument(
        "--format",
        "-f",
        choices=["json", "table", "pretty", "graph"],
        default="pretty",
        help="Output format (default: pretty)",
    )
    output_group.add_argument(
        "--export", "-o", metavar="FILE", help="Export full lineage graph to file"
    )
    output_group.add_argument(
        "--no-color", action="store_true", help="Disable colored output"
    )

    # === Configuration parameters ===
    config_group = parser.add_argument_group("Configuration")
    config_group.add_argument(
        "--strict", action="store_true", help="Enable strict mode (fail on ambiguity)"
    )
    config_group.add_argument(
        "--no-warnings", action="store_true", help="Suppress warnings"
    )
    config_group.add_argument(
        "--max-depth",
        type=int,
        default=100,
        help="Maximum trace depth (default: 100)",
    )

    args = parser.parse_args()

    # Disable color
    if args.no_color:
        global HAS_COLOR
        HAS_COLOR = False

    try:
        # 1. Read SQL file
        sql_file = Path(args.sql_file)
        if not sql_file.exists():
            print_error(f"File not found: {args.sql_file}")
            sys.exit(1)

        print_info(f"Reading SQL from: {sql_file}")
        sql_script = sql_file.read_text(encoding="utf-8")

        # 2. Read Schema (if provided)
        schema_provider = None
        if args.schema:
            schema_path = Path(args.schema)
            if not schema_path.exists():
                print_error(f"Schema file not found: {args.schema}")
                sys.exit(1)

            print_info(f"Loading schema from: {schema_path}")
            schema_dict = json.loads(schema_path.read_text(encoding="utf-8"))
            schema_provider = DictSchemaProvider(schema_dict)

        # 3. Configure analyzer
        config = LineageConfig(
            strict_mode=args.strict,
            on_ambiguity=ErrorMode.FAIL if args.strict else ErrorMode.WARN,
        )

        # 4. Execute analysis
        print_info("Analyzing SQL script...")
        analyzer = ScriptAnalyzer(config=config, schema_provider=schema_provider)
        result = analyzer.analyze_script(sql_script)

        print_success(
            f"Analysis complete! Found {len(result.get_all_tables())} tables."
        )

        # 5. Handle query commands
        if args.trace:
            handle_trace(result, args.trace, args.max_depth)
        elif args.impact:
            handle_impact(result, args.impact, args.max_depth)
        elif args.explain:
            handle_explain(result, args.explain)
        elif args.list_tables:
            handle_list_tables(result)
        else:
            # Default: show summary
            handle_summary(result, args.format)

        # 6. Export (if needed)
        if args.export:
            handle_export(result, args.export, args.format)

        # 7. Show warnings (if any)
        if not args.no_warnings:
            show_warnings(result)

    except LineageError as e:
        print_error(f"Lineage analysis failed: {e}")
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def parse_column_ref(ref: str) -> tuple[str, str]:
    """
    Parse column reference string.

    Args:
        ref: Format "table.column"

    Returns:
        (table_name, column_name)

    Raises:
        ValueError: If format is incorrect
    """
    parts = ref.split(".")
    if len(parts) != 2:
        raise ValueError(
            f"Invalid column reference: '{ref}'. "
            f"Expected format: 'table_name.column_name'"
        )
    return parts[0], parts[1]


def handle_trace(result, column_ref: str, max_depth: int) -> None:
    """Handle --trace command."""
    try:
        table_name, column_name = parse_column_ref(column_ref)
    except ValueError as e:
        print_error(str(e))
        sys.exit(1)

    print_info(f"\nTracing {column_ref} to source tables...\n")

    try:
        paths = result.trace(table_name, column_name)

        if not paths:
            print_warning(f"No lineage found for {column_ref}")
            return

        print_success(f"Found {len(paths)} lineage path(s):\n")

        for i, path in enumerate(paths, 1):
            if len(paths) > 1:
                if HAS_COLOR:
                    print(f"{Fore.CYAN}Path {i}:{Style.RESET_ALL}")
                else:
                    print(f"Path {i}:")

            # Use ASCII-safe representation for Windows compatibility
            path_str = path.to_string(use_ascii=True)
            print(f"  {path_str}")
            print(f"  Hops: {path.hops}")
            if path.source:
                if HAS_COLOR:
                    print(
                        f"  Source: {Fore.GREEN}{path.source.column.table}.{path.source.column.column}{Style.RESET_ALL}"
                    )
                else:
                    print(
                        f"  Source: {path.source.column.table}.{path.source.column.column}"
                    )
            print()

    except LineageError as e:
        print_error(str(e))
        sys.exit(1)


def handle_impact(result, column_ref: str, max_depth: int) -> None:
    """Handle --impact command."""
    try:
        table_name, column_name = parse_column_ref(column_ref)
    except ValueError as e:
        print_error(str(e))
        sys.exit(1)

    print_info(f"\nFinding impact of {column_ref}...\n")

    try:
        impacts = result.impact(table_name, column_name)

        if not impacts:
            print_warning(f"No downstream dependencies found for {column_ref}")
            return

        print_success(f"Found {len(impacts)} affected field(s):\n")

        # Group by table
        by_table: dict[str, list[str]] = {}
        for col_ref in impacts:
            if col_ref.table not in by_table:
                by_table[col_ref.table] = []
            by_table[col_ref.table].append(col_ref.column)

        for table, columns in sorted(by_table.items()):
            if HAS_COLOR:
                print(f"{Fore.YELLOW}{table}:{Style.RESET_ALL}")
            else:
                print(f"{table}:")
            for col in sorted(columns):
                print(f"  - {col}")
            print()

    except LineageError as e:
        print_error(str(e))
        sys.exit(1)


def handle_explain(result, column_ref: str) -> None:
    """Handle --explain command."""
    try:
        table_name, column_name = parse_column_ref(column_ref)
    except ValueError as e:
        print_error(str(e))
        sys.exit(1)

    print_info(f"\nExplaining calculation of {column_ref}...\n")

    try:
        explanation = result.explain(table_name, column_name)
        print(explanation)
        print()

    except LineageError as e:
        print_error(str(e))
        sys.exit(1)


def handle_list_tables(result) -> None:
    """Handle --list-tables command."""
    print_info("\nTables in script:\n")

    source_tables = result.get_source_tables()
    derived_tables = result.get_derived_tables()

    if source_tables:
        if HAS_COLOR:
            print(f"{Fore.GREEN}Source Tables:{Style.RESET_ALL}")
        else:
            print("Source Tables:")
        for table in sorted(source_tables, key=lambda t: t.name):
            print(f"  - {table.name} ({len(table.columns)} columns)")
        print()

    if derived_tables:
        if HAS_COLOR:
            print(f"{Fore.CYAN}Derived Tables:{Style.RESET_ALL}")
        else:
            print("Derived Tables:")
        for table in sorted(derived_tables, key=lambda t: t.name):
            print(f"  - {table.name} ({len(table.columns)} columns)")
            if table.created_at_statement is not None:
                print(f"    Created at statement #{table.created_at_statement}")
        print()


def handle_summary(result, format: str) -> None:
    """Show analysis summary."""
    print_info("\n" + "=" * 60)
    print_info("Analysis Summary")
    print_info("=" * 60 + "\n")

    all_tables = result.get_all_tables()
    source_tables = result.get_source_tables()
    derived_tables = result.get_derived_tables()

    print(f"Total tables: {len(all_tables)}")
    print(f"  Source tables: {len(source_tables)}")
    print(f"  Derived tables: {len(derived_tables)}")
    print()

    print(f"Total statements: {len(result.statements)}")
    supported = sum(1 for s in result.statements if s.is_supported())
    print(f"  Supported: {supported}")
    print(f"  Unsupported: {len(result.statements) - supported}")
    print()

    if format == "json":
        print("\nFull lineage data (JSON):")
        print(result.to_json(indent=2))
    elif format == "pretty":
        print("\nDerived Tables Details:")
        for table in sorted(derived_tables, key=lambda t: t.name):
            if HAS_COLOR:
                print(f"\n{Fore.CYAN}{table.name}{Style.RESET_ALL}")
            else:
                print(f"\n{table.name}")
            print(f"  Type: {table.table_type.value if table.table_type else 'unknown'}")
            print(f"  Columns: {len(table.columns)}")

            for col_name, col_lineage in list(table.columns.items())[:5]:  # Show first 5
                sources = ", ".join(
                    f"{s.table}.{s.column}" for s in col_lineage.sources
                )
                print(f"    - {col_name} <- {sources}")

            if len(table.columns) > 5:
                print(f"    ... and {len(table.columns) - 5} more columns")


def handle_export(result, output_file: str, format: str) -> None:
    """Export full lineage graph."""
    output_path = Path(output_file)

    print_info(f"\nExporting lineage to: {output_path}")

    if format == "json":
        data = result.to_dict()
    elif format == "graph":
        # Export as graph format (simplified)
        data = {
            "tables": {
                name: {
                    "type": table.table_type.value if table.table_type else "unknown",
                    "columns": list(table.columns.keys()),
                    "is_source": table.is_source_table,
                }
                for name, table in result.registry.tables.items()
            },
            "lineage": [],
        }

        # Add all dependency edges
        for table in result.registry.get_all_tables():
            for col_name, col_lineage in table.columns.items():
                for source in col_lineage.sources:
                    data["lineage"].append(
                        {
                            "from": f"{source.table}.{source.column}",
                            "to": f"{table.name}.{col_name}",
                            "expression": col_lineage.expression,
                            "type": col_lineage.expression_type.value,
                        }
                    )
    else:
        data = result.to_dict()

    output_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print_success(f"Exported to {output_path}")


def show_warnings(result) -> None:
    """Show warning messages."""
    # Collect all warnings
    warnings = []
    for analysis_result in result.analysis_results:
        if not analysis_result.get("success", True):
            error = analysis_result.get("error") or analysis_result.get("message")
            if error:
                warnings.append(error)

    if warnings:
        print_warning(f"\n{len(warnings)} warning(s):")
        for i, warning in enumerate(warnings, 1):
            print(f"  {i}. {warning}")


if __name__ == "__main__":
    main()
