"""
Symbol resolver for lineage analysis.

This module defines the SymbolResolver class, which resolves column
references in SQL to fully qualified table.column form, handling
ambiguity resolution and schema validation.
"""

from __future__ import annotations

from typing import Optional, Tuple

import sqlglot
from sqlglot import expressions

from lineage_analyzer.exceptions import (
    AmbiguousColumnError,
    SchemaValidationError,
    UnresolvedReferenceError,
)
from lineage_analyzer.models.column import ColumnRef
from lineage_analyzer.models.config import ErrorMode, LineageConfig
from lineage_analyzer.models.scope import Scope
from lineage_analyzer.models.table import TableRef
from lineage_analyzer.schema.provider import SchemaProvider
from lineage_analyzer.utils.warnings import WarningCollector


class SymbolResolver:
    """Resolves column references to fully qualified table.column form.

    This class provides functionality to resolve column references in SQL
    to fully qualified table.column form, handling ambiguity resolution,
    schema validation, and error reporting.

    Attributes:
        scope: Scope object containing table and column information.
        config: LineageConfig object containing resolver configuration.
        schema: Optional SchemaProvider for schema validation.
        warnings: WarningCollector for collecting warnings and errors.

    Example:
        >>> config = LineageConfig()
        >>> scope = Scope()
        >>> scope.register_table(TableRef(table="orders", alias="o"))
        >>> resolver = SymbolResolver(scope, config)
        >>> column_ref = resolver.resolve_column("id", "o")
        >>> column_ref.table == "orders"
        True
        >>> column_ref.column == "id"
        True
    """

    def __init__(
        self,
        scope: Scope,
        config: LineageConfig,
        schema_provider: Optional[SchemaProvider] = None,
    ) -> None:
        """Initialize a SymbolResolver.

        Args:
            scope: Scope object containing table and column information.
            config: LineageConfig object containing resolver configuration.
            schema_provider: Optional SchemaProvider for schema validation.
        """
        self.scope = scope
        self.config = config
        self.schema = schema_provider
        self.warnings = WarningCollector()

    def resolve_column(
        self, column_name: str, table_qualifier: Optional[str] = None
    ) -> ColumnRef:
        """Resolve a column reference to a ColumnRef.

        This method resolves a column reference to a fully qualified
        ColumnRef object, handling ambiguity resolution and schema
        validation according to the configuration.

        Algorithm:
        1. If table_qualifier is provided (e.g., "o.customer_id" where "o" is the qualifier):
           - Look up the qualifier in scope.tables (alias or table name)
           - If found, construct ColumnRef(table=real_table_name, column=column_name)
           - If not found, raise UnresolvedReferenceError

        2. If table_qualifier is not provided (e.g., "customer_id"):
           - If config.require_table_prefix=True, raise exception
           - Otherwise, try to infer:
             a. If scope has only one table, use that table automatically
             b. If scope has multiple tables:
                - With schema: Check which tables have this column
                  - Only one table has it → use that table
                  - Multiple tables have it → handle according to config.on_ambiguity
                  - None have it → raise SchemaValidationError
                - Without schema: Handle according to config.on_ambiguity
                  - FAIL: raise AmbiguousColumnError
                  - WARN: use first table, but record warning
                  - IGNORE: use first table

        Args:
            column_name: Column name to resolve.
            table_qualifier: Optional table qualifier (alias or table name).

        Returns:
            ColumnRef object representing the resolved column.

        Raises:
            AmbiguousColumnError: If column name is ambiguous and config requires failure.
            UnresolvedReferenceError: If table qualifier cannot be resolved.
            SchemaValidationError: If column does not exist in schema.

        Example:
            >>> config = LineageConfig()
            >>> scope = Scope()
            >>> scope.register_table(TableRef(table="orders", alias="o"))
            >>> resolver = SymbolResolver(scope, config)
            >>> column_ref = resolver.resolve_column("id", "o")
            >>> column_ref.table == "orders"
            True
        """
        if not column_name:
            raise ValueError("Column name cannot be empty")

        # Case 1: Table qualifier is provided
        if table_qualifier:
            return self._resolve_qualified_column(column_name, table_qualifier)

        # Case 2: No table qualifier
        return self._resolve_unqualified_column(column_name)

    def _resolve_qualified_column(
        self, column_name: str, table_qualifier: str
    ) -> ColumnRef:
        """Resolve a column reference with a table qualifier.

        This method resolves a column reference that includes a table
        qualifier (alias or table name), e.g., "o.customer_id" where
        "o" is the qualifier.

        Args:
            column_name: Column name to resolve.
            table_qualifier: Table qualifier (alias or table name).

        Returns:
            ColumnRef object representing the resolved column.

        Raises:
            UnresolvedReferenceError: If table qualifier cannot be resolved.
            SchemaValidationError: If schema validation is enabled and column does not exist.

        Example:
            >>> resolver = SymbolResolver(scope, config)
            >>> column_ref = resolver._resolve_qualified_column("id", "o")
            >>> column_ref.table == "orders"
            True
        """
        # Resolve table qualifier to real table name
        table_ref = self._resolve_table_qualifier(table_qualifier)
        if table_ref is None:
            raise UnresolvedReferenceError(
                f"Table qualifier '{table_qualifier}' not found in scope. "
                f"Available tables: {list(self.scope.tables.keys())}",
                table_qualifier,
            )

        # Validate column existence if schema is available
        if self.config.schema_validation and self.schema:
            if not self.schema.column_exists(
                table_ref.to_qualified_name(), column_name
            ):
                raise SchemaValidationError(
                    f"Column '{column_name}' does not exist in table "
                    f"'{table_ref.to_qualified_name()}'",
                    table_ref.to_qualified_name(),
                    column_name,
                )

        # Construct ColumnRef
        return ColumnRef(
            table=table_ref.table,
            column=column_name,
            database=table_ref.database,
            schema=table_ref.schema,
        )

    def _resolve_unqualified_column(self, column_name: str) -> ColumnRef:
        """Resolve a column reference without a table qualifier.

        This method resolves a column reference that does not include a
        table qualifier, e.g., "customer_id". It handles ambiguity
        resolution according to the configuration.

        Args:
            column_name: Column name to resolve.

        Returns:
            ColumnRef object representing the resolved column.

        Raises:
            AmbiguousColumnError: If column name is ambiguous and config requires failure.
            SchemaValidationError: If column does not exist in any table.

        Example:
            >>> resolver = SymbolResolver(scope, config)
            >>> column_ref = resolver._resolve_unqualified_column("id")
            >>> column_ref.table == "orders"
            True
        """
        # Check if table prefix is required
        if self.config.require_table_prefix:
            raise AmbiguousColumnError(
                f"Column '{column_name}' requires a table prefix. "
                f"Available tables: {list(self.scope.tables.keys())}",
                column_name,
            )

        # Get all tables in scope
        tables = list(self.scope.tables.values())
        unique_tables = {table.table: table for table in tables}.values()
        unique_tables_list = list(unique_tables)

        # Case 1: Only one table in scope
        if len(unique_tables_list) == 1:
            table_ref = unique_tables_list[0]
            
            # Validate column existence if schema is available
            if self.schema:
                table_name = table_ref.to_qualified_name()
                if not self.schema.column_exists(table_name, column_name):
                    if self.config.schema_validation:
                        raise SchemaValidationError(
                            f"Column '{column_name}' does not exist in table "
                            f"'{table_name}'",
                            table_name,
                            column_name,
                        )
                    else:
                        # Schema validation disabled, add warning
                        self.warnings.add(
                            "WARNING",
                            f"Column '{column_name}' not found in schema for table "
                            f"'{table_name}', using as fallback",
                            column_name,
                        )
            
            return ColumnRef(
                table=table_ref.table,
                column=column_name,
                database=table_ref.database,
                schema=table_ref.schema,
            )

        # Case 2: Multiple tables in scope
        # Try to resolve using schema if available
        if self.schema:
            tables_with_column = self._find_tables_with_column(column_name)
            if len(tables_with_column) == 0:
                # Column does not exist in any table
                if self.config.schema_validation:
                    raise SchemaValidationError(
                        f"Column '{column_name}' does not exist in any table. "
                        f"Available tables: {[t.table for t in unique_tables]}",
                        ", ".join([t.table for t in unique_tables]),
                        column_name,
                    )
                else:
                    # Use first table as fallback
                    table_ref = list(unique_tables)[0]
                    self.warnings.add(
                        "WARNING",
                        f"Column '{column_name}' not found in schema, "
                        f"using table '{table_ref.table}' as fallback",
                        column_name,
                    )
                    return ColumnRef(
                        table=table_ref.table,
                        column=column_name,
                        database=table_ref.database,
                        schema=table_ref.schema,
                    )
            elif len(tables_with_column) == 1:
                # Only one table has this column
                table_name = tables_with_column[0]
                table_ref = self._resolve_table_qualifier(table_name)
                if table_ref is None:
                    raise UnresolvedReferenceError(
                        f"Table '{table_name}' not found in scope",
                        table_name,
                    )
                return ColumnRef(
                    table=table_ref.table,
                    column=column_name,
                    database=table_ref.database,
                    schema=table_ref.schema,
                )
            else:
                # Multiple tables have this column - ambiguity
                return self._handle_ambiguous_column(
                    column_name, tables_with_column
                )
        else:
            # No schema available - handle ambiguity
            return self._handle_ambiguous_column(column_name, None)

    def _handle_ambiguous_column(
        self, column_name: str, tables_with_column: Optional[list[str]]
    ) -> ColumnRef:
        """Handle ambiguous column reference.

        This method handles ambiguous column references when multiple
        tables could contain the column. It applies the configured
        ambiguity resolution strategy (FAIL, WARN, IGNORE).

        Args:
            column_name: Column name that is ambiguous.
            tables_with_column: Optional list of table names that contain the column.

        Returns:
            ColumnRef object representing the resolved column (may use first table).

        Raises:
            AmbiguousColumnError: If config requires failure on ambiguity.

        Example:
            >>> resolver = SymbolResolver(scope, config)
            >>> column_ref = resolver._handle_ambiguous_column("id", ["orders", "customers"])
            >>> column_ref.table in ["orders", "customers"]
            True
        """
        # Get all unique tables
        tables = list(self.scope.tables.values())
        unique_tables = {table.table: table for table in tables}.values()
        table_list = list(unique_tables)

        if tables_with_column:
            # Filter to only tables that have the column
            table_list = [
                t
                for t in table_list
                if t.table in tables_with_column or t.alias in tables_with_column
            ]

        if not table_list:
            # No tables found (should not happen, but handle gracefully)
            table_list = list(unique_tables)

        # Apply ambiguity resolution strategy
        if self.config.on_ambiguity == ErrorMode.FAIL:
            table_names = [t.table for t in table_list]
            raise AmbiguousColumnError(
                f"Column '{column_name}' is ambiguous. "
                f"Could refer to: {', '.join(table_names)}",
                column_name,
            )
        elif self.config.on_ambiguity == ErrorMode.WARN:
            # Use first table, but record warning
            table_ref = table_list[0]
            table_names = [t.table for t in table_list]
            self.warnings.add(
                "WARNING",
                f"Column '{column_name}' is ambiguous. "
                f"Using table '{table_ref.table}'. "
                f"Possible tables: {', '.join(table_names)}",
                column_name,
            )
            return ColumnRef(
                table=table_ref.table,
                column=column_name,
                database=table_ref.database,
                schema=table_ref.schema,
            )
        else:  # IGNORE
            # Use first table without warning
            table_ref = table_list[0]
            return ColumnRef(
                table=table_ref.table,
                column=column_name,
                database=table_ref.database,
                schema=table_ref.schema,
            )

    def resolve_column_from_ast_node(
        self, column_node: sqlglot.Expression
    ) -> ColumnRef:
        """Resolve a column reference from a sqlglot AST Column node.

        This is a convenience method that extracts the column name and
        table qualifier from a sqlglot AST Column node and resolves it
        using the resolve_column() method.

        Args:
            column_node: sqlglot AST Column node.

        Returns:
            ColumnRef object representing the resolved column.

        Raises:
            ValueError: If the node is not a Column node.

        Example:
            >>> ast = sqlglot.parse_one("SELECT o.id FROM orders o")
            >>> column_node = ast.expressions[0]
            >>> resolver = SymbolResolver(scope, config)
            >>> column_ref = resolver.resolve_column_from_ast_node(column_node)
            >>> column_ref.table == "orders"
            True
        """
        if not isinstance(column_node, expressions.Column):
            raise ValueError(
                f"Expected Column node, got {type(column_node).__name__}"
            )

        # Extract column name and table qualifier
        column_name = column_node.name
        table_qualifier = column_node.table

        # Resolve column reference
        return self.resolve_column(column_name, table_qualifier)

    def _find_tables_with_column(self, column_name: str) -> list[str]:
        """Find tables that contain a specific column.

        This method uses the schema provider to find which tables contain
        the specified column. It returns a list of table names that have
        the column.

        Args:
            column_name: Column name to search for.

        Returns:
            List of table names that contain the column.

        Example:
            >>> resolver = SymbolResolver(scope, config, schema_provider)
            >>> tables = resolver._find_tables_with_column("id")
            >>> "orders" in tables
            True
        """
        if not self.schema:
            return []

        tables_with_column: list[str] = []
        unique_tables = {
            table.table: table for table in self.scope.tables.values()
        }.values()

        for table_ref in unique_tables:
            table_name = table_ref.to_qualified_name()
            if self.schema.column_exists(table_name, column_name):
                tables_with_column.append(table_ref.table)

        return tables_with_column

    def _resolve_table_qualifier(self, qualifier: str) -> Optional[TableRef]:
        """Resolve a table qualifier to a TableRef.

        This method resolves a table qualifier (alias or table name) to
        a TableRef object by looking it up in the scope's tables dictionary.

        Args:
            qualifier: Table qualifier (alias or table name).

        Returns:
            TableRef object if found, None otherwise.

        Example:
            >>> resolver = SymbolResolver(scope, config)
            >>> table_ref = resolver._resolve_table_qualifier("o")
            >>> table_ref.table == "orders"
            True
        """
        return self.scope.resolve_table(qualifier)

    def resolve_column_with_inference(
        self,
        column_name: str,
        table_qualifier: Optional[str] = None,
        context: Optional[str] = None,
    ) -> Tuple[ColumnRef, float]:
        """Resolve a column reference with inference and confidence calculation.

        This enhanced method resolves a column reference and calculates
        the confidence level of the resolution. It provides better error
        messages and handles edge cases more gracefully.

        Args:
            column_name: Column name to resolve.
            table_qualifier: Optional table qualifier (alias or table name).
            context: Optional SQL context for error messages.

        Returns:
            Tuple of (ColumnRef, confidence) where confidence is a float
            between 0.0 and 1.0.

        Raises:
            AmbiguousColumnError: If column name is ambiguous and config requires failure.
            UnresolvedReferenceError: If table qualifier cannot be resolved.
            SchemaValidationError: If column does not exist in schema.

        Example:
            >>> resolver = SymbolResolver(scope, config)
            >>> col_ref, confidence = resolver.resolve_column_with_inference("id", "o")
            >>> col_ref.table == "orders"
            True
            >>> confidence > 0.9
            True
        """
        if not column_name:
            raise ValueError("Column name cannot be empty")

        # Case 1: Table qualifier is provided
        if table_qualifier:
            table_ref = self._resolve_table_qualifier(table_qualifier)
            if table_ref is None:
                # Build detailed error message
                available_tables = list(self.scope.tables.keys())
                error_msg = self._build_error_message(
                    "unresolved",
                    column_name,
                    context,
                    available_tables,
                    table_qualifier=table_qualifier,
                )
                raise UnresolvedReferenceError(error_msg, table_qualifier)

            # Validate column existence if schema is available
            confidence = self._calculate_confidence(
                "explicit", self.schema is not None, False
            )
            if self.config.schema_validation and self.schema:
                if not self.schema.column_exists(
                    table_ref.to_qualified_name(), column_name
                ):
                    error_msg = self._build_error_message(
                        "not_found",
                        column_name,
                        context,
                        [table_ref.table],
                        table_qualifier=table_qualifier,
                    )
                    raise SchemaValidationError(
                        error_msg, table_ref.to_qualified_name(), column_name
                    )

            return (
                ColumnRef(
                    table=table_ref.table,
                    column=column_name,
                    database=table_ref.database,
                    schema=table_ref.schema,
                ),
                confidence,
            )

        # Case 2: No table qualifier
        # Check if table prefix is required
        if self.config.require_table_prefix:
            available_tables = list(self.scope.tables.keys())
            error_msg = self._build_error_message(
                "unresolved",
                column_name,
                context,
                available_tables,
            )
            raise AmbiguousColumnError(error_msg, column_name)

        # Get all tables in scope
        tables = list(self.scope.tables.values())
        unique_tables = {table.table: table for table in tables}.values()
        unique_tables_list = list(unique_tables)
        table_order = self._get_table_resolution_order()

        # Case 2a: Only one table in scope
        if len(unique_tables_list) == 1:
            table_ref = unique_tables_list[0]
            confidence = 1.0  # Single table, high confidence

            # Validate column existence if schema is available
            if self.schema:
                table_name = table_ref.to_qualified_name()
                if not self.schema.column_exists(table_name, column_name):
                    if self.config.schema_validation:
                        error_msg = self._build_error_message(
                            "not_found",
                            column_name,
                            context,
                            [table_ref.table],
                        )
                        raise SchemaValidationError(
                            error_msg, table_name, column_name
                        )
                    else:
                        # Schema validation disabled, add warning
                        confidence = 0.3
                        self.warnings.add_schema_missing_warning(
                            column_name, table_ref.table, context
                        )
            else:
                confidence = 0.95  # No schema, but single table

            return (
                ColumnRef(
                    table=table_ref.table,
                    column=column_name,
                    database=table_ref.database,
                    schema=table_ref.schema,
                ),
                confidence,
            )

        # Case 2b: Multiple tables in scope
        # Try to resolve using schema if available
        if self.schema:
            tables_with_column = self._find_tables_with_column(column_name)
            if len(tables_with_column) == 0:
                # Column does not exist in any table
                if self.config.schema_validation:
                    error_msg = self._build_error_message(
                        "not_found",
                        column_name,
                        context,
                        [t.table for t in unique_tables_list],
                    )
                    raise SchemaValidationError(
                        error_msg,
                        ", ".join([t.table for t in unique_tables_list]),
                        column_name,
                    )
                else:
                    # Use first table as fallback
                    table_ref = unique_tables_list[0]
                    confidence = 0.3
                    self.warnings.add_schema_missing_warning(
                        column_name, table_ref.table, context
                    )
                    return (
                        ColumnRef(
                            table=table_ref.table,
                            column=column_name,
                            database=table_ref.database,
                            schema=table_ref.schema,
                        ),
                        confidence,
                    )
            elif len(tables_with_column) == 1:
                # Only one table has this column
                table_name = tables_with_column[0]
                table_ref = self._resolve_table_qualifier(table_name)
                if table_ref is None:
                    raise UnresolvedReferenceError(
                        f"Table '{table_name}' not found in scope", table_name
                    )
                confidence = 1.0  # Schema match, high confidence
                return (
                    ColumnRef(
                        table=table_ref.table,
                        column=column_name,
                        database=table_ref.database,
                        schema=table_ref.schema,
                    ),
                    confidence,
                )
            else:
                # Multiple tables have this column - ambiguity
                return self._handle_ambiguous_column_with_confidence(
                    column_name, tables_with_column, context
                )
        else:
            # No schema available - handle ambiguity
            return self._handle_ambiguous_column_with_confidence(
                column_name, None, context
            )

    def _handle_ambiguous_column_with_confidence(
        self,
        column_name: str,
        tables_with_column: Optional[list[str]],
        context: Optional[str],
    ) -> Tuple[ColumnRef, float]:
        """Handle ambiguous column reference with confidence calculation.

        Args:
            column_name: Column name that is ambiguous.
            tables_with_column: Optional list of table names that contain the column.
            context: Optional SQL context for error messages.

        Returns:
            Tuple of (ColumnRef, confidence).

        Raises:
            AmbiguousColumnError: If config requires failure on ambiguity.
        """
        # Get all unique tables
        tables = list(self.scope.tables.values())
        unique_tables = {table.table: table for table in tables}.values()
        table_list = list(unique_tables)

        if tables_with_column:
            # Filter to only tables that have the column
            table_list = [
                t
                for t in table_list
                if t.table in tables_with_column or t.alias in tables_with_column
            ]

        if not table_list:
            # No tables found (should not happen, but handle gracefully)
            table_list = list(unique_tables)

        # Sort by table resolution order
        table_order = self._get_table_resolution_order()
        table_list.sort(
            key=lambda t: (
                table_order.index(t.table) if t.table in table_order else 999
            )
        )

        # Apply ambiguity resolution strategy
        if self.config.on_ambiguity == ErrorMode.FAIL:
            table_names = [t.table for t in table_list]
            error_msg = self._build_error_message(
                "ambiguous", column_name, context, table_names
            )
            raise AmbiguousColumnError(error_msg, column_name)
        elif self.config.on_ambiguity == ErrorMode.WARN:
            # Use first table, but record warning
            table_ref = table_list[0]
            table_names = [t.table for t in table_list]
            confidence = 0.6  # Ambiguous but resolved
            self.warnings.add_ambiguity_warning(
                column_name, table_names, table_ref.table, context
            )
            return (
                ColumnRef(
                    table=table_ref.table,
                    column=column_name,
                    database=table_ref.database,
                    schema=table_ref.schema,
                ),
                confidence,
            )
        else:  # IGNORE
            # Use first table without warning
            table_ref = table_list[0]
            confidence = 0.8 if self.schema else 0.5
            return (
                ColumnRef(
                    table=table_ref.table,
                    column=column_name,
                    database=table_ref.database,
                    schema=table_ref.schema,
                ),
                confidence,
            )

    def _build_error_message(
        self,
        error_type: str,
        column_name: str,
        context: Optional[str],
        suggestions: list[str],
        table_qualifier: Optional[str] = None,
    ) -> str:
        """Build a detailed error message with context and suggestions.

        Args:
            error_type: Error type ("ambiguous", "unresolved", "not_found").
            column_name: Column name that caused the error.
            context: Optional SQL context.
            suggestions: List of suggestions (table names, etc.).
            table_qualifier: Optional table qualifier that was used.

        Returns:
            Formatted error message string.
        """
        lines = []

        if error_type == "ambiguous":
            lines.append(f"AmbiguousColumnError: Column '{column_name}' is ambiguous")
            if context:
                lines.append("")
                lines.append("Query context:")
                lines.append(f"  {context}")
                # Try to highlight the column name
                if column_name in context:
                    idx = context.find(column_name)
                    lines.append(" " * (idx + 2) + "^" * len(column_name))
            lines.append("")
            lines.append("Possible sources:")
            for table in suggestions:
                lines.append(f"  • {table}.{column_name}")
            lines.append("")
            lines.append("Suggestion:")
            lines.append("  Use table prefix to clarify:")
            # Get table aliases if available
            for table_name in suggestions:
                table_ref = self._resolve_table_qualifier(table_name)
                if table_ref and table_ref.alias:
                    lines.append(f"    - {table_ref.alias}.{column_name} (for {table_name}.{column_name})")
                else:
                    lines.append(f"    - {table_name}.{column_name}")

        elif error_type == "unresolved":
            lines.append(
                f"UnresolvedReferenceError: Table qualifier '{table_qualifier}' not found"
            )
            if context:
                lines.append("")
                lines.append("Query context:")
                lines.append(f"  {context}")
            lines.append("")
            lines.append("Available tables:")
            for table in suggestions:
                table_ref = self._resolve_table_qualifier(table)
                if table_ref:
                    if table_ref.alias:
                        lines.append(f"  • {table} (alias: {table_ref.alias})")
                    else:
                        lines.append(f"  • {table}")

        elif error_type == "not_found":
            lines.append(
                f"SchemaValidationError: Column '{column_name}' not found in schema"
            )
            if table_qualifier:
                lines.append(f"  Table: {table_qualifier}")
            if context:
                lines.append("")
                lines.append("Query context:")
                lines.append(f"  {context}")
            if suggestions:
                lines.append("")
                lines.append("Available tables:")
                for table in suggestions:
                    lines.append(f"  • {table}")

        return "\n".join(lines)

    def _get_table_resolution_order(self) -> list[str]:
        """Get the table resolution order based on FROM clause order.

        Returns:
            List of table names in resolution order.

        Example:
            >>> resolver = SymbolResolver(scope, config)
            >>> order = resolver._get_table_resolution_order()
            >>> len(order) > 0
            True
        """
        # Get all unique tables
        tables = list(self.scope.tables.values())
        unique_tables = {table.table: table for table in tables}

        # Return table names in the order they appear in scope.tables
        # (which should reflect FROM clause order)
        order = []
        seen = set()
        for key, table_ref in self.scope.tables.items():
            if table_ref.table not in seen:
                order.append(table_ref.table)
                seen.add(table_ref.table)

        return order

    def _calculate_confidence(
        self,
        resolution_method: str,
        has_schema: bool,
        is_ambiguous: bool,
    ) -> float:
        """Calculate the confidence level of a column resolution.

        Args:
            resolution_method: Resolution method ("explicit", "single_table",
                "schema_match", "first_table").
            has_schema: Whether schema information is available.
            is_ambiguous: Whether the resolution was ambiguous.

        Returns:
            Confidence level (0.0-1.0).

        Example:
            >>> resolver = SymbolResolver(scope, config)
            >>> confidence = resolver._calculate_confidence("explicit", True, False)
            >>> confidence > 0.9
            True
        """
        if resolution_method == "explicit":
            # Explicit table prefix
            return 0.95 if not has_schema else 1.0
        elif resolution_method == "single_table":
            # Single table, no ambiguity
            return 1.0
        elif resolution_method == "schema_match":
            # Schema matches uniquely
            return 1.0
        elif resolution_method == "first_table":
            # Using first table as fallback
            if has_schema:
                return 0.3  # Schema says column doesn't exist
            else:
                return 0.5 if is_ambiguous else 0.8
        else:
            # Default
            return 0.5

    def resolve_star_column(
        self, table_qualifier: Optional[str] = None
    ) -> list[ColumnRef]:
        """Resolve SELECT * or SELECT table.* to a list of columns.

        Args:
            table_qualifier: Optional table qualifier (alias or table name).

        Returns:
            List of ColumnRef objects representing all columns.

        Raises:
            SchemaValidationError: If schema is required but not available.

        Example:
            >>> resolver = SymbolResolver(scope, config, schema_provider)
            >>> columns = resolver.resolve_star_column("orders")
            >>> len(columns) > 0
            True
        """
        # First, try to get columns from registry (for CTEs and created tables)
        # Registry is passed to ScopeBuilder, but Scope doesn't store it
        # We need to get it from the schema provider if it has a registry attribute
        # Or we can try to get it from the scope's _preregister_columns method context
        # Actually, the best way is to check if schema_provider has a registry
        registry = None
        if hasattr(self.schema, 'registry'):
            registry = self.schema.registry
        elif hasattr(self, 'registry'):
            registry = self.registry
        # Also try to get from scope if it was added
        if not registry:
            registry = getattr(self.scope, 'registry', None)
        
        # If we have a registry, try to get columns from it first
        if registry and table_qualifier:
            table_ref = self._resolve_table_qualifier(table_qualifier)
            if table_ref:
                table_name = table_ref.table
                table_def = registry.get_table(table_name)
                if table_def and table_def.columns:
                    # Get columns from registry
                    columns = []
                    for col_name in table_def.columns.keys():
                        columns.append(
                            ColumnRef(
                                table=table_ref.table,
                                column=col_name,
                                database=table_ref.database,
                                schema=table_ref.schema,
                            )
                        )
                    return columns
        
        if not self.schema:
            if self.config.expand_wildcards:
                raise SchemaValidationError(
                    "SELECT * requires schema information to expand. "
                    "Please provide a schema provider.",
                    "",
                    "*",
                )
            else:
                # Return empty list if wildcards are not expanded
                return []

        columns: list[ColumnRef] = []

        if table_qualifier:
            # SELECT table.*
            table_ref = self._resolve_table_qualifier(table_qualifier)
            if table_ref is None:
                raise UnresolvedReferenceError(
                    f"Table qualifier '{table_qualifier}' not found in scope. "
                    f"Available tables: {list(self.scope.tables.keys())}",
                    table_qualifier,
                )

            # Get all columns from this table
            # First try registry (for CTEs and created tables)
            table_name = table_ref.to_qualified_name()
            table_columns = None
            if registry:
                table_def = registry.get_table(table_ref.table)
                if table_def and table_def.columns:
                    table_columns = list(table_def.columns.keys())
            
            # Fallback to schema provider
            if not table_columns:
                table_columns = self.schema.get_table_columns(table_name)
            
            for col_name in table_columns:
                columns.append(
                    ColumnRef(
                        table=table_ref.table,
                        column=col_name,
                        database=table_ref.database,
                        schema=table_ref.schema,
                    )
                )
        else:
            # SELECT * (all tables)
            unique_tables = {
                table.table: table for table in self.scope.tables.values()
            }.values()

            seen_columns: set[str] = set()
            for table_ref in unique_tables:
                table_name = table_ref.to_qualified_name()
                # First try registry (for CTEs and created tables)
                table_columns = None
                if registry:
                    table_def = registry.get_table(table_ref.table)
                    if table_def and table_def.columns:
                        table_columns = list(table_def.columns.keys())
                
                # Fallback to schema provider
                if not table_columns:
                    table_columns = self.schema.get_table_columns(table_name)
                for col_name in table_columns:
                    # Deduplicate: if column name appears in multiple tables,
                    # only include it once (from first table)
                    if col_name not in seen_columns:
                        columns.append(
                            ColumnRef(
                                table=table_ref.table,
                                column=col_name,
                                database=table_ref.database,
                                schema=table_ref.schema,
                            )
                        )
                        seen_columns.add(col_name)

        return columns

    def handle_using_clause(self, column_names: list[str]) -> dict[str, ColumnRef]:
        """Handle JOIN ... USING (col1, col2) clause.

        Args:
            column_names: List of column names in the USING clause.

        Returns:
            Dictionary mapping column names to ColumnRef objects.

        Example:
            >>> resolver = SymbolResolver(scope, config)
            >>> columns = resolver.handle_using_clause(["customer_id"])
            >>> len(columns) > 0
            True
        """
        result: dict[str, ColumnRef] = {}

        for column_name in column_names:
            # In USING clause, the column should exist in both tables
            # We resolve it from the first table (left table)
            table_order = self._get_table_resolution_order()
            if len(table_order) >= 2:
                # Use the first table (left table in JOIN)
                first_table = table_order[0]
                table_ref = self._resolve_table_qualifier(first_table)
                if table_ref:
                    result[column_name] = ColumnRef(
                        table=table_ref.table,
                        column=column_name,
                        database=table_ref.database,
                        schema=table_ref.schema,
                    )
                else:
                    # Fallback: try to resolve without table qualifier
                    col_ref, _ = self.resolve_column_with_inference(column_name)
                    result[column_name] = col_ref
            else:
                # Single table or no tables
                col_ref, _ = self.resolve_column_with_inference(column_name)
                result[column_name] = col_ref

        return result

