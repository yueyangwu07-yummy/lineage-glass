"""
Tests for Table Registry system.

This module contains tests for ColumnLineage, TableDefinition, and TableRegistry.
"""

import pytest

from lineage_analyzer import (
    ColumnLineage,
    ColumnRef,
    ExpressionType,
    LineageError,
    TableDefinition,
    TableRegistry,
    TableType,
)


class TestColumnLineage:
    """Tests for ColumnLineage."""

    def test_create_simple_lineage(self):
        """Test creating simple column lineage."""
        lineage = ColumnLineage(
            name="user_id",
            sources=[ColumnRef(table="orders", column="user_id")],
        )

        assert lineage.name == "user_id"
        assert len(lineage.sources) == 1
        assert lineage.expression_type == ExpressionType.DIRECT

    def test_add_source(self):
        """Test adding source columns."""
        lineage = ColumnLineage(name="total")

        lineage.add_source(ColumnRef(table="orders", column="amount"))
        lineage.add_source(ColumnRef(table="orders", column="tax"))

        assert len(lineage.sources) == 2

    def test_add_duplicate_source(self):
        """Test adding duplicate source columns (should deduplicate)."""
        lineage = ColumnLineage(name="total")
        source = ColumnRef(table="orders", column="amount")

        lineage.add_source(source)
        lineage.add_source(source)  # Duplicate

        assert len(lineage.sources) == 1

    def test_merge_lineages(self):
        """Test merging two ColumnLineage objects."""
        lineage1 = ColumnLineage(
            name="total",
            sources=[ColumnRef(table="orders", column="amount")],
            expression="amount",
        )

        lineage2 = ColumnLineage(
            name="total",
            sources=[ColumnRef(table="new_orders", column="amount")],
            expression="amount",
        )

        lineage1.merge_from(lineage2)

        assert len(lineage1.sources) == 2
        assert lineage1.confidence < 1.0  # Confidence decreased

    def test_merge_different_columns_raises_error(self):
        """Test that merging different columns raises ValueError."""
        lineage1 = ColumnLineage(name="col1")
        lineage2 = ColumnLineage(name="col2")

        with pytest.raises(ValueError, match="Cannot merge different columns"):
            lineage1.merge_from(lineage2)

    def test_confidence_validation(self):
        """Test that confidence must be between 0.0 and 1.0."""
        with pytest.raises(ValueError, match="confidence must be between"):
            ColumnLineage(name="col", confidence=1.5)

        with pytest.raises(ValueError, match="confidence must be between"):
            ColumnLineage(name="col", confidence=-0.1)

    def test_to_dict(self):
        """Test converting to dictionary."""
        lineage = ColumnLineage(
            name="total",
            sources=[
                ColumnRef(table="orders", column="amount"),
                ColumnRef(table="orders", column="tax"),
            ],
            expression="amount + tax",
            expression_type=ExpressionType.COMPUTED,
            confidence=0.9,
        )

        result = lineage.to_dict()

        assert result["name"] == "total"
        assert len(result["sources"]) == 2
        assert result["expression"] == "amount + tax"
        assert result["expression_type"] == "computed"
        assert result["confidence"] == 0.9


class TestTableDefinition:
    """Tests for TableDefinition."""

    def test_create_table_definition(self):
        """Test creating table definition."""
        table = TableDefinition(
            name="user_summary",
            table_type=TableType.TABLE,
        )

        assert table.name == "user_summary"
        assert table.table_type == TableType.TABLE
        assert len(table.columns) == 0

    def test_add_column(self):
        """Test adding columns."""
        table = TableDefinition(name="t1", table_type=TableType.TABLE)

        col = ColumnLineage(
            name="user_id",
            sources=[ColumnRef(table="orders", column="user_id")],
        )
        table.add_column(col)

        assert table.has_column("user_id")
        assert table.get_column("user_id") is not None

    def test_add_duplicate_column_merges(self):
        """Test that adding duplicate columns automatically merges."""
        table = TableDefinition(name="t1", table_type=TableType.TABLE)

        col1 = ColumnLineage(
            name="total",
            sources=[ColumnRef(table="orders", column="amount")],
        )
        col2 = ColumnLineage(
            name="total",
            sources=[ColumnRef(table="new_orders", column="amount")],
        )

        table.add_column(col1)
        table.add_column(col2)  # Should merge

        total_col = table.get_column("total")
        assert total_col is not None
        assert len(total_col.sources) == 2

    def test_get_all_source_columns(self):
        """Test getting all source columns."""
        table = TableDefinition(name="t1", table_type=TableType.TABLE)

        table.add_column(
            ColumnLineage(
                name="col1",
                sources=[ColumnRef(table="orders", column="amount")],
            )
        )
        table.add_column(
            ColumnLineage(
                name="col2",
                sources=[
                    ColumnRef(table="orders", column="tax"),
                    ColumnRef(table="customers", column="discount"),
                ],
            )
        )

        all_sources = table.get_all_source_columns()
        assert len(all_sources) == 3  # amount, tax, discount

    def test_get_all_source_columns_deduplicates(self):
        """Test that get_all_source_columns deduplicates."""
        table = TableDefinition(name="t1", table_type=TableType.TABLE)

        table.add_column(
            ColumnLineage(
                name="col1",
                sources=[ColumnRef(table="orders", column="amount")],
            )
        )
        table.add_column(
            ColumnLineage(
                name="col2",
                sources=[ColumnRef(table="orders", column="amount")],  # Duplicate
            )
        )

        all_sources = table.get_all_source_columns()
        assert len(all_sources) == 1  # Should be deduplicated

    def test_to_dict(self):
        """Test converting to dictionary."""
        table = TableDefinition(
            name="t1",
            table_type=TableType.TABLE,
            created_by_sql="CREATE TABLE t1 AS SELECT ...",
            created_at_statement=5,
        )

        table.add_column(
            ColumnLineage(
                name="col1",
                sources=[ColumnRef(table="orders", column="amount")],
            )
        )

        result = table.to_dict()

        assert result["name"] == "t1"
        assert result["table_type"] == "table"
        assert result["created_at_statement"] == 5
        assert "col1" in result["columns"]


