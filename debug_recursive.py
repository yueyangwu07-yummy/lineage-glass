"""
Debug script for recursive CTE lineage tracking.
Tests simple and complex recursive CTE scenarios.
"""

from lineage_analyzer import ScriptAnalyzer, DictSchemaProvider


# Test 1: Simple recursive (this should work)
sql_simple = """
WITH RECURSIVE numbers AS (
    SELECT 1 as n
    UNION ALL
    SELECT n + 1 FROM numbers WHERE n < 10
)
CREATE TABLE result AS
SELECT n FROM numbers;
"""

# Test 2: Hierarchy data (this may have issues)
sql_hierarchy = """
WITH RECURSIVE emp_hierarchy AS (
    SELECT emp_id, emp_name, manager_id, 1 as level
    FROM employees
    WHERE manager_id IS NULL
    UNION ALL
    SELECT e.emp_id, e.emp_name, e.manager_id, h.level + 1
    FROM employees e
    JOIN emp_hierarchy h ON e.manager_id = h.emp_id
)
CREATE TABLE result AS
SELECT * FROM emp_hierarchy;
"""

# Test 3: Recursive CTE referenced (this may have issues)
sql_reference = """
WITH RECURSIVE emp_hierarchy AS (
    SELECT emp_id, emp_name, manager_id
    FROM employees
    WHERE manager_id IS NULL
    UNION ALL
    SELECT e.emp_id, e.emp_name, e.manager_id
    FROM employees e
    JOIN emp_hierarchy h ON e.manager_id = h.emp_id
)
CREATE TABLE result AS
SELECT eh.emp_id, eh.emp_name
FROM emp_hierarchy eh
JOIN departments d ON eh.emp_id = d.manager_id;
"""


def test_sql(sql, name):
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"{'='*60}")
    
    try:
        schema = DictSchemaProvider({
            "employees": ["emp_id", "emp_name", "manager_id"],
            "departments": ["dept_id", "manager_id", "dept_name"]
        })
        analyzer = ScriptAnalyzer(schema_provider=schema)
        result = analyzer.analyze_script(sql)
        
        print(f"\n--- Tables registered ---")
        for table_name, table_def in result.registry.tables.items():
            print(f"\n{table_name} ({table_def.table_type}):")
            print(f"  is_recursive: {getattr(table_def, 'is_recursive', False)}")
            print(f"  columns: {len(table_def.columns)}")
            for col_name, col_lineage in list(table_def.columns.items())[:5]:
                source_str = ", ".join([f"{s.table}.{s.column}" for s in col_lineage.sources[:3]]) if col_lineage.sources else "no sources"
                print(f"    {col_name}: {source_str}")
        
        # Check result table lineage
        if 'result' in result.registry.tables:
            print(f"\n--- Result table lineage ---")
            result_table = result.registry.tables['result']
            for col_name, col_lineage in result_table.columns.items():
                print(f"{col_name}:")
                if col_lineage.sources:
                    for src in col_lineage.sources[:5]:
                        print(f"  <- {src.table}.{src.column}")
                else:
                    print(f"  <- (no source)")
        
        # Try tracing
        if 'result' in result.registry.tables:
            print(f"\n--- Tracing lineage paths ---")
            result_table = result.registry.tables['result']
            for col_name in list(result_table.columns.keys())[:3]:
                try:
                    paths = result.trace("result", col_name)
                    if paths:
                        print(f"{col_name} paths ({len(paths)}):")
                        for i, path in enumerate(paths[:3], 1):
                            path_str = path.to_string()
                            try:
                                print(f"  Path {i}: {path_str}")
                            except UnicodeEncodeError:
                                print(f"  Path {i}: {path_str.encode('ascii', 'replace').decode('ascii')}")
                    else:
                        print(f"{col_name}: No paths found")
                except Exception as e:
                    print(f"{col_name}: Trace failed: {e}")
        
        print(f"\n[OK] {name} analyzed successfully")
        
    except Exception as e:
        print(f"\n[FAIL] {name} failed: {e}")
        import traceback
        traceback.print_exc()


# Run tests
if __name__ == "__main__":
    test_sql(sql_simple, "Simple recursive CTE")
    test_sql(sql_hierarchy, "Hierarchy recursive CTE")
    test_sql(sql_reference, "Recursive CTE with JOIN reference")

