-- =============================================================================
-- Comprehensive SQL Examples for Lineage Glass
-- Demonstrates all features: Multi-level dependencies, Aggregates, Field-level lineage,
-- Recursive CTE, UNION, Subqueries, Nested derived tables
-- =============================================================================

-- =============================================================================
-- Example 1: E-Commerce Analytics Pipeline
-- Demonstrates: Multi-level dependencies, Aggregates, Field-level lineage
-- =============================================================================

-- Step 1: Clean raw orders
CREATE TABLE clean_orders AS
SELECT 
    order_id,
    customer_id,
    product_id,
    quantity,
    unit_price,
    quantity * unit_price AS subtotal,
    tax_rate,
    quantity * unit_price * tax_rate AS tax_amount,
    quantity * unit_price * (1 + tax_rate) AS total_amount,
    order_date,
    status
FROM raw_orders
WHERE status IN ('completed', 'shipped');

-- Step 2: Customer aggregation with multiple metrics
CREATE TABLE customer_summary AS
SELECT 
    customer_id,
    COUNT(order_id) as total_orders,
    SUM(total_amount) as lifetime_value,
    AVG(total_amount) as avg_order_value,
    MIN(order_date) as first_order_date,
    MAX(order_date) as last_order_date
FROM clean_orders
GROUP BY customer_id;

-- Step 3: Customer segmentation using aggregates
CREATE TABLE customer_segments AS
SELECT 
    cs.customer_id,
    c.name as customer_name,
    c.email,
    cs.total_orders,
    cs.lifetime_value,
    cs.avg_order_value,
    CASE 
        WHEN cs.lifetime_value > 10000 THEN 'VIP'
        WHEN cs.lifetime_value > 5000 THEN 'Premium'
        WHEN cs.lifetime_value > 1000 THEN 'Regular'
        ELSE 'New'
    END AS customer_tier,
    CASE 
        WHEN cs.total_orders > 50 THEN 'Frequent'
        WHEN cs.total_orders > 10 THEN 'Regular'
        ELSE 'Occasional'
    END AS purchase_frequency
FROM customer_summary cs
JOIN customers c ON cs.customer_id = c.customer_id;

-- Trace these fields to see complex lineage:
-- - customer_segments.lifetime_value → customer_summary.lifetime_value → clean_orders.total_amount → raw_orders.quantity, unit_price, tax_rate
-- - customer_segments.customer_tier → Uses CASE expression on aggregated data

-- =============================================================================
-- Example 2: Organizational Hierarchy with Recursive CTE
-- Demonstrates: Recursive CTE, UNION ALL, Multi-level joins
-- =============================================================================

-- Build employee hierarchy (recursive)
WITH RECURSIVE employee_hierarchy AS (
    -- Anchor: Top-level managers
    SELECT 
        emp_id,
        name,
        manager_id,
        title,
        salary,
        1 as level,
        CAST(name AS VARCHAR(1000)) as hierarchy_path
    FROM employees
    WHERE manager_id IS NULL
    
    UNION ALL
    
    -- Recursive: All other employees
    SELECT 
        e.emp_id,
        e.name,
        e.manager_id,
        e.title,
        e.salary,
        eh.level + 1 as level,
        CAST(eh.hierarchy_path || ' > ' || e.name AS VARCHAR(1000)) as hierarchy_path
    FROM employees e
    INNER JOIN employee_hierarchy eh ON e.manager_id = eh.emp_id
    WHERE eh.level < 10
),

-- Calculate team statistics
team_stats AS (
    SELECT 
        manager_id,
        COUNT(*) as team_size,
        AVG(salary) as avg_team_salary,
        SUM(salary) as total_team_cost
    FROM employee_hierarchy
    WHERE manager_id IS NOT NULL
    GROUP BY manager_id
)

-- Final report combining hierarchy and statistics
CREATE TABLE org_report AS
SELECT 
    eh.emp_id,
    eh.name as employee_name,
    eh.title,
    eh.level as org_level,
    eh.hierarchy_path,
    eh.salary as employee_salary,
    ts.team_size,
    ts.avg_team_salary,
    ts.total_team_cost
FROM employee_hierarchy eh
LEFT JOIN team_stats ts ON eh.emp_id = ts.manager_id;

-- Trace these fields:
-- - org_report.hierarchy_path → Shows recursive path building
-- - org_report.avg_team_salary → Aggregate on recursive CTE

-- =============================================================================
-- Example 3: Sales Analysis with Multiple Subqueries
-- Demonstrates: Subqueries in FROM/WHERE/SELECT, Complex expressions
-- =============================================================================

