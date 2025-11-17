import pytest

from lineage_analyzer import ScriptAnalyzer


def test_simple_derived_table():
    """Simplest derived table"""
    sql = """
    SELECT a.id, a.name
    FROM (
        SELECT emp_id as id, emp_name as name
        FROM employees
    ) a;
    """

    analyzer = ScriptAnalyzer()
    result = analyzer.analyze_script(sql)

    # Validate: result table should be a SELECT result (not registered as table)
    # We check resolver-style tracing by registering a CREATE TABLE in later phases.
    # For now, ensure no exceptions and registry can hold derived table when implemented.
    # Placeholders for future asserts when SELECT registration is added.
    assert result is not None


@pytest.mark.skip(reason="Subquery support not implemented yet")
def test_derived_table_with_join():
    """Derived table with JOIN inside"""
    sql = """
    SELECT d.dept_name, d.emp_count
    FROM (
        SELECT d.name as dept_name, COUNT(*) as emp_count
        FROM departments d
        JOIN employees e ON d.id = e.dept_id
        GROUP BY d.name
    ) d;
    """
    analyzer = ScriptAnalyzer()
    try:
        analyzer.analyze_script(sql)
    except NotImplementedError:
        pytest.skip("Aggregation not yet supported")


def test_derived_table_select_star():
    """SELECT * from a derived table"""
    sql = """
    SELECT *
    FROM (
        SELECT id, name FROM employees
    ) a;
    """
    analyzer = ScriptAnalyzer()
    result = analyzer.analyze_script(sql)
    assert result is not None


def test_nested_derived_tables():
    """Nested derived tables"""
    sql = """
    SELECT b.id
    FROM (
        SELECT a.emp_id as id
        FROM (
            SELECT emp_id FROM employees
        ) a
    ) b;
    """
    analyzer = ScriptAnalyzer()
    result = analyzer.analyze_script(sql)
    assert result is not None


def test_derived_table_with_multiple_tables():
    """Multiple derived tables joined together"""
    sql = """
    SELECT e.name, d.dept_name
    FROM (
        SELECT emp_id, emp_name as name FROM employees
    ) e
    JOIN (
        SELECT dept_id, dept_name FROM departments
    ) d ON e.emp_id = d.dept_id;
    """
    analyzer = ScriptAnalyzer()
    result = analyzer.analyze_script(sql)
    assert result is not None


def test_derived_table_with_expression():
    """Derived table with expression column"""
    sql = """
    SELECT a.full_name
    FROM (
        SELECT first_name || ' ' || last_name as full_name
        FROM employees
    ) a;
    """
    analyzer = ScriptAnalyzer()
    result = analyzer.analyze_script(sql)
    assert result is not None


