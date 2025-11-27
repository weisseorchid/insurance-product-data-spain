# Insurance Product Data - Spain

A reliable and public source of information for the insurance policy market in Spain. This project provides automated collection and manual curation of data from different data sources in a structured manner.

## Overview

This repository contains:
- **Python package** (`insurance_data_spain`) for fetching insurance data from the Spanish regulator website
- **Collected data** in JSON format and organized folder structure
- **API modules** to retrieve insurance companies, distributors, and their details

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
from insurance_data_spain import get_insurance_companies

# Get all active insurance companies
companies = get_insurance_companies()

# Search with custom parameters
companies = get_insurance_companies(search_params={
    "Descripcion": "Allianz",
    "Situacion": "1"  # active
})
```

### Fetch Insurance Distributors

```python
from insurance_data_spain.api.v1.get_insurance_distributors import get_insurance_distributors

# Get all active distributors
distributors = get_insurance_distributors()
```

### Sync Company Folders

```python
from insurance_data_spain import sync_insurance_company_folders

# Create folder structure from JSON data
sync_insurance_company_folders()
```

## Project Structure

```
insurance-product-data-SP/
├── src/
│   └── insurance_data_spain/
│       ├── api/
│       │   └── v1/
│       │       ├── get_insurance_companies.py
│       │       ├── get_insurance_distributors.py
│       │       └── sync_insurco_data_folders.py
│       ├── constants/
│       │   ├── api_headers.py
│       │   └── public_urls.py
│       └── utils/
│           ├── data_extraction.py
│           └── text_transformations.py
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
uv run mypy src/
```

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## Links

- **Homepage**: https://github.com/weisseorchid/insurance-product-data-SP
- **Documentation**: https://insurance-product-data-sp.readthedocs.io
- **Issues**: https://github.com/weisseorchid/insurance-product-data-SP/issues
