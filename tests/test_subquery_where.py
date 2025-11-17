"""Tests for subqueries in WHERE/HAVING clauses"""

import pytest
from lineage_analyzer.analyzer.script_analyzer import ScriptAnalyzer
from lineage_analyzer.models.config import LineageConfig


class TestWhereSubquery:

    def test_simple_scalar_subquery_noncorrelated(self):
        """Simplest non-correlated scalar subquery"""
        sql = """
        CREATE TABLE high_earners AS
        SELECT emp_id, name, salary
        FROM employees
        WHERE salary > (SELECT AVG(salary) FROM employees);
        """

        analyzer = ScriptAnalyzer()
        result = analyzer.analyze_script(sql)

        high_earners = result.registry.tables['high_earners']
        assert 'emp_id' in high_earners.columns
        assert 'name' in high_earners.columns

        # Lineage should directly point to employees
        assert high_earners.columns['emp_id'].sources[0].table == 'employees'
        assert high_earners.columns['name'].sources[0].table == 'employees'

    def test_scalar_subquery_different_table(self):
        """Subquery references different table"""
        sql = """
        CREATE TABLE eng_employees AS
        SELECT e.emp_id, e.name
        FROM employees e
        WHERE e.dept_id = (
            SELECT d.id 
            FROM departments d 
            WHERE d.name = 'Engineering'
        );
        """

        analyzer = ScriptAnalyzer()
        result = analyzer.analyze_script(sql)

        eng_employees = result.registry.tables['eng_employees']
        assert eng_employees.columns['emp_id'].sources[0].table == 'employees'

    def test_correlated_subquery_simple(self):
        """Correlated subquery: references outer table"""
        sql = """
        CREATE TABLE above_dept_avg AS
        SELECT e.emp_id, e.name, e.salary
        FROM employees e
        WHERE e.salary > (
            SELECT AVG(e2.salary)
            FROM employees e2
            WHERE e2.dept_id = e.dept_id
        );
        """

        analyzer = ScriptAnalyzer()
        result = analyzer.analyze_script(sql)

        table = result.registry.tables['above_dept_avg']
        assert table.columns['emp_id'].sources[0].table == 'employees'

    def test_multiple_subqueries_in_where(self):
        """Multiple subqueries in WHERE"""
        sql = """
        CREATE TABLE filtered AS
        SELECT name
        FROM employees
        WHERE salary > (SELECT AVG(salary) FROM employees)
          AND dept_id IN (
              SELECT id 
              FROM departments 
              WHERE location = 'NY'
          );
        """

        analyzer = ScriptAnalyzer()
        result = analyzer.analyze_script(sql)

        filtered = result.registry.tables['filtered']
        assert filtered.columns['name'].sources[0].table == 'employees'

    def test_nested_subquery_in_where(self):
        """Nested subquery"""
        sql = """
        CREATE TABLE result AS
        SELECT name
        FROM employees
        WHERE dept_id IN (
            SELECT dept_id
            FROM departments
            WHERE manager_id IN (
                SELECT emp_id
                FROM employees
                WHERE title = 'Senior Manager'
            )
        );
        """

        analyzer = ScriptAnalyzer()
        result = analyzer.analyze_script(sql)

        result_table = result.registry.tables['result']
        assert result_table.columns['name'].sources[0].table == 'employees'


class TestSubqueryInExpression:
    """Tests for subqueries in SELECT expressions"""

    def test_scalar_subquery_in_select_simple(self):
        """Simple scalar subquery in SELECT list"""
        sql = """
        CREATE TABLE result AS
        SELECT 
            e.emp_id,
            e.name,
            (SELECT d.name FROM departments d WHERE d.id = e.dept_id) as dept_name
        FROM employees e;
        """

        analyzer = ScriptAnalyzer()
        result = analyzer.analyze_script(sql)

        result_table = result.registry.tables['result']
        assert 'emp_id' in result_table.columns
        assert 'name' in result_table.columns
        assert 'dept_name' in result_table.columns

        # Lineage for emp_id and name
        assert result_table.columns['emp_id'].sources[0].table == 'employees'
        assert result_table.columns['name'].sources[0].table == 'employees'

        # dept_name lineage should trace back to departments.name
        dept_name_sources = result_table.columns['dept_name'].sources
        assert len(dept_name_sources) == 1
        assert dept_name_sources[0].table == 'departments'
        assert dept_name_sources[0].column == 'name'

    def test_multiple_subqueries_in_select(self):
        """Multiple subqueries in SELECT list"""
        sql = """
        CREATE TABLE result AS
        SELECT 
            e.emp_id,
            (SELECT d.name FROM departments d WHERE d.id = e.dept_id) as dept_name,
            (SELECT l.city FROM locations l WHERE l.id = e.location_id) as city
        FROM employees e;
        """

        # Use higher complexity limit for queries with subqueries
        config = LineageConfig(max_expression_nodes=5000)
        analyzer = ScriptAnalyzer(config=config)
        result = analyzer.analyze_script(sql)

        result_table = result.registry.tables['result']
        assert 'dept_name' in result_table.columns
        assert 'city' in result_table.columns

        # Verify lineage for both subquery columns
        assert result_table.columns['dept_name'].sources[0].table == 'departments'
        assert result_table.columns['city'].sources[0].table == 'locations'

    def test_subquery_in_select_with_expression(self):
        """Subquery as part of an expression"""
        sql = """
        CREATE TABLE result AS
        SELECT 
            e.name,
            e.salary + (SELECT AVG(salary) FROM employees) as adjusted_salary
        FROM employees e;
        """

        analyzer = ScriptAnalyzer()
        result = analyzer.analyze_script(sql)

        result_table = result.registry.tables['result']
        assert 'adjusted_salary' in result_table.columns

        # adjusted_salary lineage should include employees.salary
        sources = result_table.columns['adjusted_salary'].sources
        assert any(s.table == 'employees' and s.column == 'salary' for s in sources)

    def test_nested_subquery_in_select(self):
        """Nested subquery in SELECT"""
        sql = """
        CREATE TABLE result AS
        SELECT 
            e.name,
            (
                SELECT d.name 
                FROM departments d 
                WHERE d.id = (
                    SELECT dept_id 
                    FROM assignments a 
                    WHERE a.emp_id = e.emp_id 
                    LIMIT 1
                )
            ) as dept_name
        FROM employees e;
        """

        # Use higher complexity limit for nested subqueries
        config = LineageConfig(max_expression_nodes=20000)
        analyzer = ScriptAnalyzer(config=config)
        result = analyzer.analyze_script(sql)

        result_table = result.registry.tables['result']
        assert 'dept_name' in result_table.columns

        # dept_name should trace back to departments.name and assignments.dept_id
        sources = result_table.columns['dept_name'].sources
        tables = {s.table for s in sources}
        assert 'departments' in tables

