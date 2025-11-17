"""
Quick test script for the Web UI API
"""
import requests

# Test SQL
test_sql = """
CREATE TABLE dept_stats AS
SELECT 
    dept_id,
    COUNT(*) as emp_count,
    AVG(salary) as avg_salary
FROM employees
GROUP BY dept_id;
"""

# Test API
response = requests.post(
    'http://localhost:5000/api/analyze',
    data={'sql': test_sql}
)

if response.status_code == 200:
    data = response.json()
    print("API Test Successful!")
    print(f"Found {len(data['tables'])} tables")
    print(f"Graph has {len(data['graph']['nodes'])} nodes and {len(data['graph']['edges'])} edges")
    print("\nTables:")
    for table in data['tables']:
        print(f"  - {table['name']} ({table['type']}) - {len(table['columns'])} columns")
else:
    print(f"API Test Failed: {response.status_code}")
    print(response.text)

