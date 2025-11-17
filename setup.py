"""
Setup script for lineage-analyzer package.
"""

from setuptools import find_packages, setup

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="lineage-analyzer",
    version="1.0.0",
    author="Lineage Analyzer Contributors",
    description="SQL Field-Level Lineage Analyzer",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/your-org/lineage-analyzer",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Database",
    ],
    python_requires=">=3.10",
    install_requires=[
        "sqlglot>=20.0.0",
        "networkx>=3.0",
        "tabulate>=0.9.0",
        "colorama>=0.4.6",  # Colored output
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-cov",
            "mypy",
            "black",
            "ruff",
        ],
    },
    entry_points={
        "console_scripts": [
            "lineage-analyzer=lineage_analyzer.cli:main",
        ],
    },
)

