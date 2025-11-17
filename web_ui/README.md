# Lineage Glass Web UI

Simple web interface for SQL lineage analysis.

## Quick Start

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Run the server:

```bash
python app.py
```

3. Open browser:

```
http://localhost:5000
```

## Features

- 📝 Input SQL via text or file upload
- 🔗 Interactive lineage graph visualization
- 🔍 Search tables and columns
- 💾 Export results to JSON
- 📊 Detailed column lineage view

## Usage

1. Paste your SQL script or upload a .sql file
2. Click "Analyze"
3. Explore the lineage graph
4. Click tables/nodes to view details
5. Export results if needed

## Technology Stack

- Backend: Flask
- Frontend: HTML/CSS/JavaScript
- Visualization: Cytoscape.js
- Styling: Tailwind CSS

## Project Structure

```
web_ui/
├── app.py              # Flask application
├── requirements.txt    # Python dependencies
├── templates/
│   └── index.html     # Main page template
├── static/
│   ├── css/
│   │   └── style.css  # Custom styles
│   └── js/
│       └── app.js     # Frontend logic
└── README.md          # This file
```

## API Endpoints

### POST /api/analyze

Analyzes SQL script and returns lineage data.

**Request:**
- Form data with `sql` field containing SQL text
- Or file upload with SQL file

**Response:**
```json
{
  "tables": [...],
  "graph": {
    "nodes": [...],
    "edges": [...]
  }
}
```

## Development

To run in development mode:

```bash
export FLASK_ENV=development
python app.py
```

## License

Same as lineage-glass project.

