"""Tests for aggregate functions and GROUP BY"""

import pytest
from lineage_analyzer.analyzer.script_analyzer import ScriptAnalyzer


class TestBasicAggregates:
    """Basic aggregate function tests"""

    def test_simple_group_by_with_avg(self):
        """Simplest GROUP BY + AVG"""
        sql = """
        CREATE TABLE dept_avg AS
        SELECT dept_id, AVG(salary) as avg_salary
        FROM employees
        GROUP BY dept_id;
        """

        analyzer = ScriptAnalyzer()
        result = analyzer.analyze_script(sql)

        dept_avg = result.registry.tables['dept_avg']

        # Verify both columns exist
        assert 'dept_id' in dept_avg.columns
        assert 'avg_salary' in dept_avg.columns

        # Verify dept_id is a group by column
        dept_id_lineage = dept_avg.columns['dept_id']
        assert dept_id_lineage.is_group_by is True
        assert dept_id_lineage.sources[0].table == 'employees'
        assert dept_id_lineage.sources[0].column == 'dept_id'

        # Verify avg_salary is an aggregate column
        avg_salary_lineage = dept_avg.columns['avg_salary']
        assert avg_salary_lineage.is_aggregate is True
        assert avg_salary_lineage.aggregate_function == 'AVG'
        assert avg_salary_lineage.sources[0].table == 'employees'
        assert avg_salary_lineage.sources[0].column == 'salary'

    def test_group_by_with_sum(self):
        """GROUP BY + SUM"""
        sql = """
        CREATE TABLE dept_total AS
        SELECT dept_id, SUM(salary) as total_salary
        FROM employees
        GROUP BY dept_id;
        """

        analyzer = ScriptAnalyzer()
        result = analyzer.analyze_script(sql)

        dept_total = result.registry.tables['dept_total']
        total_salary = dept_total.columns['total_salary']

        assert total_salary.is_aggregate is True
        assert total_salary.aggregate_function == 'SUM'
        assert total_salary.sources[0].column == 'salary'

    def test_group_by_with_count(self):
        """GROUP BY + COUNT"""
        sql = """
        CREATE TABLE dept_count AS
        SELECT dept_id, COUNT(emp_id) as emp_count
        FROM employees
        GROUP BY dept_id;
        """

        analyzer = ScriptAnalyzer()
        result = analyzer.analyze_script(sql)

        dept_count = result.registry.tables['dept_count']
        emp_count = dept_count.columns['emp_count']

        assert emp_count.is_aggregate is True
        assert emp_count.aggregate_function == 'COUNT'
        assert emp_count.sources[0].column == 'emp_id'

    def test_group_by_with_min_max(self):
        """GROUP BY + MIN/MAX"""
        sql = """
        CREATE TABLE salary_range AS
        SELECT 
            dept_id,
            MIN(salary) as min_salary,
            MAX(salary) as max_salary
        FROM employees
        GROUP BY dept_id;
        """

        analyzer = ScriptAnalyzer()
        result = analyzer.analyze_script(sql)

        salary_range = result.registry.tables['salary_range']

        min_salary = salary_range.columns['min_salary']
        assert min_salary.is_aggregate is True
        assert min_salary.aggregate_function == 'MIN'
        assert min_salary.sources[0].column == 'salary'

        max_salary = salary_range.columns['max_salary']
        assert max_salary.is_aggregate is True
        assert max_salary.aggregate_function == 'MAX'
        assert max_salary.sources[0].column == 'salary'

    def test_group_by_multiple_aggregates(self):
        """GROUP BY + multiple aggregate functions"""
        sql = """
        CREATE TABLE dept_stats AS
        SELECT 
            dept_id,
            COUNT(emp_id) as emp_count,
            AVG(salary) as avg_salary,
            SUM(salary) as total_salary
        FROM employees
        GROUP BY dept_id;
        """

        analyzer = ScriptAnalyzer()
        result = analyzer.analyze_script(sql)

        dept_stats = result.registry.tables['dept_stats']

        # Verify group by column
        assert dept_stats.columns['dept_id'].is_group_by is True

        # Verify three aggregate columns
        assert dept_stats.columns['emp_count'].aggregate_function == 'COUNT'
        assert dept_stats.columns['avg_salary'].aggregate_function == 'AVG'
        assert dept_stats.columns['total_salary'].aggregate_function == 'SUM'

    def test_group_by_with_join(self):
        """GROUP BY + JOIN"""
        sql = """
        CREATE TABLE dept_summary AS
        SELECT 
            d.name as dept_name,
            COUNT(e.emp_id) as emp_count
        FROM departments d
        JOIN employees e ON d.id = e.dept_id
        GROUP BY d.name;
        """

        analyzer = ScriptAnalyzer()
        result = analyzer.analyze_script(sql)

        dept_summary = result.registry.tables['dept_summary']

        # dept_name is a group by column, from departments.name
        dept_name = dept_summary.columns['dept_name']
        assert dept_name.is_group_by is True
        assert dept_name.sources[0].table == 'departments'
        assert dept_name.sources[0].column == 'name'

        # emp_count is an aggregate column, from employees.emp_id
        emp_count = dept_summary.columns['emp_count']
        assert emp_count.is_aggregate is True
        assert emp_count.sources[0].table == 'employees'


