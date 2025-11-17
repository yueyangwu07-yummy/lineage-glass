"""Test field-level lineage API"""
import requests
import json
import sys
import io

# Fix encoding for Windows console
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Test SQL - Using CREATE TABLE AS to ensure CTE is registered
sql = """
WITH sales_summary AS (
    SELECT 
        product_id,
        SUM(amount) as total_sales
    FROM sales
    GROUP BY product_id
)
CREATE TABLE result AS
SELECT 
    p.name as product_name,
    ss.total_sales
FROM products p
JOIN sales_summary ss ON p.id = ss.product_id;
"""

# 1. First analyze SQL
print("1. Analyzing SQL...")
response = requests.post(
    'http://localhost:5000/api/analyze',
    data={'sql': sql}
)
if response.status_code == 200:
    print("✅ Analysis successful")
    data = response.json()
    print(f"   Found {len(data['tables'])} tables")
else:
    print(f"❌ Analysis failed: {response.text}")
    exit(1)

# 2. Get field-level lineage
# Test with the result table's total_sales column
print("\n2. Fetching field lineage for 'result.total_sales'...")
response = requests.get(
    'http://localhost:5000/api/field-lineage/result/total_sales'
)
if response.status_code == 200:
    print("✅ Field lineage retrieved")
    lineage = response.json()
    
    print(f"\n   Field: {lineage['field']}")
    print(f"   Graph nodes: {len(lineage['graph']['nodes'])}")
    print(f"   Graph edges: {len(lineage['graph']['edges'])}")
    
    print("\n   Path:")
    for node in lineage['path']:
        indent = "  " * node['level']
        trans = f" ({node['transformation']})" if node['transformation'] else ""
        print(f"{indent}{node['table']}.{node['column']}{trans}")
    
    # Save detailed result
    with open('field_lineage_result.json', 'w') as f:
        json.dump(lineage, f, indent=2)
    print("\n   Full result saved to field_lineage_result.json")
else:
    print(f"❌ Failed: {response.text}")

