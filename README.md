# Insurance Product Data - Spain

A reliable and public source of information for the insurance policy market in Spain. This project provides automated collection and manual curation of data from different data sources in a structured manner.

## Overview

This repository contains:
- **Python package** (`insurance_product_data_spain`) for fetching insurance data from the Spanish regulator website
- **Collected data** in JSON format and organized folder structure
- **Service modules** to retrieve insurance companies, distributors, and their details

## Installation

### Requirements

- Python 3.10 or higher
- `uv` package manager or compatible with pyproject.toml files.

### Setup

1. Clone the repository:
```bash
git clone https://github.com/weisseorchid/insurance-product-data-SP.git
cd insurance-product-data-SP
```

2. Install the package in development mode:
```bash
uv sync
```

3. Install development dependencies (optional):
```bash
uv sync --extra dev
```

## Usage

### Fetch Insurance Companies

```python
from insurance_product_data_spain import get_insurance_companies, enrich_insurance_companies

# Get all active insurance companies
companies = get_insurance_companies()

# Search with custom parameters
companies = get_insurance_companies(search_params={
    "Descripcion": "Allianz",
    "Situacion": "1"  # active
})

# Enrich companies with detailed information
enriched = enrich_insurance_companies(companies)
```

### Fetch Insurance Distributors

```python
from insurance_product_data_spain import get_insurance_distributors, enrich_insurance_distributors

# Get all active distributors
distributors = get_insurance_distributors()

# Enrich distributors with detailed information
enriched = enrich_insurance_distributors(distributors)
```

### Sync Company Folders

```python
from insurance_product_data_spain import sync_insurance_company_folders

# Create folder structure from JSON data
sync_insurance_company_folders()
```

## Project Structure

```
insurance-product-data-SP/
├── insurance_product_data_spain/
│   ├── core/
│   │   ├── config.py          # Configuration (paths, settings)
│   │   ├── logging.py         # Logging setup
│   │   └── storage.py         # Data storage abstraction
│   ├── services/
│   │   └── v1/
│   │       ├── insurance_companies/
│   │       │   ├── get_insurance_companies.py
│   │       │   └── sync_insurco_data_folders.py
│   │       └── insurance_distributors/
│   │           └── get_insurance_distributors.py
│   ├── models/                # Pydantic data models
│   ├── constants/             # API headers, URLs, storage routes
│   └── utils/                 # Data extraction and text utilities
├── data/
│   ├── insurance_companies.json
│   └── insurance_companies/
│       └── [company folders]/
└── pyproject.toml
```

## Data

The `data/` directory contains:
- `insurance_companies.json`: Complete dataset of insurance companies with detailed information
- `insurance_companies/`: Individual folders for each insurance company (snake_case naming)

## Contributing

We welcome contributions! Please follow these guidelines:

### Before Contributing

1. **Fork the repository** and create a branch for your feature
2. **Install pre-commit hooks** to ensure code quality:
```bash
uv run pre-commit install
```

### Code Quality Standards

- All code must pass **ruff** linting checks
- All code must pass **mypy** type checking
- Follow existing code style and patterns
- Add type hints to all functions
- Write clear docstrings for public functions

### Pre-commit Hooks

The repository includes pre-commit hooks that automatically run:
- `ruff` for linting and code formatting
- `mypy` for type checking

These checks run automatically before commits. If they fail, fix the issues before pushing.

### Pull Request Process

1. Ensure all pre-commit checks pass
2. Test your changes thoroughly
3. Update documentation if needed
4. Submit a pull request with a clear description
5. Ensure your PR passes all CI checks

### Running Checks Manually

You can run the checks manually before committing:

```bash
# Run ruff
uv run ruff check .

# Run mypy
uv run mypy insurance_product_data_spain/
```

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## Links

- **Homepage**: https://github.com/weisseorchid/insurance-product-data-SP
- **Issues**: https://github.com/weisseorchid/insurance-product-data-SP/issues
