"""Debug script to check table structure"""
import requests
import json

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

print("Analyzing SQL...")
response = requests.post(
    'http://localhost:5000/api/analyze',
    data={'sql': sql}
)

if response.status_code == 200:
    data = response.json()
    print(f"\nFound {len(data['tables'])} tables:\n")
    
    for table in data['tables']:
        print(f"Table: {table['name']} (type: {table['type']})")
        print(f"  Columns: {len(table.get('columns', []))}")
        for col in table.get('columns', []):
            sources = col.get('sources', [])
            print(f"    - {col['name']}:")
            print(f"        expression: {col.get('expression', 'None')}")
            print(f"        sources: {sources}")
            print(f"        is_aggregate: {col.get('is_aggregate', False)}")
            print(f"        aggregate_function: {col.get('aggregate_function', 'None')}")
        print()
else:
    print(f"Error: {response.text}")

