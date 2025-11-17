# E-Commerce Data Pipeline Example

This example demonstrates a realistic e-commerce analytics pipeline.

## ⚠️ v1.0 Limitations

This example has been simplified to work with v1.0:

- ❌ Aggregate functions (SUM, COUNT, AVG) are not supported
- ❌ Window functions are not supported
- ❌ Subqueries are not supported

These features will be available in v1.1+

For now, the examples demonstrate:

- ✅ CREATE TABLE AS
- ✅ INSERT INTO SELECT
- ✅ Multi-table JOIN
- ✅ Arithmetic expressions
- ✅ CASE expressions
- ✅ Multi-hop lineage tracing

## Pipeline Overview

1. **Data Cleaning** (`clean_orders`)
   - Filter completed orders
   - Calculate total with tax

2. **Incremental Loading** (INSERT INTO)
   - Append new orders daily

3. **Feature Engineering** (`order_features`)
   - Extract order-level features
   - Direct column mapping (no aggregation in v1.0)

4. **Reporting** (`user_report`)
   - Join with customer data
   - Customer segmentation

5. **Dashboard** (`sales_dashboard`)
   - Order-level sales metrics

## How to Run

```bash
# Analyze the pipeline
lineage-analyzer pipeline.sql --schema schema.json

# Trace a field
lineage-analyzer pipeline.sql --schema schema.json --trace user_report.customer_tier

# Impact analysis
lineage-analyzer pipeline.sql --schema schema.json --impact raw_orders.amount

# Explain calculation
lineage-analyzer pipeline.sql --schema schema.json --explain sales_dashboard.daily_revenue
```

## Expected Results

### Trace: user_report.customer_tier

```
user_report.customer_tier <- order_features.total <- clean_orders.total <- raw_orders.amount
Hops: 3
```

### Impact: raw_orders.amount

Affects multiple downstream fields:
- clean_orders.amount
- clean_orders.total
- order_features.total
- order_features.order_value
- user_report.total
- user_report.order_value
- user_report.customer_tier
- sales_dashboard.daily_revenue
- sales_dashboard.order_value
