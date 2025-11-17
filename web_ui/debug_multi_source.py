"""Debug multi-source field lineage tracking"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from lineage_analyzer.analyzer.script_analyzer import ScriptAnalyzer

sql = """
CREATE TABLE clean_orders AS
SELECT 
    order_id,
    customer_id,
    amount,
    tax,
    amount + tax AS total
FROM raw_orders;

INSERT INTO clean_orders
SELECT 
    order_id,
    customer_id,
    amount,
    tax,
    amount + tax AS total
FROM raw_orders_incremental;
"""

analyzer = ScriptAnalyzer()
result = analyzer.analyze_script(sql)

# 检查clean_orders.total的血缘
clean_orders = result.registry.tables.get('clean_orders')
if clean_orders:
    total_lineage = clean_orders.columns.get('total')
    if total_lineage:
        print(f"clean_orders.total source columns count: {len(total_lineage.sources)}")
        print("Source columns list:")
        for src in total_lineage.sources:
            print(f"  - {src.table}.{src.column}")
        print(f"\nExpression: {total_lineage.expression}")
        print(f"Is aggregate: {total_lineage.is_aggregate}")
        print(f"Has sources attr: {hasattr(total_lineage, 'sources')}")
        if hasattr(total_lineage, 'sources'):
            print(f"Sources type: {type(total_lineage.sources)}")
            print(f"Sources length: {len(total_lineage.sources) if total_lineage.sources else 0}")
    else:
        print("ERROR: clean_orders.total column not found")
else:
    print("ERROR: clean_orders table not found")

# Test field-level lineage
from app import trace_field_lineage

print("\n=== Testing Field-Level Lineage ===")
try:
    path = trace_field_lineage(result, 'clean_orders', 'total')
    print(f"Path nodes count: {len(path)}")
    print("Path:")
    for node in path:
        print(f"  Level {node['level']}: {node['table']}.{node['column']}")
        print(f"    Sources: {len(node.get('sources', []))}")
        if node.get('sources'):
            for src in node['sources']:
                print(f"      - {src['table']}.{src['column']}")
        else:
            print(f"    (Leaf node - no sources)")
    
    # Summary
    print(f"\n=== Summary ===")
    print(f"Total nodes in path: {len(path)}")
    total_sources = sum(len(node.get('sources', [])) for node in path)
    print(f"Total source fields: {total_sources}")
    
    if total_sources == 4:
        print("SUCCESS: All 4 source fields found!")
    else:
        print(f"WARNING: Expected 4 sources, found {total_sources}")
        
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