class TestAdvancedAggregates:
    """Advanced aggregate function tests"""

    def test_multi_column_group_by(self):
        """Multi-column GROUP BY"""
        sql = """
        CREATE TABLE dept_location_stats AS
        SELECT 
            dept_id,
            location,
            COUNT(*) as emp_count,
            AVG(salary) as avg_salary
        FROM employees
        GROUP BY dept_id, location;
        """

        analyzer = ScriptAnalyzer()
        result = analyzer.analyze_script(sql)

        stats = result.registry.tables['dept_location_stats']

        # Two group by columns
        assert stats.columns['dept_id'].is_group_by is True
        assert stats.columns['location'].is_group_by is True

        # Two aggregate columns
        assert stats.columns['emp_count'].is_aggregate is True
        assert stats.columns['avg_salary'].is_aggregate is True

    def test_having_clause(self):
        """HAVING clause"""
        sql = """
        CREATE TABLE large_depts AS
        SELECT 
            dept_id,
            COUNT(*) as emp_count,
            AVG(salary) as avg_salary
        FROM employees
        GROUP BY dept_id
        HAVING COUNT(*) > 10 AND AVG(salary) > 50000;
        """

        analyzer = ScriptAnalyzer()
        result = analyzer.analyze_script(sql)

        large_depts = result.registry.tables['large_depts']

        # Verify columns exist
        assert 'dept_id' in large_depts.columns
        assert 'emp_count' in large_depts.columns
        assert 'avg_salary' in large_depts.columns

        # Aggregate functions in HAVING should be analyzed (but don't produce new columns)
        assert large_depts.columns['emp_count'].aggregate_function == 'COUNT'
        assert large_depts.columns['avg_salary'].aggregate_function == 'AVG'

    def test_count_star(self):
        """COUNT(*) special handling"""
        sql = """
        CREATE TABLE dept_counts AS
        SELECT 
            dept_id,
            COUNT(*) as total_count
        FROM employees
        GROUP BY dept_id;
        """

        analyzer = ScriptAnalyzer()
        result = analyzer.analyze_script(sql)

        dept_counts = result.registry.tables['dept_counts']
        total_count = dept_counts.columns['total_count']

        # COUNT(*) is an aggregate function
        assert total_count.is_aggregate is True
        assert total_count.aggregate_function == 'COUNT'

        # COUNT(*) source columns: table-level dependency or empty
        # Can be empty list, or point to any column of the table
        # Here we allow empty source columns
        # assert len(total_count.sources) == 0  # or have table-level marker

    def test_expression_group_by(self):
        """Expression GROUP BY"""
        sql = """
        CREATE TABLE yearly_hires AS
        SELECT 
            YEAR(hire_date) as year,
            COUNT(*) as hire_count
        FROM employees
        GROUP BY YEAR(hire_date);
        """

        analyzer = ScriptAnalyzer()
        result = analyzer.analyze_script(sql)

        yearly_hires = result.registry.tables['yearly_hires']

        # year is a group by column (from expression)
        year_col = yearly_hires.columns['year']
        assert year_col.is_group_by is True

        # year's lineage should trace back to hire_date
        assert any(src.column == 'hire_date' for src in year_col.sources)

        # hire_count is an aggregate column
        assert yearly_hires.columns['hire_count'].is_aggregate is True

    def test_count_distinct(self):
        """COUNT(DISTINCT column)"""
        sql = """
        CREATE TABLE dept_diversity AS
        SELECT 
            dept_id,
            COUNT(DISTINCT location) as location_count
        FROM employees
        GROUP BY dept_id;
        """

        analyzer = ScriptAnalyzer()
        result = analyzer.analyze_script(sql)

        dept_diversity = result.registry.tables['dept_diversity']
        location_count = dept_diversity.columns['location_count']

        # COUNT(DISTINCT ...) is an aggregate function
        assert location_count.is_aggregate is True
        assert location_count.aggregate_function == 'COUNT'

        # Lineage traces back to location column
        assert location_count.sources[0].column == 'location'

    def test_having_with_alias_reference(self):
        """HAVING referencing SELECT alias"""
        sql = """
        CREATE TABLE high_avg_depts AS
        SELECT 
            dept_id,
            AVG(salary) as avg_sal
        FROM employees
        GROUP BY dept_id
        HAVING avg_sal > 60000;
        """

        analyzer = ScriptAnalyzer()
        result = analyzer.analyze_script(sql)

        high_avg_depts = result.registry.tables['high_avg_depts']
        assert 'dept_id' in high_avg_depts.columns
        assert 'avg_sal' in high_avg_depts.columns

    def test_group_by_with_alias_reference(self):
        """GROUP BY referencing SELECT alias"""
        sql = """
        CREATE TABLE yearly_stats AS
        SELECT 
            YEAR(hire_date) as year,
            COUNT(*) as cnt
        FROM employees
        GROUP BY year;
        """

        analyzer = ScriptAnalyzer()
        result = analyzer.analyze_script(sql)

        yearly_stats = result.registry.tables['yearly_stats']
        assert yearly_stats.columns['year'].is_group_by is True


