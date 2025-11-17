import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lineage_analyzer.analyzer.script_analyzer import ScriptAnalyzer
from lineage_analyzer.schema.dict_provider import DictSchemaProvider

sql = """
WITH combined AS (
    SELECT id, name FROM table1
    UNION ALL
    SELECT id, name FROM table2
)
CREATE TABLE result AS
SELECT id, name FROM combined;
"""

schema = DictSchemaProvider({
    "table1": ["id", "name"],
    "table2": ["id", "name"]
})

analyzer = ScriptAnalyzer(schema_provider=schema)

try:
    result = analyzer.analyze_script(sql)
    
    combined = result.get_table("combined")
    result_table = result.get_table("result")
    
    print(f"Combined CTE: {combined}")
    if combined:
        print(f"  Type: {combined.table_type}")
        print(f"  Columns: {len(combined.columns)}")
        for col_name in combined.columns:
            print(f"    {col_name}")
    
    print(f"\nResult table: {result_table}")
    if result_table:
        print(f"  Type: {result_table.table_type}")
        print(f"  Columns: {len(result_table.columns)}")
        for col_name in result_table.columns:
            print(f"    {col_name}")
            
except Exception as e:
    import traceback
    print(f"Error: {e}")
    traceback.print_exc()