CREATE TABLE sales_analysis AS
SELECT 
    p.product_id,
    p.product_name,
    p.category,
    
    -- Subquery in SELECT (scalar subquery)
    (SELECT AVG(quantity) 
     FROM order_items oi 
     WHERE oi.product_id = p.product_id) as avg_quantity_sold,
    
    -- Expression using subquery result
    (SELECT SUM(quantity * unit_price) 
     FROM order_items oi 
     WHERE oi.product_id = p.product_id) as total_revenue,
    
    -- Another calculated field
    (SELECT COUNT(DISTINCT order_id) 
     FROM order_items oi 
     WHERE oi.product_id = p.product_id) as times_ordered,
    
    -- Derived field using multiple sources
    p.list_price,
    (SELECT AVG(unit_price) 
     FROM order_items oi 
     WHERE oi.product_id = p.product_id) as avg_selling_price,
    
    p.list_price - (SELECT AVG(unit_price) 
                    FROM order_items oi 
                    WHERE oi.product_id = p.product_id) as avg_discount
FROM products p
WHERE p.product_id IN (
    -- Subquery in WHERE
    SELECT DISTINCT product_id
    FROM order_items
    WHERE order_date >= '2024-01-01'
);

-- Trace these fields:
-- - sales_analysis.total_revenue → Scalar subquery with expression
-- - sales_analysis.avg_discount → Expression combining multiple subqueries

-- =============================================================================
-- Example 4: Multi-Source Revenue Report
-- Demonstrates: CTE, UNION ALL, Multiple aggregates, Complex GROUP BY
-- =============================================================================

WITH 
-- Online sales
online_sales AS (
    SELECT 
        product_id,
        order_date,
        quantity,
        unit_price,
        quantity * unit_price as revenue,
        'online' as channel
    FROM online_orders
    WHERE status = 'completed'
),

-- Store sales
store_sales AS (
    SELECT 
        product_id,
        sale_date as order_date,
        quantity,
        sale_price as unit_price,
        quantity * sale_price as revenue,
        'store' as channel
    FROM store_transactions
    WHERE cancelled = false
),

-- Combined sales from all channels
all_sales AS (
    SELECT * FROM online_sales
    UNION ALL
    SELECT * FROM store_sales
),

-- Monthly aggregates
monthly_summary AS (
    SELECT 
        DATE_TRUNC('month', order_date) as month,
        product_id,
        channel,
        COUNT(*) as transaction_count,
        SUM(quantity) as total_quantity,
        SUM(revenue) as total_revenue,
        AVG(unit_price) as avg_price
    FROM all_sales
    GROUP BY DATE_TRUNC('month', order_date), product_id, channel
)

-- Final report with product details
CREATE TABLE revenue_report AS
SELECT 
    p.product_name,
    p.category,
    ms.month,
    ms.channel,
    ms.transaction_count,
    ms.total_quantity,
    ms.total_revenue,
    ms.avg_price,
    ms.total_revenue / NULLIF(ms.total_quantity, 0) as revenue_per_unit
FROM monthly_summary ms
JOIN products p ON ms.product_id = p.product_id;

-- Trace these fields:
-- - revenue_report.total_revenue → UNION of two sources, then aggregated
-- - revenue_report.revenue_per_unit → Calculated from aggregated fields

-- =============================================================================
-- Example 5: Nested Derived Tables with Multi-level Aggregation
-- Demonstrates: Nested subqueries, Aggregate of aggregates, Complex joins
-- =============================================================================

CREATE TABLE advanced_metrics AS
SELECT 
    daily.customer_id,
    c.customer_name,
    daily.avg_daily_spending,
    weekly.avg_weekly_orders,
    monthly.total_monthly_revenue,
    
    -- Calculated field using multiple aggregation levels
    monthly.total_monthly_revenue / NULLIF(daily.days_active, 0) as revenue_per_active_day
    
FROM (
    -- Daily aggregates
    SELECT 
        customer_id,
        COUNT(DISTINCT order_date) as days_active,
        AVG(daily_total) as avg_daily_spending
    FROM (
        -- Inner: Daily totals per customer
        SELECT 
            customer_id,
            order_date,
            SUM(order_amount) as daily_total
        FROM orders
        GROUP BY customer_id, order_date
    ) daily_orders
    GROUP BY customer_id
) daily

JOIN (
    -- Weekly aggregates
    SELECT 
        customer_id,
        AVG(weekly_orders) as avg_weekly_orders
    FROM (
        -- Inner: Weekly order counts
        SELECT 
            customer_id,
            DATE_TRUNC('week', order_date) as week,
            COUNT(*) as weekly_orders
        FROM orders
        GROUP BY customer_id, DATE_TRUNC('week', order_date)
    ) weekly_counts
    GROUP BY customer_id
) weekly ON daily.customer_id = weekly.customer_id

JOIN (
    -- Monthly aggregates
    SELECT 
        customer_id,
        SUM(order_amount) as total_monthly_revenue
    FROM orders
    WHERE order_date >= DATE_TRUNC('month', CURRENT_DATE)
    GROUP BY customer_id
) monthly ON daily.customer_id = monthly.customer_id

JOIN customers c ON daily.customer_id = c.customer_id;

-- Trace these fields:
-- - advanced_metrics.revenue_per_active_day → Three levels of aggregation
-- - advanced_metrics.avg_weekly_orders → Aggregate of aggregate