class TestTableRegistry:
    """Tests for TableRegistry."""

    def test_register_and_get_table(self):
        """Test registering and getting tables."""
        registry = TableRegistry()

        table = TableDefinition(name="t1", table_type=TableType.TABLE)
        registry.register_table(table)

        assert registry.has_table("t1")
        retrieved = registry.get_table("t1")
        assert retrieved is not None
        assert retrieved.name == "t1"

    def test_table_name_normalization(self):
        """Test table name normalization (case-insensitive)."""
        registry = TableRegistry()

        table = TableDefinition(name="MyTable", table_type=TableType.TABLE)
        registry.register_table(table)

        assert registry.has_table("mytable")
        assert registry.has_table("MYTABLE")
        assert registry.has_table("MyTable")

    def test_register_source_table(self):
        """Test registering source tables."""
        registry = TableRegistry()

        registry.register_source_table("orders", columns=["id", "amount", "tax"])

        assert registry.has_table("orders")
        table = registry.get_table("orders")
        assert table is not None
        assert table.is_source_table
        assert table.table_type == TableType.EXTERNAL
        assert table.has_column("amount")

    def test_update_table_columns(self):
        """Test updating table columns (INSERT INTO scenario)."""
        registry = TableRegistry()

        # First create table
        table = TableDefinition(name="t1", table_type=TableType.TABLE)
        table.add_column(
            ColumnLineage(
                name="col1",
                sources=[ColumnRef(table="orders", column="amount")],
            )
        )
        registry.register_table(table)

        # Update columns (simulate INSERT INTO)
        new_columns = {
            "col1": ColumnLineage(
                name="col1",
                sources=[ColumnRef(table="new_orders", column="amount")],
            )
        }
        registry.update_table_columns("t1", new_columns)

        # Verify merge
        updated_table = registry.get_table("t1")
        assert updated_table is not None
        col1 = updated_table.get_column("col1")
        assert col1 is not None
        assert len(col1.sources) == 2

    def test_cannot_redefine_source_table(self):
        """Test that source tables cannot be redefined."""
        registry = TableRegistry()

        registry.register_source_table("orders")

        # Try to redefine should raise error
        with pytest.raises(LineageError, match="Cannot redefine source table"):
            registry.register_table(
                TableDefinition(name="orders", table_type=TableType.TABLE)
            )

    def test_get_source_and_derived_tables(self):
        """Test distinguishing source and derived tables."""
        registry = TableRegistry()

        registry.register_source_table("orders")
        registry.register_table(
            TableDefinition(name="summary", table_type=TableType.TABLE)
        )

        source_tables = registry.get_source_tables()
        derived_tables = registry.get_derived_tables()

        assert len(source_tables) == 1
        assert len(derived_tables) == 1
        assert source_tables[0].name == "orders"
        assert derived_tables[0].name == "summary"

    def test_statement_counter(self):
        """Test statement counter."""
        registry = TableRegistry()

        table1 = TableDefinition(name="t1", table_type=TableType.TABLE)
        registry.register_table(table1)
        assert table1.created_at_statement == 0

        registry.increment_statement_counter()

        table2 = TableDefinition(name="t2", table_type=TableType.TABLE)
        registry.register_table(table2)
        assert table2.created_at_statement == 1

    def test_reset(self):
        """Test resetting registry."""
        registry = TableRegistry()

        registry.register_table(TableDefinition(name="t1", table_type=TableType.TABLE))
        assert len(registry.get_all_tables()) == 1

        registry.reset()
        assert len(registry.get_all_tables()) == 0
        assert registry._statement_counter == 0

    def test_update_nonexistent_table_raises_error(self):
        """Test that updating a non-existent table raises error."""
        registry = TableRegistry()

        with pytest.raises(LineageError, match="table not found"):
            registry.update_table_columns(
                "nonexistent",
                {"col1": ColumnLineage(name="col1")},
            )

    def test_to_dict(self):
        """Test converting registry to dictionary."""
        registry = TableRegistry()

        registry.register_table(TableDefinition(name="t1", table_type=TableType.TABLE))
        registry.register_source_table("orders", columns=["id"])

        result = registry.to_dict()

        assert "tables" in result
        assert "statement_counter" in result
        assert len(result["tables"]) == 2

