# Contributing to Lineage Analyzer

Thank you for your interest in contributing! 🎉

## How to Contribute

### Reporting Bugs

If you find a bug, please open an issue with:

1. A clear description of the bug
2. Steps to reproduce
3. Expected vs actual behavior
4. SQL script that triggers the bug (if applicable)
5. Your environment (Python version, OS)

### Suggesting Features

Feature requests are welcome! Please:

1. Check if it's already requested
2. Explain the use case
3. Provide examples if possible

### Code Contributions

1. **Fork the repository**

2. **Create a feature branch**

```bash
git checkout -b feature/your-feature-name
```

3. **Set up development environment**

```bash
pip install -e ".[dev]"
```

4. **Make your changes**

   - Follow PEP 8 style guide
   - Add type hints
   - Write docstrings (Google style)

5. **Add tests**

```bash
# Your feature should have tests
pytest tests/test_your_feature.py
```

6. **Run the test suite**

```bash
pytest
pytest --cov=lineage_analyzer
mypy lineage_analyzer
black lineage_analyzer
```

7. **Commit your changes**

```bash
git commit -m "Add: brief description of your feature"
```

8. **Push and create a Pull Request**

## Development Guidelines

### Code Style

- Use `black` for formatting
- Use `mypy` for type checking
- Maximum line length: 100 characters

### Testing

- Aim for > 80% test coverage
- Write both unit tests and integration tests
- Test edge cases

### Documentation

- Update README if adding user-facing features
- Add docstrings to all public functions
- Include examples in docstrings

## Project Structure

```
lineage_analyzer/
├── analyzer/       # Core analysis logic
├── parser/         # SQL parsing
├── models/         # Data models
├── registry/       # Table registry
├── resolver/       # Transitive lineage
└── cli.py          # Command-line interface
```

## Questions?

Open an issue or email: your.email@example.com

