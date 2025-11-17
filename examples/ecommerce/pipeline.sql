-- E-commerce Data Pipeline Example
-- Demonstrates: CREATE TABLE AS + INSERT INTO + Multi-level dependencies

-- Step 1: Clean raw order data
CREATE TABLE clean_orders AS
SELECT 
    order_id,
    customer_id,
    amount,
    tax,
    amount + tax AS total,
    order_date
FROM raw_orders
WHERE status = 'completed';

-- Step 2: Append new orders (incremental load)
INSERT INTO clean_orders
SELECT 
    order_id,
    customer_id,
    amount,
    tax,
    amount + tax AS total,
    order_date
FROM raw_orders_incremental
WHERE status = 'completed';

-- Step 3: Calculate order features (keep all orders, no aggregation)
CREATE TABLE order_features AS
SELECT 
    order_id,
    customer_id,
    total,
    total AS order_value,  -- Direct use of total
    order_date
FROM clean_orders;

-- Step 4: Generate user report (one row per order)
CREATE TABLE user_report AS
SELECT 
    c.name,
    c.email,
    of.order_id,
    of.total,
    of.order_value,
    CASE 
        WHEN of.total > 1000 THEN 'VIP'
        WHEN of.total > 500 THEN 'Regular'
        ELSE 'New'
    END AS customer_tier
FROM customers c
JOIN order_features of ON c.customer_id = of.customer_id;

-- Step 5: Generate sales dashboard (one row per order)
CREATE TABLE sales_dashboard AS
SELECT 
    order_date AS sales_date,
    customer_id,
    total AS daily_revenue,
    total AS order_value
FROM clean_orders;