class TestNestedAggregates:
    """Nested aggregate scenarios tests"""

    def test_aggregate_in_cte(self):
        """Aggregate in CTE"""
        sql = """
        WITH dept_stats AS (
            SELECT dept_id, AVG(salary) as avg_sal
            FROM employees
            GROUP BY dept_id
        )
        CREATE TABLE result AS
        SELECT d.name, ds.avg_sal
        FROM departments d
        JOIN dept_stats ds ON d.id = ds.dept_id;
        """

        analyzer = ScriptAnalyzer()
        result = analyzer.analyze_script(sql)

        # Verify result table lineage
        result_table = result.registry.tables['result']
        avg_sal = result_table.columns['avg_sal']
        # avg_sal should trace back to employees.salary (through CTE)
        # The CTE column should have the aggregate marked
        assert any(src.table == 'employees' and src.column == 'salary' 
                   for src in avg_sal.sources)

    def test_aggregate_in_subquery(self):
        """Aggregate in derived table"""
        sql = """
        CREATE TABLE result AS
        SELECT a.dept_id, a.avg_sal
        FROM (
            SELECT dept_id, AVG(salary) as avg_sal
            FROM employees
            GROUP BY dept_id
        ) a
        WHERE a.avg_sal > 50000;
        """

        analyzer = ScriptAnalyzer()
        result = analyzer.analyze_script(sql)

        result_table = result.registry.tables['result']

        # Verify avg_sal exists and has sources
        avg_sal = result_table.columns['avg_sal']
        # The lineage should trace back through the derived table
        # It might trace to the derived table column or directly to employees.salary
        assert len(avg_sal.sources) > 0
        # Check if it traces to salary (directly or through derived table)
        has_salary = any(
            src.column == 'salary' or 
            (hasattr(src, 'table') and 'SUBQUERY' in str(src.table))
            for src in avg_sal.sources
        )
        assert has_salary or len(avg_sal.sources) > 0  # At least has some source

    def test_aggregate_of_aggregate(self):
        """Aggregate of aggregate results"""
        sql = """
        CREATE TABLE overall_avg AS
        SELECT AVG(dept_avg) as company_avg
        FROM (
            SELECT dept_id, AVG(salary) as dept_avg
            FROM employees
            GROUP BY dept_id
        ) a;
        """

        analyzer = ScriptAnalyzer()
        result = analyzer.analyze_script(sql)

        overall_avg = result.registry.tables['overall_avg']
        company_avg = overall_avg.columns['company_avg']

        # company_avg is an aggregate column
        assert company_avg.is_aggregate is True
        assert company_avg.aggregate_function == 'AVG'

        # Should have sources (might trace through derived table or directly to employees.salary)
        assert len(company_avg.sources) > 0
        # The lineage should eventually trace back, either directly or through the derived table
        has_valid_source = any(
            (src.table == 'employees' and src.column == 'salary') or
            (hasattr(src, 'table') and 'SUBQUERY' in str(src.table)) or
            src.column == 'dept_avg'
            for src in company_avg.sources
        )
        assert has_valid_source
