"""
Debug script for UNION/UNION ALL in CTE issues.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lineage_analyzer.analyzer.script_analyzer import ScriptAnalyzer
from lineage_analyzer.schema.dict_provider import DictSchemaProvider

# Simplest UNION scenario
sql1 = """
WITH combined AS (
    SELECT id, name FROM table1
    UNION ALL
    SELECT id, name FROM table2
)
CREATE TABLE result AS
SELECT id, name FROM combined;
"""

# Print detailed information
schema = DictSchemaProvider({
    "table1": ["id", "name"],
    "table2": ["id", "name"]
})
analyzer = ScriptAnalyzer(schema_provider=schema)

try:
    result = analyzer.analyze_script(sql1)
    
    print("=== Tables in registry ===")
    all_tables = result.get_all_tables()
    for table_def in all_tables:
        name = table_def.name
        print(f"\n{name}:")
        print(f"  Type: {table_def.table_type}")
        print(f"  Columns: {len(table_def.columns)}")
        for col_name, col_lineage in table_def.columns.items():
            sources_str = ", ".join(f"{s.table}.{s.column}" for s in col_lineage.sources)
            print(f"    {col_name}: sources=[{sources_str}]")
    
    print("\n=== Result table ===")
    result_table = result.get_table("result")
    if result_table:
        print(f"Columns: {len(result_table.columns)}")
        for col_name, col_lineage in result_table.columns.items():
            sources_str = ", ".join(f"{s.table}.{s.column}" for s in col_lineage.sources)
            print(f"  {col_name}: sources=[{sources_str}]")
    else:
        print("Result table not found!")
        
    print("\n=== Combined CTE ===")
    combined_cte = result.get_table("combined")
    if combined_cte:
        print(f"Columns: {len(combined_cte.columns)}")
        for col_name, col_lineage in combined_cte.columns.items():
            sources_str = ", ".join(f"{s.table}.{s.column}" for s in col_lineage.sources)
            print(f"  {col_name}: sources=[{sources_str}]")
    else:
        print("Combined CTE not found (may be cleaned up)")
        
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

