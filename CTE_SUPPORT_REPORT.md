# CTE Support Report

## Test Date

2024-12-19

## Test Results Summary

### Simple CTE

- **Status**: ✗ **Not Supported**
- **Description**: Standalone WITH CTE statements (WITH ... AS ... SELECT ...) are classified as `WITH_CTE` but not handled by ScriptAnalyzer. They fall into the "unsupported" branch and no tables are registered.

**Details**:
- Statement is correctly classified as `WITH_CTE`
- ScriptAnalyzer returns: `{'type': 'unsupported', 'success': False, 'statement_type': 'with_cte', 'message': 'Statement type with_cte is not supported'}`
- No tables are registered in the registry
- CTE tables (e.g., `tmp`) are not accessible via `result.get_table("tmp")`

### Multiple CTEs

- **Status**: ✗ **Not Supported**
- **Description**: Multiple CTEs in a single statement are not supported for the same reason as simple CTEs - WITH_CTE statements are not handled.

**Details**:
- Same behavior as simple CTE
- Multiple CTE definitions are not extracted or registered
- CTE dependencies between CTEs (e.g., `tmp2` depending on `tmp1`) cannot be tracked

### CTE + CREATE TABLE AS

- **Status**: ⚠️ **Partially Supported**
- **Description**: CTEs can be used within CREATE TABLE AS statements, but lineage tracing fails because CTE tables are registered as external source tables without column definitions.

**Details**:
- Statement is correctly classified as `CREATE_TABLE_AS`
- The final table (e.g., `result`) is created successfully
- CTE tables (e.g., `tmp`) are registered in the registry as `EXTERNAL` tables
- However, CTE tables have no column definitions (empty `columns` dict)
- The target table's columns correctly reference CTE columns (e.g., `doubled` sources include `tmp.amount`)
- **But lineage tracing fails** because `tmp.amount` doesn't exist in the registry (CTE columns are not registered)
- Result: `trace("result", "doubled")` returns 0 paths

**Example**:
```sql
WITH tmp AS (
    SELECT amount FROM orders
)
CREATE TABLE result AS
SELECT amount * 2 AS doubled FROM tmp;
```

- `result` table: ✅ Created
- `result.doubled` column: ✅ Has source `tmp.amount`
- `tmp` table: ✅ Registered as EXTERNAL
- `tmp.amount` column: ✗ Not registered
- Lineage trace: ✗ Fails (0 paths)

### Nested CTE

- **Status**: ✗ **Not Supported**
- **Description**: Nested CTEs (CTEs that reference other CTEs) are not supported for the same reason as simple CTEs.

**Details**:
- Same behavior as simple CTE
- CTE chains (e.g., `level3` → `level2` → `level1`) cannot be tracked
- All CTE tables return `None` when queried

## Discovered Issues

### Issue 1: WITH_CTE Statement Type Not Handled

**Error Type**: Unsupported Statement Type
**Error Message**: `Statement type with_cte is not supported`
**Impact**: Standalone WITH CTE statements are completely ignored

**Root Cause**: 
- `ScriptAnalyzer._analyze_statement()` does not have a case for `StatementType.WITH_CTE`
- It falls into the "unsupported" branch

**Location**: `lineage_analyzer/analyzer/script_analyzer.py:168-174`

### Issue 2: CTE Columns Not Registered in Registry

**Error Type**: Missing Column Definitions
**Error Message**: N/A (silent failure in lineage tracing)
**Impact**: Lineage tracing fails when CTEs are used in CREATE TABLE AS statements

**Root Cause**:
- When a CTE is used within CREATE TABLE AS, the CTE table is registered as an `EXTERNAL` source table
- However, the CTE's column definitions are not extracted or registered
- `ScopeBuilder` sees `tmp` as a table reference but doesn't know it's a CTE
- It registers `tmp` as an external table with empty columns
- When lineage tracing tries to resolve `tmp.amount`, it fails because `tmp` has no columns

**Location**: 
- `lineage_analyzer/analyzer/scope_builder.py` - CTE handling missing
- `lineage_analyzer/analyzer/create_table_analyzer.py` - CTE extraction not implemented

### Issue 3: CTE Definitions Not Extracted from WITH Clause

**Error Type**: Missing CTE Analysis
**Error Message**: N/A
**Impact**: CTE definitions are not analyzed, so their column lineage cannot be determined

