// Global variables
let currentData = null;
let cy = null;
let currentView = 'table';
let currentFieldInfo = null;

// ==================== Tab Switching ====================
document.getElementById('tab-text').addEventListener('click', () => {
    switchTab('text');
});

document.getElementById('tab-file').addEventListener('click', () => {
    switchTab('file');
});

function switchTab(tab) {
    const textTab = document.getElementById('tab-text');
    const fileTab = document.getElementById('tab-file');
    const textPanel = document.getElementById('input-text');
    const filePanel = document.getElementById('input-file');
    
    if (tab === 'text') {
        textTab.classList.add('active');
        fileTab.classList.remove('active');
        textPanel.classList.remove('hidden');
        filePanel.classList.add('hidden');
    } else {
        fileTab.classList.add('active');
        textTab.classList.remove('active');
        filePanel.classList.remove('hidden');
        textPanel.classList.add('hidden');
    }
}

// ==================== File Input ====================
const fileInput = document.getElementById('file-input');
const fileName = document.getElementById('file-name');

fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        fileName.textContent = `Selected: ${e.target.files[0].name}`;
    }
});

// ==================== Load Example Button ====================
document.getElementById('load-example').addEventListener('click', async () => {
    try {
        showLoading();
        hideError();
        
        const response = await fetch('/api/example-sql');
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to load example SQL');
        }
        
        const data = await response.json();
        
        // Switch to text tab
        switchTab('text');
        
        // Fill the textarea with example SQL
        document.getElementById('sql-input').value = data.sql;
        
        // Scroll to textarea
        document.getElementById('sql-input').scrollIntoView({ behavior: 'smooth', block: 'center' });
        
    } catch (error) {
        showError(`Failed to load example: ${error.message}`);
    } finally {
        hideLoading();
    }
});

// ==================== Clear Button ====================
document.getElementById('clear-btn').addEventListener('click', () => {
    document.getElementById('sql-input').value = '';
    fileInput.value = '';
    fileName.textContent = '';
    hideResults();
    hideError();
});

// ==================== Analyze Button ====================
document.getElementById('analyze-btn').addEventListener('click', async () => {
    await analyzeSQL();
});

