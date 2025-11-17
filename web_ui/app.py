"""
Lineage Glass Web UI

Simple Flask application for SQL lineage visualization
"""

from flask import Flask, render_template, request, jsonify
import sys
import os

# Add parent directory to path, import lineage_analyzer
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from lineage_analyzer.analyzer.script_analyzer import ScriptAnalyzer

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size


@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')


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


if __name__ == '__main__':
    print("Starting Lineage Glass Web UI...")
    print("Open http://localhost:5000 in your browser")
    app.run(debug=True, host='0.0.0.0', port=5000)

