#!/usr/bin/env python3
"""
Quick Start Script - Demonstrates lineage-analyzer core features

This script provides a quick demonstration of the main features
of lineage-analyzer v1.0.
"""

from lineage_analyzer import DictSchemaProvider, ScriptAnalyzer


def main():
    print("=" * 60)
    print("Lineage Analyzer v1.0 - Quick Start Demo")
    print("=" * 60)
    print()

    # Example SQL script (simplified for v1.0 - no aggregation)
    script = """
    -- Step 1: Extract user orders
    CREATE TABLE user_orders AS
    SELECT 
        user_id,
        order_id,
        amount
    FROM orders;
    
    -- Step 2: Create totals (without aggregation)
    CREATE TABLE user_totals AS
    SELECT 
        user_id,
        amount AS total_amount,
        order_id
    FROM user_orders;
    
    -- Step 3: Create a report
    CREATE TABLE user_report AS
    SELECT 
        u.name,
        ut.total_amount,
        ut.order_id
    FROM users u
    JOIN user_totals ut ON u.id = ut.user_id;
    """

    # Schema definition
    schema = DictSchemaProvider(
        {"orders": ["order_id", "user_id", "amount"], "users": ["id", "name", "email"]}
    )

    # Analyze script
    print("Analyzing SQL script...\n")
    analyzer = ScriptAnalyzer(schema_provider=schema)
    result = analyzer.analyze_script(script)

    print(f"[OK] Analysis complete! Found {len(result.get_all_tables())} tables.\n")

    # Demo 1: Trace field
    print("=" * 60)
    print("Demo 1: Trace a field to its sources")
    print("=" * 60)
    print("\nQuestion: Where does 'user_report.name' come from?\n")

    # Trace a field
    user_report = result.get_table("user_report")
    if user_report and user_report.has_column("name"):
        paths = result.trace("user_report", "name")
        for path in paths:
            # Use ASCII-safe representation (replace Unicode arrow)
            path_str = path.to_string().replace('←', '<-')
            print(f"  {path_str}")
            print(f"  - Hops: {path.hops}\n")
    else:
        print("  (Note: user_report table not found)\n")

    # Demo 2: Impact analysis
    print("=" * 60)
    print("Demo 2: Impact Analysis")
    print("=" * 60)
    print("\nQuestion: What breaks if I change 'orders.amount'?\n")

    impacts = result.impact("orders", "amount")
    print(f"  Affects {len(impacts)} downstream field(s):\n")
    for impact in impacts:
        print(f"  - {impact.table}.{impact.column}")
    print()

    # Demo 3: List tables
    print("=" * 60)
    print("Demo 3: List All Tables")
    print("=" * 60)
    print()

    source_tables = result.get_source_tables()
    derived_tables = result.get_derived_tables()

    if source_tables:
        print("  Source Tables:")
        for table in source_tables:
            print(f"    - {table.name} ({len(table.columns)} columns)")
        print()

    if derived_tables:
        print("  Derived Tables:")
        for table in derived_tables:
            print(f"    - {table.name} ({len(table.columns)} columns)")
        print()

    print("=" * 60)
    print("Try it yourself!")
    print("=" * 60)
    print("\nRun: lineage-analyzer examples/simple/transform.sql\n")


if __name__ == "__main__":
    main()
