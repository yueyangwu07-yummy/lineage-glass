# Release Checklist for v1.0.0

Use this checklist to ensure a complete and high-quality release.

## Code Quality

- [ ] All 262+ tests pass
  ```bash
  pytest tests/ -v
  ```

- [ ] No linter errors
  ```bash
  flake8 lineage_analyzer/ --max-line-length=100
  flake8 web_ui/ --max-line-length=100
  ```

- [ ] Type annotations complete
  ```bash
  mypy lineage_analyzer/ --ignore-missing-imports
  ```

- [ ] Code coverage >80%
  ```bash
  pytest --cov=lineage_analyzer --cov-report=html
  ```

## Documentation

- [ ] README.md updated
  - [ ] Web UI section added
  - [ ] Usage examples updated
  - [ ] Supported features list accurate
  - [ ] Installation instructions clear

- [ ] CHANGELOG.md complete
  - [ ] All major features documented
  - [ ] Breaking changes listed (if any)
  - [ ] Known limitations documented

- [ ] Web UI README complete
  - [ ] Quick start guide
  - [ ] API documentation
  - [ ] Feature list

- [ ] API documentation clear
  - [ ] Python API examples
  - [ ] CLI usage examples
  - [ ] Web UI API endpoints documented

- [ ] Screenshots added
  - [ ] Input interface screenshot
  - [ ] Lineage graph screenshot
  - [ ] Details panel screenshot
  - [ ] Screenshots referenced in README

## Functionality

- [ ] CLI works correctly
  ```bash
  lineage-analyze examples/simple/transform.sql
  lineage-analyze examples/simple/transform.sql --trace final_table.column
  ```

- [ ] Web UI works correctly
  ```bash
  cd web_ui
  python app.py
  # Test in browser:
  # - SQL input (text and file)
  # - Analysis execution
  # - Graph visualization
  # - Search functionality
  # - Export to JSON
  # - Example SQL loading
  ```

- [ ] Python API works correctly
  ```python
  from lineage_analyzer import ScriptAnalyzer
  analyzer = ScriptAnalyzer()
  result = analyzer.analyze_script(sql_text)
  assert result.registry is not None
  ```

- [ ] Example SQL runs successfully
  ```bash
  lineage-analyze examples/ecommerce/pipeline.sql
  ```

## Packaging

- [ ] setup.py/pyproject.toml complete
  - [ ] Version number correct (1.0.0)
  - [ ] Dependencies listed
  - [ ] Entry points configured

- [ ] requirements.txt accurate
  - [ ] Core dependencies listed
  - [ ] Web UI dependencies listed
  - [ ] Version pins appropriate

- [ ] LICENSE file present
  - [ ] MIT License included
  - [ ] Copyright year updated

- [ ] .gitignore complete
  - [ ] Python artifacts ignored
  - [ ] IDE files ignored
  - [ ] Build artifacts ignored

## Release Preparation

- [ ] Version number updated
  - [ ] `lineage_analyzer/version.py` updated to 1.0.0
  - [ ] README.md version updated
  - [ ] CHANGELOG.md version updated

- [ ] Git repository clean
  ```bash
  git status
  git add .
  git commit -m "Release v1.0.0: Production ready with Web UI"
  ```

- [ ] Git tag created
  ```bash
  git tag -a v1.0.0 -m "Version 1.0.0 - Production Ready

  Major features:
  - Complete CTE support (regular + recursive)
  - Comprehensive subquery support
  - Full aggregate function support
  - Interactive Web UI
  - 262+ test cases
  - 90%+ SQL coverage"
  ```

- [ ] GitHub Release prepared
  - [ ] Release notes written
  - [ ] Screenshots ready
  - [ ] Known limitations documented

## Post-Release

- [ ] Git tag pushed
  ```bash
  git push origin main
  git push origin v1.0.0
  ```

- [ ] GitHub Release created
  - [ ] Tag selected (v1.0.0)
  - [ ] Title: "v1.0.0 - Production Ready 🎉"
  - [ ] Description from CHANGELOG
  - [ ] Screenshots attached
  - [ ] Release published

## Optional Enhancements

- [ ] PyPI package published
  ```bash
  python setup.py sdist bdist_wheel
  twine upload dist/*
  ```

- [ ] Docker image built
  ```bash
  docker build -t lineage-glass:1.0.0 .
  ```

- [ ] Documentation site deployed
  - [ ] ReadTheDocs configured
  - [ ] API documentation generated

## Verification

After release, verify:

- [ ] GitHub Release page looks good
- [ ] Download links work
- [ ] Installation from PyPI works (if published)
- [ ] Documentation is accessible
- [ ] Issues/PRs are properly tagged

---

**Release Date:** TBD
**Release Manager:** TBD
**Status:** In Progress

