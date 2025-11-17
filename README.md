# Lineage Glass v1.0.0

A powerful Python tool for analyzing field-level data lineage in SQL scripts. Trace any field from its final destination back to its original source tables.

## 🚀 Features

### Core Capabilities

- ✅ **CTE (Common Table Expressions)** - Regular and recursive CTEs
- ✅ **UNION/UNION ALL** - Combined with CTE support
- ✅ **Subqueries** - FROM, WHERE, HAVING, SELECT clauses
- ✅ **Aggregate Functions** - SUM, AVG, MIN, MAX, COUNT with GROUP BY and HAVING
- ✅ **CREATE TABLE AS** support
- ✅ **INSERT INTO SELECT** support
- ✅ **End-to-end lineage tracing** across multiple statements
- ✅ **Impact analysis** - find all downstream dependencies
- ✅ **Calculation explanation** - understand how fields are computed
- ✅ **Multi-table JOIN** support (INNER, LEFT, RIGHT, FULL, CROSS)
- ✅ **Arithmetic expressions** (+, -, *, /)
- ✅ **Function calls** (UPPER, LENGTH, etc.)
- ✅ **CASE expressions**
- ✅ **Column aliases**

### What's New in v1.0.0

- 🎯 **CTE Support** - Full support for WITH clauses, including recursive CTEs
- 🔄 **UNION Operations** - UNION and UNION ALL support within CTEs
- 📋 **Subqueries** - Complete support for subqueries in all clauses
- 🎨 **Interactive Web UI** - Visual lineage graph with search and export
- 📊 **Aggregate Functions** - Full GROUP BY and HAVING support
- 🔗 **Transitive lineage** - trace fields through multiple table transformations
- 📊 **Impact analysis** - see what breaks when you change a column

## 📦 Installation

```bash
pip install lineage-analyzer
```

Or install from source:

```bash
git clone https://github.com/yourusername/lineage-glass
cd lineage-glass
pip install -e .
```

## 📸 Screenshots

### Web UI

![Input Interface](docs/screenshots/input.png)
*Input SQL via text or file upload*

![Lineage Graph](docs/screenshots/graph.png)
*Interactive lineage graph visualization*

![Details Panel](docs/screenshots/details.png)
*Detailed column lineage information*

## 🎯 Quick Start

### Option 1: Web UI (Recommended for Exploration)

```bash
cd web_ui
pip install -r requirements.txt
python app.py

# Open http://localhost:5000 in your browser
```

**Interactive web interface features:**
- 📝 Input SQL via paste or file upload
- 🔗 Visual lineage graph with Cytoscape.js
- 🔍 Search tables and columns
- 💾 Export to JSON
- 📊 Detailed column lineage view

### Option 2: Command Line (Recommended for Automation)

```bash
# Analyze a SQL script
lineage-analyze script.sql

# Trace a field to its sources
lineage-analyze script.sql --trace report.revenue
```

### Option 3: Python API (Recommended for Integration)

```python
from lineage_analyzer import ScriptAnalyzer

analyzer = ScriptAnalyzer()
result = analyzer.analyze_script(sql_text)

# Trace a field
paths = result.trace("table", "column")
```

**Example output:**

```
✓ Found 1 lineage path(s):

  report.revenue ← feature_sales.total ← clean_orders.amount ← raw_orders.amount
  Hops: 3
  Source: raw_orders.amount
```

### Export to JSON

```bash
# Export full analysis to JSON
lineage-analyze script.sql --export-json output.json
```

### Impact Analysis

```bash
# Find all fields affected by orders.amount
lineage-analyze script.sql --impact orders.amount
```

**Example output:**

```
✓ Found 5 affected field(s):

clean_orders:
  • amount
  • total

feature_sales:
  • total
  • revenue

report:
  • revenue
```

### Explain Calculation

```bash
# Understand how a field is calculated
lineage-analyzer script.sql --explain dashboard.total_sales
```

**Example output:**

```
Calculation chain for dashboard.total_sales:
============================================================
dashboard.total_sales = feature_sales.revenue * 1.1 (computed)
  ↓
  feature_sales.revenue = clean_orders.amount + clean_orders.tax (computed)
    ↓
    clean_orders.amount = raw_orders.amount (direct)
      ↓
      raw_orders.amount (source)
```

## 📚 Usage Examples

### Analyze with Schema Validation

```bash
lineage-analyzer script.sql --schema schema.json --strict
```

**schema.json:**

```json
{
  "raw_orders": ["id", "amount", "tax", "customer_id"],
  "raw_customers": ["id", "name", "email"]
}
```

### Export Full Lineage Graph

```bash
lineage-analyzer script.sql --export lineage.json --format graph
```

### List All Tables

```bash
lineage-analyzer script.sql --list-tables
```

## 🐍 Python API

