"""Debug script to check field lineage tracing"""
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

print("1. Analyzing SQL...")
response = requests.post(
    'http://localhost:5000/api/analyze',
    data={'sql': sql}
)

if response.status_code != 200:
    print(f"Error: {response.text}")
    exit(1)

print("2. Getting field lineage...")
response = requests.get(
    'http://localhost:5000/api/field-lineage/result/total_sales'
)

if response.status_code == 200:
    lineage = response.json()
    print(f"\nField: {lineage['field']}")
    print(f"Path nodes: {len(lineage['path'])}")
    print(f"Graph nodes: {len(lineage['graph']['nodes'])}")
    print(f"Graph edges: {len(lineage['graph']['edges'])}")
    
    print("\nDetailed path:")
    def print_node(node, indent=0):
        prefix = "  " * indent
        print(f"{prefix}Level {node['level']}: {node['table']}.{node['column']}")
        if node.get('transformation'):
            print(f"{prefix}  Transformation: {node['transformation']}")
        print(f"{prefix}  Sources count: {len(node.get('sources', []))}")
        for src in node.get('sources', []):
            print_node(src, indent + 1)
    
    for node in lineage['path']:
        print_node(node)
    
    print("\nFull JSON:")
    print(json.dumps(lineage, indent=2))
else:
    print(f"Error: {response.text}")