// ==================== Main Analysis ====================
async function analyzeSQL() {
    let sqlText = '';
    const activeTab = document.querySelector('.tab-button.active').id;
    
    if (activeTab === 'tab-text') {
        sqlText = document.getElementById('sql-input').value.trim();
        if (!sqlText) {
            showError('Please enter SQL code');
            return;
        }
    } else {
        const file = fileInput.files[0];
        if (!file) {
            showError('Please select a file');
            return;
        }
        sqlText = await file.text();
    }
    
    showLoading();
    hideError();
    hideResults();
    
    try {
        const formData = new FormData();
        formData.append('sql', sqlText);
        
        const response = await fetch('/api/analyze', {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Analysis failed');
        }
        
        const data = await response.json();
        currentData = data;
        displayResults(data);
        
    } catch (error) {
        showError(`Error: ${error.message}`);
    } finally {
        hideLoading();
    }
}

function displayResults(data) {
    document.getElementById('results').classList.remove('hidden');
    renderTableList(data.tables);
    renderGraph(data.graph);
    document.getElementById('export-btn').classList.remove('hidden');
}

// ==================== Table List ====================
function renderTableList(tables) {
    const tableList = document.getElementById('table-list');
    tableList.innerHTML = '';
    
    tables.forEach(table => {
        const tableDiv = document.createElement('div');
        tableDiv.className = 'table-item';
        tableDiv.innerHTML = `
            <div class="font-semibold">${getTableIcon(table.type)} ${table.name}</div>
            <div class="text-xs text-gray-500 mt-1">${table.columns.length} columns</div>
        `;
        
        tableDiv.addEventListener('click', () => {
            showTableDetails(table);
            highlightTableInGraph(table.name);
        });
        
        tableList.appendChild(tableDiv);
    });
}

function getTableIcon(type) {
    const icons = {
        'TABLE': '📦',
        'VIEW': '👁️',
        'CTE': '🔄',
        'SUBQUERY': '📊',
        'EXTERNAL': '🌐'
    };
    return icons[type] || '📋';
}

// ==================== Table Graph ====================
function renderGraph(graphData) {
    cy = cytoscape({
        container: document.getElementById('cy'),
        elements: {
            nodes: graphData.nodes,
            edges: graphData.edges
        },
        style: [
            {
                selector: 'node',
                style: {
                    'label': 'data(label)',
                    'background-color': (ele) => getNodeColor(ele.data('type')),
                    'width': 60,
                    'height': 60,
                    'text-valign': 'bottom',
                    'text-halign': 'center',
                    'text-margin-y': 5,
                    'font-size': '12px',
                    'color': '#333'
                }
            },
            {
                selector: 'edge',
                style: {
                    'width': 2,
                    'line-color': '#93c5fd',
                    'target-arrow-color': '#3b82f6',
                    'target-arrow-shape': 'triangle',
                    'curve-style': 'bezier'
                }
            },
            {
                selector: 'node:selected',
                style: {
                    'border-width': 3,
                    'border-color': '#3b82f6'
                }
            }
        ],
        layout: {
            name: 'breadthfirst',
            directed: true,
            spacingFactor: 1.5,
            padding: 30
        }
    });
    
    cy.on('tap', 'node', function(evt) {
        const nodeId = evt.target.id();
        const table = currentData.tables.find(t => t.name === nodeId);
        if (table) {
            showTableDetails(table);
        }
    });
}

function getNodeColor(type) {
    const colors = {
        'TABLE': '#60a5fa',
        'VIEW': '#34d399',
        'CTE': '#fbbf24',
        'SUBQUERY': '#a78bfa',
        'EXTERNAL': '#d1d5db'
    };
    return colors[type] || '#9ca3af';
}

function highlightTableInGraph(tableName) {
    if (!cy) return;
    cy.nodes().removeClass('selected');
    cy.getElementById(tableName).addClass('selected');
    cy.center(cy.getElementById(tableName));
}

// ==================== Table Details ====================
function showTableDetails(table) {
    const detailPanel = document.getElementById('detail-panel');
    
    let html = `
        <div class="border-b pb-3 mb-3">
            <h4 class="font-semibold text-lg">${table.name}</h4>
            <p class="text-sm text-gray-500">${table.type}</p>
        </div>
        <div class="space-y-3">
            <h5 class="font-semibold text-sm">Columns (${table.columns.length})</h5>
    `;
    
    table.columns.forEach(col => {
        let badge = '';
        if (col.is_aggregate) {
            badge = `<span class="text-xs bg-purple-100 text-purple-700 px-2 py-1 rounded">${col.aggregate_function}</span>`;
        } else if (col.is_group_by) {
            badge = `<span class="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded">GROUP BY</span>`;
        }
        
        const safeTableName = table.name.replace(/'/g, "\\'");
        const safeColName = col.name.replace(/'/g, "\\'");
        
        html += `
            <div class="border rounded p-2 text-sm hover:bg-blue-50 transition cursor-pointer" 
                 onclick="showFieldLineageView('${safeTableName}', '${safeColName}')">
                <div class="flex justify-between items-center">
                    <div class="font-mono font-semibold">${col.name} ${badge}</div>
                    <span class="text-xs text-blue-600">🔍 View lineage</span>
                </div>
        `;
        
        if (col.sources && col.sources.length > 0) {
            html += '<div class="mt-1 text-gray-600 text-xs">Sources:</div>';
            col.sources.forEach(src => {
                html += `<div class="ml-2 text-xs text-gray-700">← ${src.table}.${src.column}</div>`;
            });
        }
        
        if (col.expression) {
            html += `<div class="mt-1 text-xs text-gray-500 font-mono">${col.expression}</div>`;
        }
        
        html += '</div>';
    });
    
    html += '</div>';
    detailPanel.innerHTML = html;
}

// ==================== Field Lineage View ====================
async function showFieldLineageView(table, column) {
    currentView = 'field';
    currentFieldInfo = { table, column };
    
    try {
        const response = await fetch(`/api/field-lineage/${encodeURIComponent(table)}/${encodeURIComponent(column)}`);
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to fetch field lineage');
        }
        
        const data = await response.json();
        
        updateViewControls('field');
        document.getElementById('current-field-name').textContent = data.field;
        document.getElementById('field-view-info').classList.remove('hidden');
        
        renderFieldGraph(data.graph);
        
    } catch (error) {
        showError(`Failed to load field lineage: ${error.message}`);
        backToTableView();
    }
}

function backToTableView() {
    currentView = 'table';
    currentFieldInfo = null;
    
    updateViewControls('table');
    document.getElementById('field-view-info').classList.add('hidden');
    
    if (currentData) {
        renderGraph(currentData.graph);
    }
}

function updateViewControls(view) {
    const tableBtn = document.getElementById('btn-table-view');
    const fieldBtn = document.getElementById('btn-field-view');
    const tableLegend = document.getElementById('table-legend');
    const fieldLegend = document.getElementById('field-legend');
    const tableHint = document.getElementById('table-view-hint');
    const fieldHint = document.getElementById('field-view-hint');
    
    if (view === 'table') {
        tableBtn.classList.add('active');
        fieldBtn.classList.remove('active');
        fieldBtn.classList.add('hidden');
        
        // Switch legend
        tableLegend.classList.remove('hidden');
        fieldLegend.classList.add('hidden');
        tableHint.classList.remove('hidden');
        fieldHint.classList.add('hidden');
    } else {
        tableBtn.classList.remove('active');
        fieldBtn.classList.add('active');
        fieldBtn.classList.remove('hidden');
        
        // Switch legend
        tableLegend.classList.add('hidden');
        fieldLegend.classList.remove('hidden');
        tableHint.classList.add('hidden');
        fieldHint.classList.remove('hidden');
    }
}

function renderFieldGraph(graphData) {
    cy = cytoscape({
        container: document.getElementById('cy'),
        
        elements: {
            nodes: graphData.nodes,
            edges: graphData.edges
        },
        
        style: [
            {
                selector: 'node',
                style: {
                    'label': 'data(label)',
                    'background-color': (ele) => {
                        if (ele.data('is_aggregate')) {
                            return '#ec4899';
                        } else if (ele.data('is_group_by')) {
                            return '#8b5cf6';
                        }
                        return '#60a5fa';
                    },
                    'width': 80,
                    'height': 80,
                    'text-valign': 'center',
                    'text-halign': 'center',
                    'font-size': '11px',
                    'color': '#fff',
                    'text-wrap': 'wrap',
                    'text-max-width': '70px',
                    'border-width': 2,
                    'border-color': '#fff'
                }
            },
            {
                selector: 'node[badge]',
                style: {
                    'label': (ele) => {
                        const label = ele.data('label');
                        const badge = ele.data('badge');
                        return badge ? `${label}\n[${badge}]` : label;
                    }
                }
            },
            {
                selector: 'edge',
                style: {
                    'width': 3,
                    'line-color': '#93c5fd',
                    'target-arrow-color': '#3b82f6',
                    'target-arrow-shape': 'triangle',
                    'curve-style': 'bezier',
                    'arrow-scale': 1.5
                }
            },
            {
                selector: 'edge[is_aggregate = true]',
                style: {
                    'line-style': 'dashed',
                    'line-dash-pattern': [8, 4],
                    'width': 4,
                    'line-color': '#ec4899'
                }
            },
            {
                selector: 'node:selected',
                style: {
                    'border-width': 4,
                    'border-color': '#fbbf24'
                }
            }
        ],
        
        layout: {
            name: 'dagre',
            rankDir: 'LR',
            nodeSep: 80,
            rankSep: 150,
            padding: 30
        }
    });
    
    cy.on('tap', 'node', function(evt) {
        const node = evt.target;
        showFieldNodeDetails(node.data());
    });
}

function showFieldNodeDetails(nodeData) {
    const detailPanel = document.getElementById('detail-panel');
    
    let badge = '';
    if (nodeData.is_aggregate && nodeData.aggregate_function) {
        badge = `<span class="text-xs bg-pink-100 text-pink-700 px-2 py-1 rounded">${nodeData.aggregate_function}</span>`;
    } else if (nodeData.is_group_by) {
        badge = `<span class="text-xs bg-purple-100 text-purple-700 px-2 py-1 rounded">GROUP BY</span>`;
    }
    
    let html = `
        <div class="border-b pb-3 mb-3">
            <h4 class="font-semibold text-lg">${nodeData.table}.${nodeData.column}</h4>
            ${badge ? `<div class="mt-1">${badge}</div>` : ''}
        </div>
        
        <div class="space-y-2 text-sm">
            <div>
                <span class="font-semibold">Level:</span>
                <span class="text-gray-700">${nodeData.level}</span>
            </div>
    `;
    
    if (nodeData.transformation) {
        html += `
            <div>
                <span class="font-semibold">Transformation:</span>
                <pre class="mt-1 p-2 bg-gray-50 rounded text-xs overflow-x-auto">${nodeData.transformation}</pre>
            </div>
        `;
    }
    
    html += `
        </div>
        
        <div class="mt-4 pt-3 border-t">
            <button 
                onclick="backToTableView()" 
                class="text-blue-600 hover:underline text-sm"
            >
                ← Back to Table View
            </button>
        </div>
    `;
    
    detailPanel.innerHTML = html;
}

// ==================== View Controls ====================
document.getElementById('btn-table-view').addEventListener('click', () => {
    if (currentView !== 'table') {
        backToTableView();
    }
});

document.getElementById('btn-field-view').addEventListener('click', () => {
    if (currentFieldInfo) {
        showFieldLineageView(currentFieldInfo.table, currentFieldInfo.column);
    }
});

document.getElementById('btn-back-to-table').addEventListener('click', () => {
    backToTableView();
});

// ==================== Helper Functions ====================
function showLoading() {
    document.getElementById('loading').classList.remove('hidden');
}

function hideLoading() {
    document.getElementById('loading').classList.add('hidden');
}

function showError(message) {
    const errorDiv = document.getElementById('error');
    errorDiv.textContent = message;
    errorDiv.classList.remove('hidden');
}

function hideError() {
    document.getElementById('error').classList.add('hidden');
}

function hideResults() {
    document.getElementById('results').classList.add('hidden');
}

// ==================== Help Modal ====================
document.getElementById('btn-help').addEventListener('click', () => {
    document.getElementById('help-modal').classList.remove('hidden');
});

document.getElementById('btn-close-help').addEventListener('click', () => {
    document.getElementById('help-modal').classList.add('hidden');
});

// Click outside modal to close
document.getElementById('help-modal').addEventListener('click', (e) => {
    if (e.target.id === 'help-modal') {
        document.getElementById('help-modal').classList.add('hidden');
    }
});

// ESC key to close help
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const modal = document.getElementById('help-modal');
        if (!modal.classList.contains('hidden')) {
            modal.classList.add('hidden');
        }
    }
});