```python
from lineage_analyzer import ScriptAnalyzer, DictSchemaProvider

# Analyze a script
analyzer = ScriptAnalyzer()
result = analyzer.analyze_script("""
    CREATE TABLE t1 AS SELECT amount FROM orders;
    CREATE TABLE t2 AS SELECT amount * 2 AS doubled FROM t1;
""")

# Trace a field
paths = result.trace("t2", "doubled")
for path in paths:
    print(path.to_string())
    # Output: t2.doubled ← t1.amount ← orders.amount

# Impact analysis
impacts = result.impact("orders", "amount")
print(f"Affects {len(impacts)} fields")

# Explain calculation
explanation = result.explain("t2", "doubled")
print(explanation)
```

## 🎨 CLI Commands

| Command | Description |
|---------|-------------|
| `lineage-analyzer script.sql` | Analyze a SQL script |
| `--trace TABLE.COLUMN` | Trace a field to its sources |
| `--impact TABLE.COLUMN` | Find downstream dependencies |
| `--explain TABLE.COLUMN` | Explain calculation chain |
| `--list-tables` | List all tables in script |
| `--export FILE` | Export lineage graph |
| `--format [json\|table\|pretty\|graph]` | Output format |
| `--schema FILE` | Provide schema definitions |
| `--strict` | Enable strict mode (fail on ambiguity) |
| `--no-color` | Disable colored output |

## 🔧 Configuration

Create a `lineage.config.json`:

```json
{
  "strict_mode": true,
  "require_table_prefix": false,
  "schema_validation": true,
  "max_depth": 100
}
```

## 📖 Supported SQL Features

### Complete SQL Support (v1.0.0)

#### Basic Queries
- ✅ **SELECT** - Standard SELECT statements
- ✅ **CREATE TABLE AS** - Create tables from SELECT queries
- ✅ **INSERT INTO SELECT** - Insert data from SELECT queries

#### CTE (Common Table Expressions)
- ✅ **Regular CTE** - WITH clause with single or multiple CTEs
- ✅ **Recursive CTE** - WITH RECURSIVE for hierarchical data
- ✅ **CTE with UNION** - CTEs containing UNION/UNION ALL operations
- ✅ **Nested CTE** - CTEs referencing other CTEs

#### UNION Operations
- ✅ **UNION** - Combined with CTE support
- ✅ **UNION ALL** - Combined with CTE support

#### Subqueries
- ✅ **Derived Tables** - Subqueries in FROM clause (including nested)
- ✅ **WHERE Subqueries** - Subqueries in WHERE clause
- ✅ **HAVING Subqueries** - Subqueries in HAVING clause
- ✅ **SELECT Subqueries** - Scalar subqueries in SELECT list

#### Aggregate Functions
- ✅ **GROUP BY** - Single and multi-column grouping
- ✅ **Expression GROUP BY** - GROUP BY with expressions (e.g., YEAR(date))
- ✅ **HAVING** - Filtering on aggregate results
- ✅ **Aggregate Functions** - SUM, AVG, MIN, MAX, COUNT
- ✅ **COUNT(*)** - Special handling for table-level counting
- ✅ **COUNT(DISTINCT)** - Distinct counting support
- ✅ **Alias References** - GROUP BY and HAVING can reference SELECT aliases

#### Expressions
- ✅ Direct columns
- ✅ Column aliases
- ✅ Arithmetic (+, -, *, /)
- ✅ Functions (UPPER, LOWER, COALESCE, etc.)
- ✅ CASE expressions
- ✅ CAST/CONVERT

#### Joins
- ✅ INNER JOIN
- ✅ LEFT/RIGHT/FULL OUTER JOIN
- ✅ CROSS JOIN

#### Not Yet Supported (Planned for v1.1)
- ❌ **Window functions** - ROW_NUMBER, RANK, etc. (planned)
- ❌ **UPDATE/DELETE statements** - Planned for future versions

## 🛠️ Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=lineage_analyzer

# Type checking
mypy lineage_analyzer

# Format code
black lineage_analyzer
```

## 📊 Performance

Typical performance on a modern laptop:

- Small scripts (< 10 statements): < 1 second
- Medium scripts (10-50 statements): 1-5 seconds
- Large scripts (50-200 statements): 5-30 seconds

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repo
2. Create a feature branch
3. Add tests for new features
4. Submit a pull request

## 📄 License

MIT License - see LICENSE file

## 🙏 Acknowledgments

Built with:

- [sqlglot](https://github.com/tobymao/sqlglot) - SQL parser
- [networkx](https://networkx.org/) - Graph algorithms
- [colorama](https://github.com/tartley/colorama) - Colored terminal output

## 📞 Support

- 🐛 Issues: https://github.com/yourusername/lineage-glass/issues
- 📖 Documentation: See [CHANGELOG.md](CHANGELOG.md) for detailed changes
- 💬 Discussions: GitHub Discussions

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details

## 🙏 Acknowledgments

Built with:
- [sqlglot](https://github.com/tobymao/sqlglot) - SQL parser
- [Cytoscape.js](https://js.cytoscape.org/) - Graph visualization
- [Flask](https://flask.palletsprojects.com/) - Web framework
- [Tailwind CSS](https://tailwindcss.com/) - CSS framework

---

**Made with ❤️ for data engineers everywhere**
