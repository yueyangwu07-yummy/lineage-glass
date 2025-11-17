# Simple Data Transformation Example

A minimal example to get started with lineage-analyzer.

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

## Quick Start

```bash
lineage-analyzer transform.sql --trace user_summary.total_amount
```

**Note**: You may need to provide a schema file if source tables are not automatically detected.

## Expected Output

```
user_summary.total_amount <- user_totals.total_amount <- user_orders.amount <- orders.amount
```

This shows that `user_summary.total_amount` ultimately comes from `orders.amount`.
