# Insurance Product Data - Spain

A pycountry-style Python library providing Spanish insurance market data. Access insurance companies, distributors, and product information with simple, intuitive APIs.

## Installation

```bash
pip install insurance-product-data-sp
```

## Quick Start

```python
from insurance_product_data_spain import companies, distributors

# Get a company by key
company = companies.get(company_key="C0001")
print(company.denomination)  # ASEGURADORES AGRUPADOS, SOCIEDAD ANONIMA DE SEGUROS

# Get a company by NIF
company = companies.get(nif="A28007748")

# Search companies
active = companies.search(status="Activa")
print(f"Found {len(active)} active companies")

# Iterate over all companies
for company in companies:
    print(f"{company.company_key}: {company.denomination}")

# Work with distributors
for distributor in distributors:
    print(f"{distributor.distributor_key}: {distributor.name}")
    
    # Access agency contracts
    for contract in distributor.agency_contracts:
        insurer = companies.get(company_key=contract.company_key)
        print(f"  Contract with: {insurer.denomination if insurer else 'Unknown'}")
```

## API Reference

### Data Stores

The library provides three main data stores:

| Store | Description | Primary Key |
|-------|-------------|-------------|
| `companies` | Insurance companies (aseguradoras) | `company_key` |
| `distributors` | Insurance distributors (mediadores) | `distributor_key` |
| `branches` | Insurance branches/lines (ramos) | `ramo` |

### Methods

All data stores support these methods:

```python
# Get by indexed field (returns None if not found)
company = companies.get(company_key="C0001")
company = companies.get(nif="A28007748")

# Lookup by indexed field (raises KeyError if not found)
company = companies.lookup(company_key="C0001")

# Search by any field (returns list)
results = companies.search(status="Activa")
results = companies.search(province="Madrid")

# Iteration and length
for company in companies:
    ...
print(len(companies))

# Membership test
"C0001" in companies  # True
```

### Synthetic Entity Resolution

For graph resilience, `companies` supports resolving unknown keys to synthetic entities:

```python
# Never returns None - creates synthetic entity for unknown keys
company = companies.resolve("UNKNOWN_KEY")
print(company.is_synthetic)  # True
print(company.denomination)  # "Entity UNKNOWN_KEY (Unmapped)"
```

## Data Models

### InsuranceCompanyDetails

Key fields:
- `company_key`: Unique identifier (e.g., "C0001")
- `denomination`: Company name
- `nif`: Tax identification number
- `status`: Company status (e.g., "Activa")
- `insurance_branches`: List of authorized products/lines
- `executives`, `shareholders`, `agencies`: Related entities

### InsuranceDistributorDetails

Key fields:
- `distributor_key`: Unique identifier
- `name`: Distributor name
- `mediator_class`: Type of mediator
- `agency_contracts`: List of contracts with insurers

## Project Structure

```
insurance-product-data-spain/
├── insurance_product_data_spain/    # Package (pip installable)
│   ├── __init__.py                  # Public API
│   ├── core/                        # Data stores and utilities
│   ├── schemas/                     # Pydantic models
│   └── data/                        # Bundled JSON data
│
├── scripts/                         # Data processing scripts
│   ├── sync_data.py                 # Sync regulatory data
│   ├── analyze_products.py          # AI-powered product analysis
│   ├── process_pdfs.py              # PDF processing
│   └── fetchers/                    # Web scrapers
│
└── data/                            # Data files
    ├── insurance_companies.json
    ├── insurance_distributors.json
    └── products_by_insurance_company/  # Product documents and analysis
```

## Data Sources

The library provides two types of data:

1. **Regulatory Data** (companies, distributors, branches): Fetched from the Spanish regulator (DGSFP/Mineco) via `scripts/sync_data.py`
2. **Product Documents**: Stored in `data/products_by_insurance_company/` with AI-powered analysis via `scripts/analyze_products.py`

### Updating Regulatory Data

```bash
# Install sync dependencies
pip install insurance-product-data-sp[sync]

# Run sync script
uv run python -m scripts.sync_data
```

## Development

```bash
# Clone and install
git clone https://github.com/weisseorchid/insurance-product-data-SP.git
cd insurance-product-data-SP
uv sync --extra dev

# Run tests
uv run pytest

# Run linting and formatting
uv run ruff check .
uv run ruff format .

# Run type checker
uv run ty check
```

## License

Apache License 2.0 - see [LICENSE](LICENSE) for details.

## Links

- **Repository**: https://github.com/weisseorchid/insurance-product-data-SP
- **Issues**: https://github.com/weisseorchid/insurance-product-data-SP/issues