**Root Cause**:
- The `WITH` clause is part of the SELECT statement AST
- `CreateTableAnalyzer` analyzes the entire query but doesn't extract CTE definitions
- CTE definitions need to be analyzed BEFORE the main query to register CTE tables with their columns

**Location**: `lineage_analyzer/analyzer/create_table_analyzer.py` - CTE extraction missing

## Current Limitations

1. **Standalone WITH CTE statements are not supported**
   - No analyzer handles `WITH_CTE` statement type
   - CTE tables are not registered
   - No lineage information is extracted

2. **CTE columns are not registered in the registry**
   - CTE tables are registered as external source tables
   - Column definitions are missing
   - Lineage tracing fails for CTE columns

3. **CTE definitions are not analyzed**
   - WITH clause is not parsed to extract CTE definitions
   - CTE SELECT statements are not analyzed
   - CTE column lineage cannot be determined

4. **CTE dependencies cannot be tracked**
   - CTEs that reference other CTEs cannot be analyzed
   - Dependency chains are broken

5. **No support for recursive CTEs**
   - Not tested, but likely not supported

## Recommended Next Steps

### If Completely Unsupported: Implement CTE Support

**Priority: High**

1. **Add WITH_CTE handler in ScriptAnalyzer**
   - Create a new analyzer or extend existing analyzers to handle `WITH_CTE` statements
   - Register CTE tables in the registry with `TableType.CTE`

2. **Extract CTE definitions from WITH clause**
   - Parse the `WITH` clause to extract CTE definitions
   - Each CTE has a name and a SELECT statement
   - Analyze each CTE's SELECT statement to determine column lineage

3. **Register CTE tables with column definitions**
   - Before analyzing the main query, analyze all CTE definitions
   - Register each CTE table in the registry with its column definitions
   - Mark CTE tables with `TableType.CTE`

4. **Handle CTE references in ScopeBuilder**
   - When `ScopeBuilder` encounters a table reference, check if it's a CTE
   - If it's a CTE, use the registered CTE table definition
   - Don't register CTEs as external source tables

5. **Support nested CTEs**
   - CTEs can reference other CTEs defined earlier in the same WITH clause
   - Analyze CTEs in order and register them before use

6. **Update CreateTableAnalyzer to handle CTEs**
   - Extract CTE definitions from the WITH clause
   - Analyze and register CTEs before analyzing the main SELECT
   - Ensure lineage tracing works through CTEs

### Implementation Details

**File: `lineage_analyzer/analyzer/cte_analyzer.py`** (new)
- `CTEAnalyzer` class to extract and analyze CTE definitions
- Methods to parse WITH clause and extract CTE definitions
- Methods to analyze CTE SELECT statements

**File: `lineage_analyzer/analyzer/script_analyzer.py`**
- Add case for `StatementType.WITH_CTE` in `_analyze_statement()`
- Call `CTEAnalyzer` to analyze CTE statements
- Register CTE tables in the registry

**File: `lineage_analyzer/analyzer/create_table_analyzer.py`**
- Extract CTE definitions from WITH clause (if present)
- Analyze and register CTEs before analyzing main SELECT
- Ensure CTE tables are available for lineage analysis

**File: `lineage_analyzer/analyzer/scope_builder.py`**
- Check registry for CTE tables before registering as external
- Use CTE table definitions when available

### Testing

- ✅ Test simple CTE
- ✅ Test multiple CTEs
- ✅ Test CTE + CREATE TABLE AS
- ✅ Test nested CTEs
- ⬜ Test recursive CTEs (if needed)
- ⬜ Test CTE with JOINs
- ⬜ Test CTE with expressions
- ⬜ Test CTE with subqueries

## Conclusion

**Current Status**: ⚠️ **Partially Supported**

- **Standalone WITH CTE statements**: ✗ Not supported
- **CTE + CREATE TABLE AS**: ⚠️ Partially supported (tables created but lineage tracing fails)
- **Multiple CTEs**: ✗ Not supported
- **Nested CTEs**: ✗ Not supported

**Recommendation**: Implement full CTE support to enable:
1. Standalone WITH CTE statement analysis
2. CTE column registration in the registry
3. Lineage tracing through CTEs
4. Nested CTE support

The foundation is there (CTE classification works, CREATE TABLE AS with CTE creates tables), but the missing piece is CTE definition extraction and column registration.

