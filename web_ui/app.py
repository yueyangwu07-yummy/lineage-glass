"""
Lineage Glass Web UI

Simple Flask application for SQL lineage visualization
"""

from flask import Flask, render_template, request, jsonify
import sys
import os

# Force unbuffered output for debugging
sys.stdout = sys.__stdout__
sys.stderr = sys.__stderr__

# Add parent directory to path, import lineage_analyzer
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from lineage_analyzer.analyzer.script_analyzer import ScriptAnalyzer

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Global variable to store the most recent analysis result (for field-level lineage queries)
current_analysis_result = None

# Add request logging for debugging
@app.before_request
def log_request_info():
    if request.path.startswith('/api/field-lineage'):
        print(f"[REQUEST] {request.method} {request.path}", flush=True)
        print(f"[REQUEST] Args: {dict(request.args)}", flush=True)


@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')


@app.route('/api/example-sql', methods=['GET'])
def get_example_sql():
    """Load example SQL from examples/ecommerce/pipeline.sql"""
    try:
        # Get the path to the example SQL file
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        example_path = os.path.join(project_root, 'examples', 'ecommerce', 'pipeline.sql')
        
        # Read and return the SQL content
        with open(example_path, 'r', encoding='utf-8') as f:
            sql_content = f.read()
        
        return jsonify({'sql': sql_content})
    
    except FileNotFoundError:
        return jsonify({'error': 'Example SQL file not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/analyze', methods=['POST'])
def analyze():
    """
    Analyze SQL script
    
    Receives:
    - sql: SQL script text
    - or file: uploaded SQL file
    
    Returns:
    - tables: table list
    - lineages: lineage relationships
    - graph: graph data (for Cytoscape)
    """
    global current_analysis_result  # Add this line
    
    try:
        # Get SQL text
        sql_text = None
        
        if 'file' in request.files:
            file = request.files['file']
            if file.filename:
                sql_text = file.read().decode('utf-8')
        
        if not sql_text and 'sql' in request.form:
            sql_text = request.form['sql']
        
        if not sql_text:
            return jsonify({'error': 'No SQL provided'}), 400
        
        # Analyze SQL
        analyzer = ScriptAnalyzer()
        result = analyzer.analyze_script(sql_text)
        
        # Save result to global variable (for field-level lineage queries)
        current_analysis_result = result
        
        # Convert to JSON format
        response_data = {
            'tables': serialize_tables(result.registry),
            'graph': generate_graph_data(result.registry)
        }
        
        return jsonify(response_data)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def serialize_tables(registry):
    """Convert TableRegistry to JSON format"""
    tables = []
    
    for table_name, table_def in registry.tables.items():
        columns = []
        
        for col_name, col_lineage in table_def.columns.items():
            # Serialize source columns
            sources = []
            if col_lineage.sources:
                for src in col_lineage.sources:
                    sources.append({
                        'table': src.table,
                        'column': src.column
                    })
            
            columns.append({
                'name': col_name,
                'sources': sources,
                'expression': col_lineage.expression,
                'is_aggregate': col_lineage.is_aggregate,
                'aggregate_function': col_lineage.aggregate_function,
                'is_group_by': col_lineage.is_group_by
            })
        
        table_type = table_def.table_type.value if table_def.table_type else 'UNKNOWN'
        
        tables.append({
            'name': table_name,
            'type': table_type,
            'columns': columns
        })
    
    return tables


def generate_graph_data(registry):
    """
    Generate graph data for Cytoscape.js
    
    Returns:
    {
        'nodes': [{'data': {'id': 'table1', 'label': 'table1', 'type': 'TABLE'}}],
        'edges': [{'data': {'source': 'table1', 'target': 'table2'}}]
    }
    """
    nodes = []
    edges = []
    node_ids = set()
    edge_set = set()
    
    for table_name, table_def in registry.tables.items():
        # Add table node
        if table_name not in node_ids:
            table_type = table_def.table_type.value if table_def.table_type else 'UNKNOWN'
            nodes.append({
                'data': {
                    'id': table_name,
                    'label': table_name,
                    'type': table_type,
                    'column_count': len(table_def.columns)
                }
            })
            node_ids.add(table_name)
        
        # Add edges (table to table dependencies)
        source_tables = set()
        for col_lineage in table_def.columns.values():
            if col_lineage.sources:
                for src in col_lineage.sources:
                    source_tables.add(src.table)
        
        for source_table in source_tables:
            # Add source table node (if doesn't exist)
            if source_table not in node_ids:
                nodes.append({
                    'data': {
                        'id': source_table,
                        'label': source_table,
                        'type': 'EXTERNAL',  # External table
                        'column_count': 0
                    }
                })
                node_ids.add(source_table)
            
            # Add edge
            edge_id = f"{source_table}->{table_name}"
            if edge_id not in edge_set:
                edges.append({
                    'data': {
                        'source': source_table,
                        'target': table_name
                    }
                })
                edge_set.add(edge_id)
    
    return {
        'nodes': nodes,
        'edges': edges
    }


@app.route('/api/field-lineage/<table>/<column>', methods=['GET'])
def field_lineage(table, column):
    """
    Get complete lineage path for a single field
    
    Parameters:
        table: Table name
        column: Column name
    
    Returns:
        {
            'field': 'table.column',
            'path': [...],  # Lineage path node list
            'graph': {...}  # Cytoscape graph data
        }
    """
    import time
    global current_analysis_result
    
    # Log immediately when endpoint is called
    print(f"[API] field_lineage endpoint called: table={table}, column={column}", flush=True)
    print(f"[API] current_analysis_result exists: {current_analysis_result is not None}", flush=True)
    
    if not current_analysis_result:
        print("[API] ERROR: No analysis result available", flush=True)
        return jsonify({'error': 'No analysis result available. Please analyze SQL first.'}), 400
    
    try:
        start_time = time.time()
        
        # Log start
        print(f"[DEBUG] Starting field lineage for {table}.{column}...", flush=True)
        
        # Step 1: Trace field lineage (THIS IS THE FIRST STEP)
        trace_start = time.time()
        print(f"[DEBUG] Calling trace_field_lineage...", flush=True)
        
        path_nodes = trace_field_lineage(
            current_analysis_result, 
            table, 
            column
        )
        
        trace_time = time.time() - trace_start
        
        print(f"[DEBUG] trace_field_lineage completed in {trace_time:.3f}s", flush=True)
        print(f"[DEBUG] path_nodes length: {len(path_nodes)}", flush=True)
        
        if not path_nodes:
            print(f"[DEBUG] No path nodes found, returning 404", flush=True)
            return jsonify({
                'error': f'Field {table}.{column} not found or has no lineage'
            }), 404
        
        # Step 2: Build field-level graph data (THIS IS THE SECOND STEP)
        build_start = time.time()
        print(f"[DEBUG] Calling build_field_graph...", flush=True)
        
        graph_data = build_field_graph(path_nodes)
        
        build_time = time.time() - build_start
        
        print(f"[DEBUG] build_field_graph completed in {build_time:.3f}s", flush=True)
        
        total_time = time.time() - start_time
        
        # Log performance
        print(f"[Performance] Field lineage for {table}.{column}:", flush=True)
        print(f"  - Trace: {trace_time:.3f}s", flush=True)
        print(f"  - Build graph: {build_time:.3f}s", flush=True)
        print(f"  - Total: {total_time:.3f}s", flush=True)
        print(f"  - Nodes: {len(graph_data['nodes'])}, Edges: {len(graph_data['edges'])}", flush=True)
        print(f"[DEBUG] Returning response...", flush=True)
        
        return jsonify({
            'field': f"{table}.{column}",
            'path': path_nodes,
            'graph': graph_data
        })
    
    except Exception as e:
        import traceback
        if app.debug:
            traceback.print_exc()
        return jsonify({'error': str(e)}), 500


def trace_field_lineage(result, table, column, visited=None, level=0, max_depth=10):
    """
    Recursively trace field lineage path
    
    Parameters:
        result: ScriptAnalysisResult object
        table: Table name
        column: Column name
        visited: Set of visited nodes (to avoid cycles)
        level: Current depth level
        max_depth: Maximum recursion depth
    
    Returns:
        List of lineage nodes, each node contains:
        {
            'level': 0,
            'table': 'result',
            'column': 'total_revenue',
            'transformation': 'SUM(revenue)',
            'is_aggregate': True,
            'aggregate_function': 'SUM',
            'is_group_by': False,
            'sources': [...]  # List of child nodes
        }
    """
    if visited is None:
        visited = set()
    
    # Prevent infinite recursion
    if level >= max_depth:
        return []
    
    # Debug: Log deep recursion
    if level > 5:
        print(f"[DEBUG] Deep recursion: level={level}, table={table}, column={column}", flush=True)
    
    # Normalize table name (registry uses lowercase)
    table_normalized = table.lower().strip()
    
    # Build node key
    key = f"{table_normalized}.{column}"
    if key in visited:
        return []  # Avoid cycles
    visited.add(key)
    
    # Get table definition
    table_def = result.registry.tables.get(table_normalized)
    if not table_def:
        # External table (no definition), treat as leaf node
        return [{
            'level': level,
            'table': table_normalized,
            'column': column,
            'transformation': None,
            'is_aggregate': False,
            'aggregate_function': None,
            'is_group_by': False,
            'sources': []
        }]
    
    # Get column lineage
    if column not in table_def.columns:
        # If table is EXTERNAL type, treat missing columns as leaf nodes (source fields)
        from lineage_analyzer.models.table_definition import TableType
        if table_def.table_type == TableType.EXTERNAL:
            return [{
                'level': level,
                'table': table_normalized,
                'column': column,
                'transformation': None,
                'is_aggregate': False,
                'aggregate_function': None,
                'is_group_by': False,
                'sources': []
            }]
        # For other table types, return empty if column not found
        return []
    
    col_lineage = table_def.columns[column]
    
    # Debug: Check sources
    # col_lineage.sources is a list of ColumnRef objects
    sources_list = col_lineage.sources if hasattr(col_lineage, 'sources') else []
    
    # Build current node
    node = {
        'level': level,
        'table': table_normalized,
        'column': column,
        'transformation': col_lineage.expression,
        'is_aggregate': getattr(col_lineage, 'is_aggregate', False),
        'aggregate_function': getattr(col_lineage, 'aggregate_function', None),
        'is_group_by': getattr(col_lineage, 'is_group_by', False),
        'sources': []
    }
    
    # Recursively trace source fields
    if sources_list and len(sources_list) > 0:
        for src in sources_list:
            # Check if already visited before recursing (early exit optimization)
            src_key = f"{src.table.lower().strip()}.{src.column}"
            if src_key in visited:
                continue  # Skip if already visited
            
            # Create a new visited set copy for each source branch
            # This allows different branches to explore independently
            src_visited = visited.copy()
            src_path = trace_field_lineage(
                result,
                src.table,
                src.column,
                src_visited,
                level + 1,
                max_depth
            )
            
            if src_path:
                node['sources'].extend(src_path)
    
    return [node]


def build_field_graph(path_nodes):
    """
    Convert field lineage path to Cytoscape graph data
    
    Parameters:
        path_nodes: List of nodes returned by trace_field_lineage
    
    Returns:
        {
            'nodes': [...],  # Node list
            'edges': [...]   # Edge list
        }
    """
    nodes = []
    edges = []
    node_ids = set()
    edge_set = set()
    
    def process_node(node, parent_id=None):
        """Recursively process nodes to build graph data"""
        node_id = f"{node['table']}.{node['column']}"
        
        # Add node (if not already added)
        if node_id not in node_ids:
            # Build node label
            label = node['column']
            if node['table']:
                label = f"{node['column']}\n({node['table']})"
            
            # Add badge information
            badge = ''
            if node['is_aggregate'] and node['aggregate_function']:
                badge = node['aggregate_function']
            elif node['is_group_by']:
                badge = 'GROUP BY'
            
            nodes.append({
                'data': {
                    'id': node_id,
                    'label': label,
                    'table': node['table'],
                    'column': node['column'],
                    'level': node['level'],
                    'transformation': node.get('transformation'),
                    'is_aggregate': node.get('is_aggregate', False),
                    'aggregate_function': node.get('aggregate_function'),
                    'is_group_by': node.get('is_group_by', False),
                    'badge': badge
                }
            })
            node_ids.add(node_id)
        
        # Add edge (from source to target)
        if parent_id:
            edge_id = f"{node_id}->{parent_id}"
            
            if edge_id not in edge_set:
                # Build edge label
                edge_label = ''
                if node.get('transformation'):
                    # Simplify transformation expression (avoid too long)
                    trans = node['transformation']
                    if len(trans) > 30:
                        trans = trans[:27] + '...'
                    edge_label = trans
                
                edges.append({
                    'data': {
                        'id': edge_id,
                        'source': node_id,
                        'target': parent_id,
                        'label': edge_label,
                        'transformation': node.get('transformation'),
                        'is_aggregate': node.get('is_aggregate', False)
                    }
                })
                edge_set.add(edge_id)
        
        # Recursively process source fields
        for src_node in node.get('sources', []):
            process_node(src_node, node_id)
    
    # Process all root nodes
    for node in path_nodes:
        process_node(node)
    
    return {
        'nodes': nodes,
        'edges': edges
    }


if __name__ == '__main__':
    print("Starting Lineage Glass Web UI...")
    print("Open http://localhost:5000 in your browser")
    app.run(debug=True, host='0.0.0.0', port=5000)

