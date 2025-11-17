"""
CTE (Common Table Expression) extraction and analysis tool.

This module defines the CTEExtractor class, which extracts and analyzes
CTE definitions from WITH clauses in SQL queries.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import sqlglot
from sqlglot import exp

from lineage_analyzer.analyzer.dependency_extractor import DependencyExtractor
from lineage_analyzer.analyzer.scope_builder import ScopeBuilder
from lineage_analyzer.analyzer.symbol_resolver import SymbolResolver
from lineage_analyzer.exceptions import LineageError
from lineage_analyzer.models.column_lineage import ColumnLineage
from lineage_analyzer.models.config import LineageConfig
from lineage_analyzer.models.scope import Scope
from lineage_analyzer.models.table_definition import TableDefinition, TableType
from lineage_analyzer.registry.table_registry import TableRegistry
from lineage_analyzer.schema.provider import SchemaProvider


class CTEDefinition:
    """CTE definition."""

    def __init__(self, name: str, select_node: exp.Expression, is_recursive: bool = False):
        """
        Initialize CTE definition.
        
        Args:
            name: CTE name
            select_node: SELECT or Union node (for recursive CTEs)
            is_recursive: Whether this is a recursive CTE
        """
        self.name = name
        self.select_node = select_node  # Can be Select or Union
        self.is_recursive = is_recursive

    def __repr__(self):
        return f"CTE({self.name}, recursive={self.is_recursive})"


class CTEExtractor:
    """
    CTE extractor.

    Responsibilities:
    1. Extract CTE definitions from SELECT statements
    2. Analyze CTE's SELECT statements
    3. Register CTEs as temporary tables

    Usage:
        extractor = CTEExtractor(registry, config, schema_provider)
        ctes = extractor.extract_ctes(select_node)
        extractor.analyze_and_register_ctes(ctes)
    """

    def __init__(
        self,
        registry: TableRegistry,
        config: LineageConfig,
        schema_provider: Optional[SchemaProvider] = None,
    ):
        """
        Args:
            registry: Table registry
            config: Lineage configuration
            schema_provider: Optional schema provider
        """
        self.registry = registry
        self.config = config
        self.schema_provider = schema_provider

    def extract_ctes(self, select_node: exp.Select) -> List[CTEDefinition]:
        """
        Extract all CTE definitions from a SELECT node.

        Args:
            select_node: SELECT statement AST node

        Returns:
            List[CTEDefinition]: CTE definition list (in definition order)

        Example:
            WITH tmp1 AS (...), tmp2 AS (...)
            Returns: [CTE(tmp1), CTE(tmp2)]
            
            WITH RECURSIVE numbers AS (...)
            Returns: [CTE(numbers, recursive=True)]
        """
        ctes = []

        # Check if there is a WITH clause
        with_node = select_node.args.get("with")
        if not with_node:
            return ctes

        # Check if this is a WITH RECURSIVE clause
        # In sqlglot, the With node has a 'recursive' attribute
        is_recursive = getattr(with_node, 'recursive', False)

        # Traverse all CTE expressions
        for cte_expr in with_node.expressions:
            # CTE structure:
            # CTE(
            #     alias=...,     # CTE name
            #     this=Select() or Union()  # CTE's SELECT statement (or Union for recursive)
            # )
            if isinstance(cte_expr, exp.CTE):
                cte_name = cte_expr.alias
                cte_body = cte_expr.this

                if cte_name:
                    # For recursive CTEs, the body might be a Union or Select
                    # For normal CTEs, it's usually a Select
                    cte_is_recursive = is_recursive
                    
                    if cte_is_recursive:
                        # Verify that this CTE actually has recursive structure
                        # (UNION/UNION ALL with self-reference)
                        # Check if body is Union or if it references itself
                        if isinstance(cte_body, exp.Union):
                            # Has UNION structure, check if recursive part references CTE
                            if not self._has_recursive_structure_in_union(cte_body, cte_name):
                                cte_is_recursive = False
                        elif isinstance(cte_body, exp.Select):
                            # Single Select, check if it has recursive structure
                            if not self._has_recursive_structure(cte_body, cte_name):
                                cte_is_recursive = False
                        else:
                            # Unknown structure
                            cte_is_recursive = False
                    
                    # For recursive CTEs, we need to handle Union nodes
                    # For now, we'll pass the body as-is and handle it in analysis
                    # But we need a Select node for CTEDefinition
                    # If it's a Union, we'll need to extract a Select from it or handle differently
                    if isinstance(cte_body, (exp.Select, exp.Union)):
                        # Create CTEDefinition with the body
                        # Note: For Union, we'll handle it specially in analysis
                        ctes.append(CTEDefinition(cte_name, cte_body, cte_is_recursive))

        return ctes

    def analyze_and_register_ctes(
        self, ctes: List[CTEDefinition], statement_index: int = 0
    ) -> Dict[str, TableDefinition]:
        """
        Analyze and register CTE tables.

        Key points:
        1. Analyze in order (later CTEs may reference earlier ones)
        2. Use existing DependencyExtractor to analyze SELECT
        3. Register as TableType.CTE

        Args:
            ctes: CTE definition list
            statement_index: Statement index (for recording)

        Returns:
            Dict[str, TableDefinition]: CTE name -> table definition
        """
        registered_ctes = {}

        for cte in ctes:
            try:
                if cte.is_recursive:
                    # Handle recursive CTE specially
                    cte_table = self._analyze_recursive_cte(cte, statement_index)
                else:
                    # Handle normal CTE
                    cte_table = self._analyze_normal_cte(cte, statement_index)

                if cte_table:
                    # Register to Registry
                    self.registry.register_table(cte_table)
                    registered_ctes[cte.name] = cte_table
                else:
                    pass

            except Exception as e:
                # If CTE analysis fails, log but continue
                # This prevents one CTE failure from breaking the entire statement
                # Note: Error is silently ignored to prevent breaking the entire statement
                continue

        return registered_ctes

    def _analyze_normal_cte(
        self, cte: CTEDefinition, statement_index: int
    ) -> TableDefinition:
        """
        Analyze a normal (non-recursive) CTE.
        
        Args:
            cte: CTE definition
            statement_index: Statement index
            
        Returns:
            TableDefinition for the CTE
        """
        # Check if CTE body is a Union (UNION/UNION ALL)
        if isinstance(cte.select_node, exp.Union):
            # Handle UNION in CTE
            return self._analyze_union_cte(cte, statement_index)
        
        # 1. Build scope for CTE's SELECT
        # CTE can reference earlier CTEs (already in registry)
        scope_builder = ScopeBuilder(
            config=self.config,
            schema_provider=self.schema_provider,
            registry=self.registry,
        )
        scope = scope_builder.build_scope(cte.select_node)

        # 2. Auto-register source tables from scope to registry
        # This ensures source tables are available for transitive resolution
        for table_ref in scope.tables.values():
            table_name = table_ref.table
            # Only register if not already in registry
            if not self.registry.has_table(table_name):
                # Try to get columns from schema provider
                if self.schema_provider:
                    try:
                        columns = self.schema_provider.get_table_columns(
                            table_ref.to_qualified_name()
                        )
                        self.registry.register_source_table(table_name, columns)
                    except Exception:
                        # Schema doesn't have this table, register without columns
                        self.registry.register_source_table(table_name)
                else:
                    # No schema provider, register without columns
                    self.registry.register_source_table(table_name)

        # 3. Create Symbol Resolver
        resolver = SymbolResolver(scope, self.config, self.schema_provider)
        # Attach registry to resolver for CTE references
        resolver.registry = self.registry

        # 4. Extract dependencies (using DependencyExtractor)
        extractor = DependencyExtractor(scope, resolver, self.config)
        dependencies = extractor.extract(cte.select_node)

        # 5. Convert ColumnDependency to ColumnLineage
        column_lineages = self._convert_dependencies_to_lineages(dependencies)

        # 6. Convert to ColumnLineage dictionary
        columns = {}
        for lineage in column_lineages:
            columns[lineage.name] = lineage

        # 7. Create CTE table definition
        cte_table = TableDefinition(
            name=cte.name,
            table_type=TableType.CTE,
            columns=columns,
            created_at_statement=statement_index,
            is_recursive=False,
        )

        return cte_table

    def _analyze_recursive_cte(
        self, cte: CTEDefinition, statement_index: int, max_depth: int = 100
    ) -> TableDefinition:
        """
        Analyze a recursive CTE.
        
        For recursive CTEs:
        1. Parse anchor and recursive parts
        2. Process anchor part normally (traces to source tables)
        3. Process recursive part with special handling for self-reference
        4. Merge lineage from both parts, ensuring final lineage traces to anchor's sources
        
        Args:
            cte: Recursive CTE definition
            statement_index: Statement index
            max_depth: Maximum recursion depth (default 100)
            
        Returns:
            TableDefinition for the recursive CTE
        """
        # Parse anchor and recursive parts
        # For recursive CTEs, select_node might be a Union
        if isinstance(cte.select_node, exp.Union):
            anchor_select, recursive_select = self._parse_recursive_cte(
                cte.select_node, cte.name
            )
        elif isinstance(cte.select_node, exp.Select):
            anchor_select, recursive_select = self._parse_recursive_cte(
                cte.select_node, cte.name
            )
        else:
            # Unknown structure - treat as normal CTE
            return self._analyze_normal_cte(cte, statement_index)
        
        if not anchor_select:
            # No anchor part - invalid recursive CTE structure, treat as normal CTE
            return self._analyze_normal_cte(cte, statement_index)
        
        # 1. Analyze anchor part (this gives us the base source tables)
        try:
            anchor_columns = self._analyze_cte_part(anchor_select, cte.name, is_anchor=True)
        except Exception as e:
            # If anchor analysis fails, log and fall back to normal CTE analysis
            # This prevents recursive CTE failures from breaking the entire statement
            return self._analyze_normal_cte(cte, statement_index)
        
        # Check if anchor columns are empty - if so, fall back to normal CTE analysis
        if not anchor_columns:
            # Anchor part produced no columns - likely an error, fall back to normal analysis
            return self._analyze_normal_cte(cte, statement_index)
        
        # 1.5. Register temporary CTE with anchor columns so recursive part can reference it
        # This allows DependencyExtractor to resolve CTE references in the recursive part
        temp_cte_table = TableDefinition(
            name=cte.name,
            table_type=TableType.CTE,
            columns=anchor_columns,
            created_at_statement=statement_index,
            is_recursive=True,
        )
        # Temporarily register it (we'll update it later with merged columns)
        self.registry.register_table(temp_cte_table)
        
        # 2. Analyze recursive part (if present)
        recursive_columns = {}
        if recursive_select:
            # Check recursion depth
            depth = self._estimate_recursion_depth(recursive_select, cte.name)
            if depth > max_depth:
                # Depth exceeds limit, analysis will be limited
                pass
            
            # Analyze recursive part
            # For recursive part, self-references to the CTE should resolve to anchor's sources
            recursive_columns = self._analyze_recursive_part(
                recursive_select, cte.name, anchor_columns, max_depth
            )
        
        # 3. Merge columns from anchor and recursive parts
        # For columns that appear in both, merge their sources
        merged_columns = {}
        
        # Start with anchor columns
        for col_name, lineage in anchor_columns.items():
            merged_columns[col_name] = lineage
        
        # Merge recursive columns
        for col_name, recursive_lineage in recursive_columns.items():
            if col_name in merged_columns:
                # Merge sources: anchor sources + recursive sources
                anchor_lineage = merged_columns[col_name]
                # Combine sources (deduplicate)
                all_sources = anchor_lineage.sources + recursive_lineage.sources
                # Deduplicate sources
                seen = set()
                unique_sources = []
                for source in all_sources:
                    key = source.to_qualified_name()
                    if key not in seen:
                        seen.add(key)
                        unique_sources.append(source)
                
                # Create merged lineage (prefer anchor's expression type)
                # Merge aggregate attributes (prefer anchor's)
                is_aggregate = anchor_lineage.is_aggregate or recursive_lineage.is_aggregate
                aggregate_function = anchor_lineage.aggregate_function or recursive_lineage.aggregate_function
                is_group_by = anchor_lineage.is_group_by or recursive_lineage.is_group_by

                merged_lineage = ColumnLineage(
                    name=col_name,
                    sources=unique_sources,
                    expression=anchor_lineage.expression or recursive_lineage.expression,
                    expression_type=anchor_lineage.expression_type or recursive_lineage.expression_type,
                    confidence=min(anchor_lineage.confidence, recursive_lineage.confidence),
                    is_aggregate=is_aggregate,
                    aggregate_function=aggregate_function,
                    is_group_by=is_group_by,
                )
                merged_columns[col_name] = merged_lineage
            else:
                # New column from recursive part
                merged_columns[col_name] = recursive_lineage
        
        # 4. Update the CTE table definition with merged columns
        # (it was already registered temporarily with anchor columns)
        temp_cte_table.columns = merged_columns
        # Update in registry
        self.registry.register_table(temp_cte_table)
        
        return temp_cte_table

    def _analyze_union_cte(
        self, cte: CTEDefinition, statement_index: int
    ) -> TableDefinition:
        """
        Analyze a CTE that contains UNION/UNION ALL.
        
        Args:
            cte: CTE definition with Union body
            statement_index: Statement index
            
        Returns:
            TableDefinition for the UNION CTE
        """
        if not isinstance(cte.select_node, exp.Union):
            raise ValueError("_analyze_union_cte requires Union node")
        
        # Collect all branches
        branches = self._collect_union_branches_for_cte(cte.select_node)
        
        # Build scopes for all branches and register source tables
        scope_builder = ScopeBuilder(
            config=self.config,
            schema_provider=self.schema_provider,
            registry=self.registry,
        )
        
        for branch in branches:
            if isinstance(branch, exp.Select):
                scope = scope_builder.build_scope(branch)
                # Auto-register source tables
                for table_ref in scope.tables.values():
                    table_name = table_ref.table
                    if not self.registry.has_table(table_name):
                        if self.schema_provider:
                            try:
                                columns = self.schema_provider.get_table_columns(
                                    table_ref.to_qualified_name()
                                )
                                self.registry.register_source_table(table_name, columns)
                            except Exception:
                                self.registry.register_source_table(table_name)
                        else:
                            self.registry.register_source_table(table_name)
        
        # Extract dependencies from UNION
        # DependencyExtractor handles UNION internally, but we need to ensure
        # the resolver has access to the registry for SELECT * expansion
        # Use first branch's scope (or create a combined scope)
        first_branch = branches[0] if branches else None
        if not first_branch or not isinstance(first_branch, exp.Select):
            raise LineageError("UNION CTE must have at least one SELECT branch")
        
        scope = scope_builder.build_scope(first_branch)
        resolver = SymbolResolver(scope, self.config, self.schema_provider)
        # IMPORTANT: Attach registry to resolver for SELECT * expansion (CTEs)
        resolver.registry = self.registry
        extractor = DependencyExtractor(scope, resolver, self.config)
        
        # Extract dependencies (DependencyExtractor now handles UNION)
        # The _extract_from_union method will create separate resolvers for each branch
        # and ensure they have access to the registry
        dependencies = extractor.extract(cte.select_node)
        
        # Convert to ColumnLineage
        column_lineages = self._convert_dependencies_to_lineages(dependencies)
        
        # Convert to dictionary
        columns = {}
        for lineage in column_lineages:
            columns[lineage.name] = lineage
        
        # Create CTE table definition
        cte_table = TableDefinition(
            name=cte.name,
            table_type=TableType.CTE,
            columns=columns,
            created_at_statement=statement_index,
            is_recursive=False,
        )
        return cte_table
    
    def _collect_union_branches_for_cte(
        self, union_node: exp.Union
    ) -> List[exp.Select]:
        """
        Collect all SELECT branches from a UNION structure for CTE analysis.
        
        Args:
            union_node: Union node
            
        Returns:
            List of all SELECT branch expressions
        """
        branches = []
        
        # Left side
        left = union_node.this
        if isinstance(left, exp.Union):
            branches.extend(self._collect_union_branches_for_cte(left))
        elif isinstance(left, exp.Select):
            branches.append(left)
        
        # Right side
        right = union_node.expression
        if isinstance(right, exp.Union):
            branches.extend(self._collect_union_branches_for_cte(right))
        elif isinstance(right, exp.Select):
            branches.append(right)
        
        return branches

    def _analyze_cte_part(
        self, select_node: exp.Expression, cte_name: str, is_anchor: bool = False
    ) -> Dict[str, ColumnLineage]:
        """
        Analyze a part of a CTE (anchor or recursive).
        
        Args:
            select_node: SELECT or Union statement node
            cte_name: Name of the CTE (for context)
            is_anchor: Whether this is the anchor part
            
        Returns:
            Dictionary of column name -> ColumnLineage
        """
        # Handle Union nodes
        if isinstance(select_node, exp.Union):
            # For Union, we need to build scopes for all branches
            branches = self._collect_union_branches_for_cte(select_node)
            scope_builder = ScopeBuilder(
                config=self.config,
                schema_provider=self.schema_provider,
                registry=self.registry,
            )
            # Build scope from first branch (for resolver context)
            if branches and isinstance(branches[0], exp.Select):
                scope = scope_builder.build_scope(branches[0])
                # Register source tables from all branches
                for branch in branches:
                    if isinstance(branch, exp.Select):
                        branch_scope = scope_builder.build_scope(branch)
                        for table_ref in branch_scope.tables.values():
                            table_name = table_ref.table
                            if not self.registry.has_table(table_name):
                                if self.schema_provider:
                                    try:
                                        columns = self.schema_provider.get_table_columns(
                                            table_ref.to_qualified_name()
                                        )
                                        self.registry.register_source_table(table_name, columns)
                                    except Exception:
                                        self.registry.register_source_table(table_name)
                                else:
                                    self.registry.register_source_table(table_name)
            else:
                scope = Scope()
        else:
            # Build scope for single SELECT
            scope_builder = ScopeBuilder(
                config=self.config,
                schema_provider=self.schema_provider,
                registry=self.registry,
            )
            scope = scope_builder.build_scope(select_node)
        
        # Auto-register source tables
        for table_ref in scope.tables.values():
            table_name = table_ref.table
            if not self.registry.has_table(table_name):
                if self.schema_provider:
                    try:
                        columns = self.schema_provider.get_table_columns(
                            table_ref.to_qualified_name()
                        )
                        self.registry.register_source_table(table_name, columns)
                    except Exception:
                        self.registry.register_source_table(table_name)
                else:
                    self.registry.register_source_table(table_name)
        
        # Extract dependencies
        try:
            resolver = SymbolResolver(scope, self.config, self.schema_provider)
            # Attach registry to resolver for CTE references
            resolver.registry = self.registry
            extractor = DependencyExtractor(scope, resolver, self.config)
            dependencies = extractor.extract(select_node)
            
            # Convert to ColumnLineage
            column_lineages = self._convert_dependencies_to_lineages(dependencies)
            
            # Convert to dictionary
            columns = {}
            for lineage in column_lineages:
                columns[lineage.name] = lineage
            
            return columns
        except Exception as e:
            # If extraction fails, return empty dict (will be handled by caller)
            # Log the error for debugging
            return {}

    def _analyze_recursive_part(
        self,
        recursive_select: exp.Select,
        cte_name: str,
        anchor_columns: Dict[str, ColumnLineage],
        max_depth: int,
    ) -> Dict[str, ColumnLineage]:
        """
        Analyze the recursive part of a recursive CTE.
        
        Key: When the recursive part references the CTE itself, resolve those
        references to the anchor's source columns (not the CTE itself).
        
        Args:
            recursive_select: Recursive part SELECT statement
            cte_name: Name of the recursive CTE
            anchor_columns: Column lineages from anchor part
            max_depth: Maximum recursion depth
            
        Returns:
            Dictionary of column name -> ColumnLineage
        """
        # First, analyze the recursive part normally
        recursive_columns = self._analyze_cte_part(recursive_select, cte_name, is_anchor=False)
        
        
        # Now, resolve self-references: replace CTE column references with anchor's sources
        resolved_columns = {}
        for col_name, lineage in recursive_columns.items():
            # Check if any sources reference the CTE itself
            resolved_sources = []
            has_self_reference = False
            self_referenced_columns = set()
            
            for source in lineage.sources:
                if source.table == cte_name:
                    # This is a self-reference - resolve to anchor's sources
                    has_self_reference = True
                    self_referenced_columns.add(source.column)
                    # Find the corresponding column in anchor
                    if source.column in anchor_columns:
                        # Use anchor's sources for this column
                        resolved_sources.extend(anchor_columns[source.column].sources)
                    elif col_name in anchor_columns:
                        # Column name matches (e.g., "h.level + 1" might map to "level")
                        # Use anchor's sources for this column
                        resolved_sources.extend(anchor_columns[col_name].sources)
                    else:
                        # Column doesn't exist in anchor - try to find by matching column names
                        # For expressions like "h.level + 1", try to match "level"
                        matched = False
                        for anchor_col_name in anchor_columns.keys():
                            # Try to match if the recursive column name contains the anchor column name
                            # or if the self-referenced column matches the anchor column
                            if (anchor_col_name in col_name or 
                                source.column == anchor_col_name or
                                col_name.replace("h.", "").replace(" + 1", "") == anchor_col_name):
                                resolved_sources.extend(anchor_columns[anchor_col_name].sources)
                                matched = True
                                break
                        if not matched:
                            # Keep the self-reference as fallback
                            resolved_sources.append(source)
                else:
                    # Not a self-reference, keep as is
                    resolved_sources.append(source)
            
            # If this column has no sources or is a computed expression that might reference CTE columns,
            # try to map it to anchor columns by matching column names
            if (not resolved_sources or (not has_self_reference and col_name not in anchor_columns)):
                # Check if column name suggests it's derived from anchor columns
                # (e.g., "h.level + 1" might be related to "level")
                for anchor_col_name in anchor_columns.keys():
                    # Try various matching strategies
                    normalized_col_name = col_name.lower().replace("h.", "").replace("eh.", "").replace(" ", "")
                    normalized_anchor = anchor_col_name.lower()
                    
                    # Match if:
                    # 1. Anchor column name is contained in recursive column name
                    # 2. Recursive column name without qualifiers and operations matches anchor
                    # 3. Direct match (already checked above but check again)
                    if (anchor_col_name.lower() in col_name.lower() or 
                        normalized_col_name.replace("+1", "").replace("+", "").replace("-1", "").replace("-", "") == normalized_anchor or
                        col_name.replace("h.", "").replace("eh.", "").replace(" + 1", "").replace(" - 1", "").strip() == anchor_col_name):
                        # This might be a computed version of an anchor column
                        # Include anchor's sources
                        resolved_sources.extend(anchor_columns[anchor_col_name].sources)
                        break
            
            # Deduplicate sources
            seen = set()
            unique_sources = []
            for source in resolved_sources:
                key = source.to_qualified_name()
                if key not in seen:
                    seen.add(key)
                    unique_sources.append(source)
            
            # Determine final column name: prefer anchor column name if it matches
            final_col_name = col_name
            if col_name not in anchor_columns:
                # Try to find matching anchor column name
                # Normalize the recursive column name by removing common patterns
                normalized_col_name = col_name.lower().strip()
                
                # Remove table qualifiers (h., eh., el., e., etc.) - handle various formats
                import re
                # Remove patterns like "el.", "eh.", "h.", "e." at the start or middle
                normalized_col_name = re.sub(r'^[a-z]+\.', '', normalized_col_name)  # Remove "el." at start
                normalized_col_name = re.sub(r'[a-z]+\.', '', normalized_col_name)  # Remove any "xxx." pattern
                
                # Remove common arithmetic operations and whitespace
                normalized_col_name = re.sub(r'\s*\+\s*1\s*', '', normalized_col_name)  # Remove "+ 1", "+1", etc.
                normalized_col_name = re.sub(r'\s*-\s*1\s*', '', normalized_col_name)  # Remove "- 1", "-1", etc.
                normalized_col_name = re.sub(r'\s*\+\s*', '', normalized_col_name)  # Remove any "+"
                normalized_col_name = re.sub(r'\s*-\s*', '', normalized_col_name)  # Remove any "-"
                normalized_col_name = normalized_col_name.replace(" ", "").strip()
                
                for anchor_col_name in anchor_columns.keys():
                    normalized_anchor = anchor_col_name.lower().strip()
                    
                    # Try multiple matching strategies
                    if (normalized_col_name == normalized_anchor or
                        normalized_col_name.endswith(normalized_anchor) or
                        normalized_anchor in normalized_col_name or
                        anchor_col_name.lower() in col_name.lower()):
                        final_col_name = anchor_col_name
                        break
            
            # Create resolved lineage
            resolved_lineage = ColumnLineage(
                name=final_col_name,
                sources=unique_sources,
                expression=lineage.expression,
                expression_type=lineage.expression_type,
                confidence=lineage.confidence * 0.9,  # Slightly lower confidence for recursive
                is_aggregate=lineage.is_aggregate,
                aggregate_function=lineage.aggregate_function,
                is_group_by=lineage.is_group_by,
            )
            resolved_columns[final_col_name] = resolved_lineage
        
        return resolved_columns

    def _estimate_recursion_depth(self, select_node: exp.Select, cte_name: str) -> int:
        """
        Estimate the recursion depth of a recursive CTE.
        
        This is a simple heuristic - in practice, recursion depth depends on data.
        We estimate based on the structure of the recursive query.
        
        Args:
            select_node: Recursive part SELECT statement
            cte_name: Name of the recursive CTE
            
        Returns:
            Estimated recursion depth
        """
        # Simple heuristic: count how many times the CTE is referenced
        # This is a rough estimate
        count = 0
        
        def count_references(node: exp.Expression) -> int:
            nonlocal count
            if isinstance(node, exp.Table) and node.name == cte_name:
                count += 1
            for key, value in node.args.items():
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, exp.Expression):
                            count_references(item)
                elif isinstance(value, exp.Expression):
                    count_references(value)
            return count
        
        count_references(select_node)
        # Return a conservative estimate (multiply by a factor)
        return max(count * 10, 1)

    def _convert_dependencies_to_lineages(
        self, dependencies: List
    ) -> List[ColumnLineage]:
        """Convert ColumnDependency list to ColumnLineage list.

        This method groups dependencies by target column and merges
        all sources for each target.

        Args:
            dependencies: List of ColumnDependency objects

        Returns:
            List[ColumnLineage]: Deduplicated and merged column lineages
        """
        from collections import defaultdict

        # Group by target column
        grouped: Dict[str, List] = defaultdict(list)
        for dep in dependencies:
            target_name = dep.target.column
            grouped[target_name].append(dep)

        # Build ColumnLineage for each target column
        lineages = []
        for target_name, deps in grouped.items():
            # Collect all source columns (filter out placeholder constants)
            sources = []
            for dep in deps:
                # Filter out __CONSTANT__ placeholder sources
                if dep.source.table != "__CONSTANT__":
                    sources.append(dep.source)

            # Extract expression (use first dependency's expression)
            expression = deps[0].expression if deps else None
            expression_type = deps[0].expression_type if deps else None
            confidence = deps[0].confidence if deps else 1.0

            # Extract aggregate attributes
            is_aggregate = deps[0].is_aggregate if deps else False
            aggregate_function = deps[0].aggregate_function if deps else None
            is_group_by = deps[0].is_group_by if deps else False

            # Create ColumnLineage
            # Note: sources may be empty for constants, but the column still exists
            lineage = ColumnLineage(
                name=target_name,
                sources=sources,  # Empty for constants, but column still created
                expression=expression,
                expression_type=expression_type,
                confidence=confidence,
                is_aggregate=is_aggregate,
                aggregate_function=aggregate_function,
                is_group_by=is_group_by,
            )

            lineages.append(lineage)

        return lineages

    def has_ctes(self, select_node: exp.Select) -> bool:
        """
        Check if SELECT statement contains CTEs.

        Args:
            select_node: SELECT statement node

        Returns:
            bool: Whether there are CTEs
        """
        return select_node.args.get("with") is not None

    def _has_recursive_structure_in_union(self, union_node: exp.Union, cte_name: str) -> bool:
        """
        Check if a Union node has recursive CTE structure.
        
        Args:
            union_node: Union node
            cte_name: Name of the CTE being checked
            
        Returns:
            bool: True if the structure is recursive
        """
        left = union_node.this
        right = union_node.expression
        
        # At least one part should reference the CTE
        left_refs = self._references_cte(left, cte_name) if isinstance(left, exp.Expression) else False
        right_refs = self._references_cte(right, cte_name) if isinstance(right, exp.Expression) else False
        
        return left_refs or right_refs
    
    def _has_recursive_structure(self, select_node: exp.Select, cte_name: str) -> bool:
        """
        Check if a SELECT statement has recursive CTE structure.
        
        A recursive CTE must have:
        1. UNION or UNION ALL
        2. The recursive part must reference the CTE itself
        
        Args:
            select_node: SELECT statement node
            cte_name: Name of the CTE being checked
            
        Returns:
            bool: True if the structure is recursive
        """
        # Check if there's a UNION or UNION ALL
        if not isinstance(select_node, exp.Select):
            return False
            
        # Check for UNION/UNION ALL in the query
        # In sqlglot, UNION is represented as a Union node that wraps Select nodes
        # We need to check if the select_node is part of a Union
        parent = getattr(select_node, 'parent', None)
        if parent and isinstance(parent, exp.Union):
            # This is part of a UNION, check if recursive part references CTE
            return self._references_cte(select_node, cte_name)
        
        # Also check if this Select itself contains a UNION
        # (the recursive part might be in a subquery or join)
        return self._references_cte(select_node, cte_name) and self._has_union(select_node)
    
    def _has_union(self, node: exp.Expression) -> bool:
        """Check if a node contains UNION or UNION ALL."""
        if isinstance(node, exp.Union):
            return True
        # Recursively check children
        for child in node.args.values():
            if isinstance(child, list):
                for item in child:
                    if isinstance(item, exp.Expression) and self._has_union(item):
                        return True
            elif isinstance(child, exp.Expression):
                if self._has_union(child):
                    return True
        return False
    
    def _references_cte(self, node: exp.Expression, cte_name: str) -> bool:
        """
        Check if a node references a CTE by name.
        
        Args:
            node: AST node to check
            cte_name: Name of the CTE to look for
            
        Returns:
            bool: True if the node references the CTE
        """
        # Check if this is a Table node with the CTE name
        if isinstance(node, exp.Table) and node.name == cte_name:
            return True
        
        # Recursively check children
        for key, value in node.args.items():
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, exp.Expression) and self._references_cte(item, cte_name):
                        return True
            elif isinstance(value, exp.Expression):
                if self._references_cte(value, cte_name):
                    return True
        
        return False
    
    def _parse_recursive_cte(self, node: exp.Expression, cte_name: str) -> tuple[Optional[exp.Select], Optional[exp.Select]]:
        """
        Parse a recursive CTE to separate anchor and recursive parts.
        
        A recursive CTE has the structure:
        SELECT ... (anchor part)
        UNION [ALL]
        SELECT ... FROM cte_name ... (recursive part)
        
        In sqlglot, the CTE's 'this' field may be a Union node that contains
        the anchor and recursive Select statements.
        
        Args:
            node: The SELECT or Union node from the CTE
            cte_name: Name of the recursive CTE
            
        Returns:
            Tuple of (anchor_select, recursive_select), either may be None
        """
        # In sqlglot, when a CTE has UNION, the CTE's 'this' field is a Union node
        # The Union node has 'this' (left) and 'expression' (right) fields
        # We need to check if node is actually a Union or if it's a Select
        
        # Check if node itself is a Union (this is the common case for recursive CTEs)
        node_to_check = node
        
        # If the node has a parent that is Union, or if it's part of a Union structure
        # we need to traverse up or check the structure differently
        # Actually, in sqlglot CTE structure, the CTE.this might be a Union directly
        # Let's check if we can find a Union in the structure
        
        # First, check if this node is actually a Union
        if isinstance(node_to_check, exp.Union):
            left = node_to_check.this
            right = node_to_check.expression
            
            # Determine which is anchor and which is recursive
            # Anchor doesn't reference the CTE, recursive does
            left_refs = self._references_cte(left, cte_name) if isinstance(left, (exp.Select, exp.Union)) else False
            right_refs = self._references_cte(right, cte_name) if isinstance(right, (exp.Select, exp.Union)) else False
            
            if left_refs and not right_refs:
                # Left is recursive, right is anchor
                # Ensure we return Select nodes
                anchor = right if isinstance(right, exp.Select) else None
                recursive = left if isinstance(left, exp.Select) else None
                return (anchor, recursive)
            elif right_refs and not left_refs:
                # Right is recursive, left is anchor
                anchor = left if isinstance(left, exp.Select) else None
                recursive = right if isinstance(right, exp.Select) else None
                return (anchor, recursive)
            elif not left_refs and not right_refs:
                # Neither references CTE - not a valid recursive CTE structure
                # Treat first as anchor
                anchor = left if isinstance(left, exp.Select) else None
                return (anchor, None)
            else:
                # Both reference CTE - complex case, treat first as anchor
                anchor = left if isinstance(left, exp.Select) else None
                recursive = right if isinstance(right, exp.Select) else None
                return (anchor, recursive)
        
        # If it's a Select, check if it references the CTE
        if isinstance(node_to_check, exp.Select):
            if self._references_cte(node_to_check, cte_name):
                # References itself - this might be just the recursive part
                # or the whole thing is malformed
                return (None, node_to_check)
            else:
                # Doesn't reference itself - might be anchor only
                # But a recursive CTE should have UNION, so this is unusual
                return (node_to_check, None)
        
        # Fallback: treat as anchor only
        if isinstance(node_to_check, exp.Select):
            return (node_to_check, None)
        
        return (None, None)

