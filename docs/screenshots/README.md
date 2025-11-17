# Screenshots

This directory contains screenshots of the Lineage Glass Web UI.

## Required Screenshots

To complete the documentation, please capture the following screenshots:

### 1. Input Interface (`input.png`)
- Shows the Web UI input page
- SQL textarea with example SQL
- File upload option visible
- "Load example SQL" button visible

### 2. Lineage Graph (`graph.png`)
- Shows the interactive lineage graph
- Multiple tables visible as nodes
- Edges showing dependencies
- Search box visible
- Legend showing table types

### 3. Details Panel (`details.png`)
- Shows the details panel on the right
- Table information displayed
- Column list with sources
- Aggregate function badges visible
- GROUP BY indicators visible

## How to Capture

1. Start the Web UI:
   ```bash
   cd web_ui
   python app.py
   ```

2. Open http://localhost:5000 in your browser

3. Load example SQL or paste a sample query

4. Click "Analyze"

5. Capture screenshots at 1920x1080 or higher resolution

6. Save as PNG files with the names above

## Example SQL for Screenshots

Use this SQL for consistent screenshots:

```sql
-- Example: Sales Analysis with CTE and Aggregates
WITH monthly_sales AS (
    SELECT 
        dept_id,
        AVG(salary) as avg_salary,
        COUNT(*) as emp_count
    FROM employees
    GROUP BY dept_id
)
SELECT 
    d.name as dept_name,
    ms.avg_salary,
    ms.emp_count
FROM departments d
JOIN monthly_sales ms ON d.id = ms.dept_id
WHERE ms.avg_salary > 50000;
```

