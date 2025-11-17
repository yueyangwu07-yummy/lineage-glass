-- Simple Data Transformation Example
-- Perfect for quick start

-- Step 1: Extract user orders
CREATE TABLE user_orders AS
SELECT 
    user_id,
    order_id,
    amount
FROM orders;

-- Step 2: Select user orders (with total amount)
CREATE TABLE user_totals AS
SELECT 
    user_id,
    amount AS total_amount,
    order_id
FROM user_orders;

-- Step 3: Add user names
CREATE TABLE user_summary AS
SELECT 
    u.name,
    ut.total_amount,
    ut.order_id
FROM users u
JOIN user_totals ut ON u.id = ut.user_id;

