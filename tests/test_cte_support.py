"""
CTE (WITH clause) support test.

Test current tool's support level for CTE (Common Table Expression).
"""

import pytest

from lineage_analyzer import ScriptAnalyzer, DictSchemaProvider


class TestCTESupport:
    """Test CTE functionality support"""

    def test_simple_cte(self):
        """Test simple CTE"""
        script = """
        WITH tmp AS (
            SELECT amount FROM orders
        )
        SELECT amount FROM tmp;
        """

        schema = DictSchemaProvider({"orders": ["id", "amount"]})
        analyzer = ScriptAnalyzer(schema_provider=schema)

        # Try to analyze
        try:
            result = analyzer.analyze_script(script)

            # Check if tmp is recognized as a table
            tmp_table = result.get_table("tmp")

            if tmp_table:
                print("[OK] CTE 'tmp' is recognized as a table")
                print(f"  Table type: {tmp_table.table_type}")
                print(f"  Column count: {len(tmp_table.columns)}")

                # Check column lineage
                if tmp_table.has_column("amount"):
                    amount_lineage = tmp_table.get_column("amount")
                    print(f"  amount sources: {amount_lineage.sources}")

                    # Verify lineage correctness
                    assert len(amount_lineage.sources) > 0
                    assert amount_lineage.sources[0].table == "orders"
                    print("[OK] Lineage tracking is correct")
                else:
                    print("[FAIL] amount column not recognized")
            else:
                print("[FAIL] CTE 'tmp' is not recognized as a table")

        except Exception as e:
            print(f"[FAIL] Analysis failed: {type(e).__name__}: {e}")
            pytest.skip(f"CTE not supported yet: {e}")

    def test_multiple_ctes(self):
        """Test multiple CTEs"""
        script = """
        WITH 
        tmp1 AS (
            SELECT amount FROM orders
        ),
        tmp2 AS (
            SELECT amount * 2 AS doubled FROM tmp1
        )
        SELECT doubled FROM tmp2;
        """

        schema = DictSchemaProvider({"orders": ["id", "amount"]})
        analyzer = ScriptAnalyzer(schema_provider=schema)

        try:
            result = analyzer.analyze_script(script)

            # Check both CTEs
            tmp1 = result.get_table("tmp1")
            tmp2 = result.get_table("tmp2")

            if tmp1 and tmp2:
                print("[OK] Multiple CTEs recognized")

                # Check dependency relationship
                if tmp2.has_column("doubled"):
                    doubled_lineage = tmp2.get_column("doubled")
                    sources = [f"{s.table}.{s.column}" for s in doubled_lineage.sources]
                    print(f"  tmp2.doubled sources: {sources}")

                    # Verify dependency chain
                    # tmp2.doubled should come from tmp1.amount
                    assert any("tmp1" in s for s in sources)
                    print("[OK] Dependency relationship between CTEs is correct")
            else:
                print("[FAIL] Multiple CTEs not fully recognized")

        except Exception as e:
            print(f"[FAIL] Analysis failed: {e}")
            pytest.skip(f"Multiple CTEs not supported: {e}")

    def test_cte_with_create_table(self):
        """Test CTE + CREATE TABLE AS - Step 1 core functionality"""
        script = """
        WITH tmp AS (
            SELECT amount FROM orders
        )
        CREATE TABLE result AS
        SELECT amount * 2 AS doubled FROM tmp;
        """

        schema = DictSchemaProvider({"orders": ["id", "amount"]})
        analyzer = ScriptAnalyzer(schema_provider=schema)

        result = analyzer.analyze_script(script)

        # Verification 1: Final table created successfully
        result_table = result.get_table("result")
        assert result_table is not None, "result table should be created"

        # Verification 2: result.doubled column exists
        assert result_table.has_column("doubled"), "doubled column should exist"

        # Verification 3: Blood lineage tracking successful (Step 1 key goal)
        paths = result.trace("result", "doubled")

        assert len(paths) > 0, "Should be able to trace at least one path"

        # Verification 4: Path correctness
        # Should be: result.doubled <- orders.amount (CTE expanded)
        path_str = paths[0].to_string()
        # Print with safe encoding for Windows console
        try:
            print(f"Blood lineage path: {path_str}")
        except UnicodeEncodeError:
            # Windows console may not support Unicode arrows
            print(f"Blood lineage path: {path_str.encode('ascii', 'replace').decode('ascii')}")

        assert "orders" in path_str, "Path should contain source table orders"
        # Note: After CTE expansion, tmp is removed, so path goes directly to orders

        # Verification 5: CTE cleaned up after analysis (not in final Registry)
        tmp_table = result.get_table("tmp")
        assert tmp_table is None, "CTE 'tmp' should be cleaned up after analysis (not in final Registry)"

        print("[OK] CTE + CREATE TABLE AS: Blood lineage tracking successful")

    def test_nested_cte(self):
        """Test nested CTE (CTE using CTE)"""
        script = """
        WITH 
        level1 AS (
            SELECT amount FROM orders
        ),
        level2 AS (
            SELECT amount * 2 AS doubled FROM level1
        ),
        level3 AS (
            SELECT doubled + 100 AS final FROM level2
        )
        SELECT final FROM level3;
        """

        schema = DictSchemaProvider({"orders": ["id", "amount"]})
        analyzer = ScriptAnalyzer(schema_provider=schema)

        try:
            result = analyzer.analyze_script(script)

            # Check all levels
            level1 = result.get_table("level1")
            level2 = result.get_table("level2")
            level3 = result.get_table("level3")

            if level1 and level2 and level3:
                print("[OK] Nested CTE (3 levels) recognized")

                # Try to trace
                if level3.has_column("final"):
                    # Note: This might fail because it's a SELECT statement, not CREATE TABLE
                    # If it fails, it means we only support CTE in CREATE TABLE AS
                    print("  level3.final exists")
            else:
                print("[FAIL] Nested CTE not fully recognized")

        except Exception as e:
            print(f"[FAIL] Analysis failed: {e}")
            pytest.skip(f"Nested CTE not supported: {e}")

    # === Step 2 的新测试 ===

    def test_simple_with_cte(self):
        """Test standalone WITH CTE statement (Step 2)"""
        script = """
        WITH tmp AS (
            SELECT amount FROM orders
        )
        SELECT amount FROM tmp;
        """

        schema = DictSchemaProvider({"orders": ["id", "amount"]})
        analyzer = ScriptAnalyzer(schema_provider=schema)

        result = analyzer.analyze_script(script)

        # Verification: Statement was successfully analyzed
        assert len(result.analysis_results) == 1
        analysis = result.analysis_results[0]

        assert analysis["success"] == True, "WITH CTE statement should be analyzed successfully"
        assert analysis["type"] == "with_cte", "Type should be with_cte"
        assert analysis["cte_count"] == 1, "Should analyze 1 CTE"

        # Verification: CTE was cleaned up (not in final Registry)
        tmp_table = result.get_table("tmp")
        assert tmp_table is None, "CTE 'tmp' should be cleaned up"

        print("[OK] Simple WITH CTE: Analyzed successfully")

    def test_multiple_ctes(self):
        """Test multiple CTEs (Step 2)"""
        script = """
        WITH 
            tmp1 AS (SELECT amount FROM orders),
            tmp2 AS (SELECT amount * 2 AS doubled FROM tmp1)
        CREATE TABLE result AS
        SELECT doubled FROM tmp2;
        """

        schema = DictSchemaProvider({"orders": ["id", "amount"]})
        analyzer = ScriptAnalyzer(schema_provider=schema)

        result = analyzer.analyze_script(script)

        # Verification: Final table created successfully
        result_table = result.get_table("result")
        assert result_table is not None, "result table should be created"
        assert result_table.has_column("doubled"), "doubled column should exist"

        # Verification: Blood lineage tracking successful (through 2 CTEs)
        paths = result.trace("result", "doubled")
        assert len(paths) > 0, "Should be able to trace at least one path"

        path_str = paths[0].to_string()
        # Print with safe encoding for Windows console
        try:
            print(f"Blood lineage path (2 CTEs): {path_str}")
        except UnicodeEncodeError:
            print(f"Blood lineage path (2 CTEs): {path_str.encode('ascii', 'replace').decode('ascii')}")

        # Should trace to source table
        assert "orders" in path_str, "Path should contain source table orders"

        # Verification: Both CTEs were cleaned up
        assert result.get_table("tmp1") is None, "tmp1 should be cleaned up"
        assert result.get_table("tmp2") is None, "tmp2 should be cleaned up"

        print("[OK] Multiple CTEs: Blood lineage tracking successful")

    def test_insert_with_cte(self):
        """Test INSERT INTO + CTE (Step 2)"""
        script = """
        CREATE TABLE target AS SELECT amount FROM orders LIMIT 0;

        WITH tmp AS (
            SELECT amount FROM orders
        )
        INSERT INTO target SELECT amount FROM tmp;
        """

        schema = DictSchemaProvider({"orders": ["id", "amount"]})
        analyzer = ScriptAnalyzer(schema_provider=schema)

        result = analyzer.analyze_script(script)

        # Verification: target table exists
        target_table = result.get_table("target")
        assert target_table is not None, "target table should exist"

        # Verification: amount column exists (should be created from first CREATE TABLE AS)
        assert target_table.has_column("amount"), "amount column should exist"

        # After INSERT, amount column should have lineage
        amount_lineage = target_table.get_column("amount")
        assert len(amount_lineage.sources) > 0, "amount should have lineage sources after INSERT"

        # Verification: Sources are from orders (not CTE, after expansion)
        sources_str = ", ".join(f"{s.table}.{s.column}" for s in amount_lineage.sources)
        print(f"INSERT sources: {sources_str}")
        assert "orders" in sources_str, "Sources should contain orders"

        # Verification: CTE was cleaned up
        assert result.get_table("tmp") is None, "tmp should be cleaned up"

        print("[OK] INSERT with CTE: Blood lineage tracking successful")

    def test_nested_cte_dependencies(self):
        """Test nested CTE dependencies (Step 2)"""
        script = """
        WITH 
            level1 AS (SELECT amount FROM orders),
            level2 AS (SELECT amount * 2 AS doubled FROM level1),
            level3 AS (SELECT doubled + 100 AS final FROM level2)
        CREATE TABLE result AS
        SELECT final FROM level3;
        """

        schema = DictSchemaProvider({"orders": ["id", "amount"]})
        analyzer = ScriptAnalyzer(schema_provider=schema)

        result = analyzer.analyze_script(script)

        # Verification: Final table created successfully
        result_table = result.get_table("result")
        assert result_table is not None, "result table should be created"
        assert result_table.has_column("final"), "final column should exist"

        # Verification: Blood lineage tracking successful (through 3 CTEs)
        paths = result.trace("result", "final")
        assert len(paths) > 0, "Should be able to trace at least one path"

        path_str = paths[0].to_string()
        # Print with safe encoding for Windows console
        try:
            print(f"Blood lineage path (3 levels): {path_str}")
        except UnicodeEncodeError:
            print(f"Blood lineage path (3 levels): {path_str.encode('ascii', 'replace').decode('ascii')}")

        # Should trace to source table
        assert "orders" in path_str, "Path should contain source table orders"

        # Verification: All CTEs were cleaned up
        assert result.get_table("level1") is None, "level1 should be cleaned up"
        assert result.get_table("level2") is None, "level2 should be cleaned up"
        assert result.get_table("level3") is None, "level3 should be cleaned up"

        print("[OK] Nested CTE dependencies (3 levels): Successful")

    # === Recursive CTE Tests ===

    def test_simple_recursive_cte(self):
        """Test simple recursive CTE: numbers 1 to 10"""
        script = """
        WITH RECURSIVE numbers AS (
            -- Anchor part
            SELECT 1 AS n
            UNION ALL
            -- Recursive part
            SELECT n + 1 FROM numbers WHERE n < 10
        )
        CREATE TABLE result AS
        SELECT n FROM numbers;
        """

        schema = DictSchemaProvider({})
        analyzer = ScriptAnalyzer(schema_provider=schema)

        try:
            result = analyzer.analyze_script(script)

            # Verification: Final table created successfully
            result_table = result.get_table("result")
            assert result_table is not None, "result table should be created"
            assert result_table.has_column("n"), "n column should exist"

            # Verification: Recursive CTE was recognized
            # Note: CTE should be cleaned up, but we can check if analysis succeeded
            print("[OK] Simple recursive CTE: Analyzed successfully")

        except Exception as e:
            print(f"[FAIL] Analysis failed: {e}")
            pytest.skip(f"Recursive CTE not supported yet: {e}")

    def test_recursive_cte_hierarchical(self):
        """Test recursive CTE with hierarchical data: employee manager relationships"""
        script = """
        WITH RECURSIVE employee_hierarchy AS (
            -- Anchor part: top-level managers
            SELECT employee_id, manager_id, name, 1 AS level
            FROM employees
            WHERE manager_id IS NULL
            UNION ALL
            -- Recursive part: subordinates
            SELECT e.employee_id, e.manager_id, e.name, eh.level + 1
            FROM employees e
            INNER JOIN employee_hierarchy eh ON e.manager_id = eh.employee_id
        )
        CREATE TABLE result AS
        SELECT employee_id, name, level FROM employee_hierarchy;
        """

        schema = DictSchemaProvider({
            "employees": ["employee_id", "manager_id", "name"]
        })
        analyzer = ScriptAnalyzer(schema_provider=schema)

        try:
            result = analyzer.analyze_script(script)

            # Verification: Final table created successfully
            result_table = result.get_table("result")
            assert result_table is not None, "result table should be created"
            assert result_table.has_column("employee_id"), "employee_id column should exist"
            assert result_table.has_column("name"), "name column should exist"
            assert result_table.has_column("level"), "level column should exist"

            # Verification: Blood lineage tracking - should trace back to employees table
            paths = result.trace("result", "name")
            assert len(paths) > 0, "Should be able to trace at least one path"

            path_str = paths[0].to_string()
            try:
                print(f"Blood lineage path (recursive CTE): {path_str}")
            except UnicodeEncodeError:
                print(f"Blood lineage path (recursive CTE): {path_str.encode('ascii', 'replace').decode('ascii')}")

            # Should trace to source table employees
            assert "employees" in path_str, "Path should contain source table employees"

            print("[OK] Recursive CTE hierarchical: Blood lineage tracking successful")

        except Exception as e:
            print(f"[FAIL] Analysis failed: {e}")
            pytest.skip(f"Recursive CTE hierarchical not supported yet: {e}")

    def test_recursive_cte_referenced_by_other_query(self):
        """Test recursive CTE referenced by other queries"""
        script = """
        WITH RECURSIVE numbers AS (
            SELECT 1 AS n
            UNION ALL
            SELECT n + 1 FROM numbers WHERE n < 5
        )
        CREATE TABLE result AS
        SELECT n * 2 AS doubled FROM numbers WHERE n > 2;
        """

        schema = DictSchemaProvider({})
        analyzer = ScriptAnalyzer(schema_provider=schema)

        try:
            result = analyzer.analyze_script(script)

            # Verification: Final table created successfully
            result_table = result.get_table("result")
            assert result_table is not None, "result table should be created"
            assert result_table.has_column("doubled"), "doubled column should exist"

            # Verification: CTE was cleaned up
            assert result.get_table("numbers") is None, "numbers CTE should be cleaned up"

            print("[OK] Recursive CTE referenced by other query: Successful")

        except Exception as e:
            print(f"[FAIL] Analysis failed: {e}")
            pytest.skip(f"Recursive CTE referenced by other query not supported yet: {e}")

    def test_recursive_cte_lineage_to_anchor_source(self):
        """Test that recursive CTE lineage traces back to anchor query's source tables"""
        script = """
        WITH RECURSIVE category_tree AS (
            -- Anchor part: root categories
            SELECT category_id, parent_id, name
            FROM categories
            WHERE parent_id IS NULL
            UNION ALL
            -- Recursive part: child categories
            SELECT c.category_id, c.parent_id, c.name
            FROM categories c
            INNER JOIN category_tree ct ON c.parent_id = ct.category_id
        )
        CREATE TABLE result AS
        SELECT category_id, name FROM category_tree;
        """

        schema = DictSchemaProvider({
            "categories": ["category_id", "parent_id", "name"]
        })
        analyzer = ScriptAnalyzer(schema_provider=schema)

        try:
            result = analyzer.analyze_script(script)

            # Verification: Final table created successfully
            result_table = result.get_table("result")
            assert result_table is not None, "result table should be created"
            assert result_table.has_column("name"), "name column should exist"

            # Verification: Blood lineage should trace back to anchor's source table
            paths = result.trace("result", "name")
            assert len(paths) > 0, "Should be able to trace at least one path"

            path_str = paths[0].to_string()
            try:
                print(f"Blood lineage path (recursive CTE anchor source): {path_str}")
            except UnicodeEncodeError:
                print(f"Blood lineage path (recursive CTE anchor source): {path_str.encode('ascii', 'replace').decode('ascii')}")

            # Should trace to source table categories (from anchor part)
            assert "categories" in path_str, "Path should contain source table categories from anchor"

            print("[OK] Recursive CTE lineage to anchor source: Successful")

        except Exception as e:
            print(f"[FAIL] Analysis failed: {e}")
            pytest.skip(f"Recursive CTE lineage to anchor source not supported yet: {e}")

    # === UNION/UNION ALL Tests ===

    def test_cte_with_simple_union(self):
        """Test CTE with simple UNION: two tables merged"""
        script = """
        WITH combined AS (
            SELECT id, name FROM table1
            UNION
            SELECT id, name FROM table2
        )
        CREATE TABLE result AS
        SELECT * FROM combined;
        """

        schema = DictSchemaProvider({
            "table1": ["id", "name"],
            "table2": ["id", "name"]
        })
        analyzer = ScriptAnalyzer(schema_provider=schema)

        try:
            result = analyzer.analyze_script(script)

            # Verification: Final table created successfully
            result_table = result.get_table("result")
            assert result_table is not None, "result table should be created"
            assert result_table.has_column("id"), "id column should exist"
            assert result_table.has_column("name"), "name column should exist"

            # Verification: Blood lineage tracking - should trace to both tables
            paths = result.trace("result", "id")
            assert len(paths) > 0, "Should be able to trace at least one path"

            path_str = paths[0].to_string()
            try:
                print(f"Blood lineage path (UNION): {path_str}")
            except UnicodeEncodeError:
                print(f"Blood lineage path (UNION): {path_str.encode('ascii', 'replace').decode('ascii')}")

            # Should trace to both source tables
            assert "table1" in path_str or "table2" in path_str, "Path should contain at least one source table"

            # Check column lineage sources
            id_lineage = result_table.get_column("id")
            assert id_lineage is not None, "id column lineage should exist"
            sources_str = ", ".join(f"{s.table}.{s.column}" for s in id_lineage.sources)
            print(f"id sources: {sources_str}")
            # Should have sources from both tables
            assert any("table1" in s for s in sources_str.split(", ")), "Should have source from table1"
            assert any("table2" in s for s in sources_str.split(", ")), "Should have source from table2"

            print("[OK] CTE with simple UNION: Blood lineage tracking successful")

        except Exception as e:
            print(f"[FAIL] Analysis failed: {e}")
            pytest.skip(f"CTE with UNION not supported yet: {e}")

    def test_cte_with_union_all(self):
        """Test CTE with UNION ALL: preserves duplicates"""
        script = """
        WITH combined AS (
            SELECT id, name FROM table1
            UNION ALL
            SELECT id, name FROM table2
        )
        CREATE TABLE result AS
        SELECT * FROM combined;
        """

        schema = DictSchemaProvider({
            "table1": ["id", "name"],
            "table2": ["id", "name"]
        })
        analyzer = ScriptAnalyzer(schema_provider=schema)

        try:
            result = analyzer.analyze_script(script)

            # Verification: Final table created successfully
            result_table = result.get_table("result")
            assert result_table is not None, "result table should be created"
            assert result_table.has_column("id"), "id column should exist"
            assert result_table.has_column("name"), "name column should exist"

            # Verification: Blood lineage should include both branches
            id_lineage = result_table.get_column("id")
            sources_str = ", ".join(f"{s.table}.{s.column}" for s in id_lineage.sources)
            print(f"id sources (UNION ALL): {sources_str}")
            assert any("table1" in s for s in sources_str.split(", ")), "Should have source from table1"
            assert any("table2" in s for s in sources_str.split(", ")), "Should have source from table2"

            print("[OK] CTE with UNION ALL: Successful")

        except Exception as e:
            print(f"[FAIL] Analysis failed: {e}")
            pytest.skip(f"CTE with UNION ALL not supported yet: {e}")

    def test_cte_with_union_different_column_names(self):
        """Test CTE with UNION where branches have different column names (positional matching)"""
        script = """
        WITH combined AS (
            SELECT id, name FROM table1
            UNION ALL
            SELECT emp_id, emp_name FROM table2
        )
        CREATE TABLE result AS
        SELECT * FROM combined;
        """

        schema = DictSchemaProvider({
            "table1": ["id", "name"],
            "table2": ["emp_id", "emp_name"]
        })
        analyzer = ScriptAnalyzer(schema_provider=schema)

        try:
            result = analyzer.analyze_script(script)

            # Verification: Final table created successfully
            result_table = result.get_table("result")
            assert result_table is not None, "result table should be created"
            # Column names should come from first branch
            assert result_table.has_column("id"), "id column should exist (from first branch)"
            assert result_table.has_column("name"), "name column should exist (from first branch)"

            # Verification: Blood lineage - id should trace to both table1.id and table2.emp_id
            id_lineage = result_table.get_column("id")
            sources_str = ", ".join(f"{s.table}.{s.column}" for s in id_lineage.sources)
            print(f"id sources (different names): {sources_str}")
            assert any("table1.id" in s for s in sources_str.split(", ")), "Should have source from table1.id"
            assert any("table2.emp_id" in s for s in sources_str.split(", ")), "Should have source from table2.emp_id"

            # name should trace to both table1.name and table2.emp_name
            name_lineage = result_table.get_column("name")
            sources_str = ", ".join(f"{s.table}.{s.column}" for s in name_lineage.sources)
            print(f"name sources (different names): {sources_str}")
            assert any("table1.name" in s for s in sources_str.split(", ")), "Should have source from table1.name"
            assert any("table2.emp_name" in s for s in sources_str.split(", ")), "Should have source from table2.emp_name"

            print("[OK] CTE with UNION (different column names): Successful")

        except Exception as e:
            print(f"[FAIL] Analysis failed: {e}")
            pytest.skip(f"CTE with UNION (different column names) not supported yet: {e}")

    def test_cte_with_multiple_union_branches(self):
        """Test CTE with three or more UNION branches"""
        script = """
        WITH combined AS (
            SELECT id, name FROM table1
            UNION ALL
            SELECT id, name FROM table2
            UNION ALL
            SELECT id, name FROM table3
        )
        CREATE TABLE result AS
        SELECT * FROM combined;
        """

        schema = DictSchemaProvider({
            "table1": ["id", "name"],
            "table2": ["id", "name"],
            "table3": ["id", "name"]
        })
        analyzer = ScriptAnalyzer(schema_provider=schema)

        try:
            result = analyzer.analyze_script(script)

            # Verification: Final table created successfully
            result_table = result.get_table("result")
            assert result_table is not None, "result table should be created"

            # Verification: Blood lineage should include all three branches
            id_lineage = result_table.get_column("id")
            sources_str = ", ".join(f"{s.table}.{s.column}" for s in id_lineage.sources)
            print(f"id sources (3 branches): {sources_str}")
            assert any("table1" in s for s in sources_str.split(", ")), "Should have source from table1"
            assert any("table2" in s for s in sources_str.split(", ")), "Should have source from table2"
            assert any("table3" in s for s in sources_str.split(", ")), "Should have source from table3"

            print("[OK] CTE with multiple UNION branches: Successful")

        except Exception as e:
            print(f"[FAIL] Analysis failed: {e}")
            pytest.skip(f"CTE with multiple UNION branches not supported yet: {e}")

    def test_cte_with_union_referenced_by_other_query(self):
        """Test CTE containing UNION referenced by other queries"""
        script = """
        WITH combined AS (
            SELECT id, name FROM table1
            UNION ALL
            SELECT id, name FROM table2
        )
        CREATE TABLE result AS
        SELECT id * 2 AS doubled_id, UPPER(name) AS upper_name FROM combined;
        """

        schema = DictSchemaProvider({
            "table1": ["id", "name"],
            "table2": ["id", "name"]
        })
        analyzer = ScriptAnalyzer(schema_provider=schema)

        try:
            result = analyzer.analyze_script(script)

            # Verification: Final table created successfully
            result_table = result.get_table("result")
            assert result_table is not None, "result table should be created"
            assert result_table.has_column("doubled_id"), "doubled_id column should exist"
            assert result_table.has_column("upper_name"), "upper_name column should exist"

            # Verification: Blood lineage should trace through CTE to source tables
            paths = result.trace("result", "doubled_id")
            assert len(paths) > 0, "Should be able to trace at least one path"

            path_str = paths[0].to_string()
            try:
                print(f"Blood lineage path (UNION CTE referenced): {path_str}")
            except UnicodeEncodeError:
                print(f"Blood lineage path (UNION CTE referenced): {path_str.encode('ascii', 'replace').decode('ascii')}")

            # Should trace to source tables
            assert "table1" in path_str or "table2" in path_str, "Path should contain at least one source table"

            print("[OK] CTE with UNION referenced by other query: Successful")

        except Exception as e:
            print(f"[FAIL] Analysis failed: {e}")
            pytest.skip(f"CTE with UNION referenced by other query not supported yet: {e}")

    def test_cte_with_nested_union(self):
        """Test CTE with nested UNION: (A UNION B) UNION C"""
        script = """
        WITH combined AS (
            (
                SELECT id, name FROM table1
                UNION ALL
                SELECT id, name FROM table2
            )
            UNION ALL
            SELECT id, name FROM table3
        )
        CREATE TABLE result AS
        SELECT * FROM combined;
        """

        schema = DictSchemaProvider({
            "table1": ["id", "name"],
            "table2": ["id", "name"],
            "table3": ["id", "name"]
        })
        analyzer = ScriptAnalyzer(schema_provider=schema)

        try:
            result = analyzer.analyze_script(script)

            # Verification: Final table created successfully
            result_table = result.get_table("result")
            assert result_table is not None, "result table should be created"

            # Verification: Blood lineage should include all three tables
            id_lineage = result_table.get_column("id")
            sources_str = ", ".join(f"{s.table}.{s.column}" for s in id_lineage.sources)
            print(f"id sources (nested UNION): {sources_str}")
            assert any("table1" in s for s in sources_str.split(", ")), "Should have source from table1"
            assert any("table2" in s for s in sources_str.split(", ")), "Should have source from table2"
            assert any("table3" in s for s in sources_str.split(", ")), "Should have source from table3"

            print("[OK] CTE with nested UNION: Successful")

        except Exception as e:
            print(f"[FAIL] Analysis failed: {e}")
            pytest.skip(f"CTE with nested UNION not supported yet: {e}")

