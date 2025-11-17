// Global variables
let currentData = null;
let cy = null;

// Tab switching
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

// File input handling
const fileInput = document.getElementById('file-input');
const fileName = document.getElementById('file-name');

fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        fileName.textContent = `Selected: ${e.target.files[0].name}`;
    }
});

// Load example SQL
document.getElementById('load-example').addEventListener('click', () => {
    const exampleSQL = `-- Example: Sales Analysis with CTE and Aggregates
WITH monthly_sales AS (
    SELECT 
        dept_id,
        AVG(salary) as avg_salary,
        COUNT(*) as emp_count
    FROM employees
    GROUP BY dept_id
)
SELECT 
    d.name as dept_name,
    ms.avg_salary,
    ms.emp_count
FROM departments d
JOIN monthly_sales ms ON d.id = ms.dept_id
WHERE ms.avg_salary > 50000;`;
    
    document.getElementById('sql-input').value = exampleSQL;
    switchTab('text');
});

// Clear button
document.getElementById('clear-btn').addEventListener('click', () => {
    document.getElementById('sql-input').value = '';
    fileInput.value = '';
    fileName.textContent = '';
    hideResults();
    hideError();
});

// Analyze button
document.getElementById('analyze-btn').addEventListener('click', async () => {
    await analyzeSQL();
});

// Export button
document.getElementById('export-btn').addEventListener('click', () => {
    if (!currentData) return;
    
    const dataStr = JSON.stringify(currentData, null, 2);
    const blob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    
    const a = document.createElement('a');
    a.href = url;
    a.download = 'lineage_analysis.json';
    a.click();
    
    URL.revokeObjectURL(url);
});

// Main analysis function
async function analyzeSQL() {
    // Get SQL text
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
    
    // Show loading
    showLoading();
    hideError();
    hideResults();
    
    try {
        // Call API
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
        
        // Display results
        displayResults(data);
        
    } catch (error) {
        showError(`Error: ${error.message}`);
    } finally {
        hideLoading();
    }
}

// Display results
function displayResults(data) {
    // Show results section
    document.getElementById('results').classList.remove('hidden');
    
    // Render table list
    renderTableList(data.tables);
    
    // Render graph
    renderGraph(data.graph);
    
    // Show export button
    document.getElementById('export-btn').classList.remove('hidden');
}

// Render table list
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
            // Remove previous selection
            document.querySelectorAll('.table-item').forEach(item => {
                item.classList.remove('selected');
            });
            tableDiv.classList.add('selected');
            
            showTableDetails(table);
            highlightTableInGraph(table.name);
        });
        
        tableList.appendChild(tableDiv);
    });
}

// Get table icon based on type
function getTableIcon(type) {
    const icons = {
        'table': '📦',
        'view': '👁️',
        'cte': '🔄',
        'subquery': '📊',
        'external': '🌐',
        'temp_table': '📋'
    };
    return icons[type] || '📋';
}

// Render graph with Cytoscape.js
function renderGraph(graphData) {
    // Initialize Cytoscape
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
                    'color': '#333',
                    'shape': 'round-rectangle'
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
            },
            {
                selector: 'node.highlighted',
                style: {
                    'border-width': 4,
                    'border-color': '#fbbf24',
                    'background-color': '#fef3c7'
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
    
    // Node click event
    cy.on('tap', 'node', function(evt) {
        const nodeId = evt.target.id();
        const table = currentData.tables.find(t => t.name === nodeId);
        if (table) {
            // Update table list selection
            document.querySelectorAll('.table-item').forEach(item => {
                item.classList.remove('selected');
            });
            const tableItems = document.querySelectorAll('.table-item');
            const tableIndex = currentData.tables.findIndex(t => t.name === nodeId);
            if (tableItems[tableIndex]) {
                tableItems[tableIndex].classList.add('selected');
            }
            
            showTableDetails(table);
        }
    });
}

// Get node color based on type
function getNodeColor(type) {
    const colors = {
        'table': '#60a5fa',      // Blue
        'view': '#34d399',       // Green
        'cte': '#fbbf24',        // Yellow
        'subquery': '#a78bfa',   // Purple
        'external': '#d1d5db',   // Gray
        'temp_table': '#fb923c'  // Orange
    };
    return colors[type] || '#9ca3af';
}

// Highlight table in graph
function highlightTableInGraph(tableName) {
    if (!cy) return;
    
    // Reset all
    cy.nodes().removeClass('selected');
    
    // Highlight selected
    const node = cy.getElementById(tableName);
    if (node.length > 0) {
        node.addClass('selected');
        // Center on node
        cy.center(node);
    }
}

// Show table details
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
        let badges = '';
        if (col.is_aggregate) {
            badges += `<span class="text-xs bg-purple-100 text-purple-700 px-2 py-1 rounded mr-1">${col.aggregate_function}</span>`;
        }
        if (col.is_group_by) {
            badges += `<span class="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded">GROUP BY</span>`;
        }
        
        html += `
            <div class="border rounded p-2 text-sm">
                <div class="font-mono font-semibold">${col.name} ${badges}</div>
        `;
        
        if (col.sources && col.sources.length > 0) {
            html += '<div class="mt-1 text-gray-600 text-xs">Sources:</div>';
            col.sources.forEach(src => {
                html += `<div class="ml-2 text-xs text-gray-700">← ${src.table}.${src.column}</div>`;
            });
        } else {
            html += '<div class="mt-1 text-xs text-gray-400">No sources (e.g., COUNT(*))</div>';
        }
        
        if (col.expression) {
            html += `<div class="mt-1 text-xs text-gray-500 font-mono">${col.expression}</div>`;
        }
        
        html += '</div>';
    });
    
    html += '</div>';
    
    detailPanel.innerHTML = html;
}

// Search functionality
document.getElementById('search-box').addEventListener('input', (e) => {
    const query = e.target.value.toLowerCase();
    
    if (!currentData || !query) {
        // Reset highlight
        if (cy) {
            cy.nodes().removeClass('highlighted');
        }
        return;
    }
    
    // Search in tables and columns
    const matches = [];
    currentData.tables.forEach(table => {
        if (table.name.toLowerCase().includes(query)) {
            matches.push(table.name);
        }
        table.columns.forEach(col => {
            if (col.name.toLowerCase().includes(query)) {
                matches.push(table.name);
            }
        });
    });
    
    // Highlight matches in graph
    if (cy) {
        cy.nodes().removeClass('highlighted');
        matches.forEach(tableName => {
            const node = cy.getElementById(tableName);
            if (node.length > 0) {
                node.addClass('highlighted');
            }
        });
    }
});

// Helper functions
function showLoading() {
    document.getElementById('loading').classList.remove('hidden');
}

function hideLoading() {
    document.getElementById('loading').classList.add('hidden');
}

function showError(message) {
    const errorDiv = document.getElementById('error');
    
    // Parse common errors
    let friendlyMessage = message;
    if (message.includes('syntax')) {
        friendlyMessage = '❌ SQL Syntax Error: Please check your SQL syntax';
    } else if (message.includes('table')) {
        friendlyMessage = '❌ Table Error: ' + message;
    }
    
    errorDiv.innerHTML = `
        <strong>Error</strong>
        <p class="mt-1">${friendlyMessage}</p>
    `;
    errorDiv.classList.remove('hidden');
}

function hideError() {
    document.getElementById('error').classList.add('hidden');
}

function hideResults() {
    document.getElementById('results').classList.add('hidden');
    document.getElementById('export-btn').classList.add('hidden');
}

