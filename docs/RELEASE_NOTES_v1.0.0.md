# Lineage Glass v1.0.0 - Production Ready 🎉

We're excited to announce the first production release of Lineage Glass, a powerful SQL field-level lineage analysis tool!

## 🎯 What's Lineage Glass?

Lineage Glass helps you understand your SQL data pipelines by tracing data lineage from source to target at the column level. Whether you're doing data governance, impact analysis, or documentation, Lineage Glass provides the insights you need.

## ✨ Key Features

### Comprehensive SQL Support

- ✅ **CTEs (Common Table Expressions)** - Regular & Recursive
- ✅ **Subqueries** - FROM, WHERE, HAVING, SELECT clauses
- ✅ **UNION/UNION ALL** - Complete support
- ✅ **Aggregate Functions** - GROUP BY, HAVING, SUM, AVG, MIN, MAX, COUNT
- ✅ **All JOIN types** - INNER, LEFT, RIGHT, FULL, CROSS
- ✅ **Expressions** - Arithmetic, functions, CASE statements

### Three Ways to Use

1. **🌐 Web UI** - Interactive visualization (NEW!)
   - Visual lineage graph
   - Search and filter
   - Export to JSON
   - Example SQL templates

2. **⌨️ CLI** - Command-line tool for automation
   - Trace columns
   - Impact analysis
   - JSON export

3. **🐍 Python API** - Programmatic integration
   - Type-safe API
   - Comprehensive result objects
   - Easy to integrate

### Production Quality

- **262+ comprehensive test cases**
- **90%+ SQL coverage** for common patterns
- **Clean, modular architecture**
- **Type-safe** with full annotations
- **Well-documented** with examples

## 🚀 Quick Start

### Web UI (Recommended for Exploration)

```bash
cd web_ui
pip install -r requirements.txt
python app.py

# Open http://localhost:5000
```

### CLI

```bash
pip install lineage-glass

lineage-analyze your_script.sql --trace table.column
```

### Python API

```python
from lineage_analyzer import ScriptAnalyzer

analyzer = ScriptAnalyzer()
result = analyzer.analyze_script(sql_text)

# Trace a field
paths = result.trace("table", "column")
for path in paths:
    print(path.to_string())
```

## 📊 Use Cases

- **Data Governance**: Trace data origins and ensure quality
- **Impact Analysis**: Assess effects of schema changes
- **Documentation**: Auto-generate lineage documentation
- **Code Review**: Understand complex SQL transformations
- **Compliance**: Track data lineage for regulatory requirements

## 📸 Screenshots

[Add screenshots here - see docs/screenshots/README.md for instructions]

## 🎓 Example

```sql
-- Analyze this SQL
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

Lineage Glass will show you:
- `dept_name` comes from `departments.name`
- `avg_salary` is computed from `employees.salary` via AVG aggregation
- `emp_count` is a COUNT(*) from `employees` table
- All dependencies are traced through the CTE

## 🐛 Known Limitations

- Window functions not yet supported (coming in v1.1)
- UPDATE/DELETE statements not supported
- Some advanced SQL features may require workarounds

## 📝 Full Changelog

See [CHANGELOG.md](../CHANGELOG.md) for detailed changes.

## 🙏 Acknowledgments

Built with ❤️ for data engineers and analysts.

Special thanks to:
- The sqlglot project for excellent SQL parsing
- The open-source community for feedback and contributions

## 💬 Feedback

Found a bug? Have a feature request? [Open an issue](https://github.com/yourusername/lineage-glass/issues)!

## 📄 License

MIT License - See [LICENSE](../LICENSE) file

---

**Download**: [GitHub Releases](https://github.com/yourusername/lineage-glass/releases/tag/v1.0.0)
**Documentation**: [README.md](../README.md)
**Changelog**: [CHANGELOG.md](../CHANGELOG.md)

