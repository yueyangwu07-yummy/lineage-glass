# Changelog

All notable changes to Lineage Glass will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-01-XX

### 🎉 Major Release: Production Ready

#### Core Features

- **Complete SQL Support**
  - CTEs (Common Table Expressions) - Regular and Recursive
  - Subqueries in FROM, WHERE, HAVING, SELECT clauses
  - UNION/UNION ALL operations
  - Aggregate functions with GROUP BY and HAVING
  - All JOIN types (INNER, LEFT, RIGHT, FULL, CROSS)

- **Field-Level Lineage Tracking**
  - Trace individual columns from target to source
  - Support for expressions and transformations
  - Transitive dependency resolution
  - Multi-source column tracking

- **Aggregate Function Support**
  - SUM, AVG, MIN, MAX, COUNT
  - Single and multi-column GROUP BY
  - Expression-based GROUP BY (e.g., `GROUP BY YEAR(date)`)
  - HAVING clause support
  - COUNT(*) and COUNT(DISTINCT) special handling
  - Alias references in GROUP BY and HAVING

#### Interfaces

- **Web UI**
  - Interactive lineage graph visualization with Cytoscape.js
  - Search and filter functionality
  - Export to JSON
  - Example SQL templates
  - Responsive design with Tailwind CSS
  - Table and column detail panels

- **Command Line Tool**
  - Analyze SQL scripts
  - Trace specific columns
  - Impact analysis
  - JSON export
  - Colored output

- **Python API**
  - Programmatic access
  - Integration friendly
  - Type-safe with annotations
  - Comprehensive result objects

#### Testing & Quality

- 262+ test cases covering core features and edge cases
- Comprehensive documentation
- Clean, modular architecture
- Type annotations throughout

#### Performance

- Small scripts (<10 statements): <1 second
- Medium scripts (10-50 statements): 1-5 seconds
- Large scripts (50-200 statements): 5-30 seconds

#### Known Limitations

- Window functions not yet supported (planned for v1.1)
- UPDATE/DELETE statements not supported
- Some advanced SQL features may require workarounds

---

## Upcoming in v1.1

### Planned Features

- Window functions (ROW_NUMBER, RANK, DENSE_RANK, etc.)
- Enhanced Web UI (more layouts, filters, dark mode)
- Performance optimizations for large scripts
- More database dialects support
- Column-level graph visualization

---

## Previous Versions

### v0.1.0 - Initial Release

**Basic Features**
- Basic SELECT statement analysis
- Single-SQL lineage extraction
- Simple column tracking

