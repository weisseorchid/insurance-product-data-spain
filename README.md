# Insurance Product Data - Spain

A pycountry-style Python library providing Spanish insurance market data. Access insurance companies, distributors, branches, and product information with simple, intuitive APIs.

## Installation

```bash
pip install insurance-product-data-sp
```

## Quick Start

```python
from insurance_product_data_sp import companies, distributors, branches, products

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

# Work with branches (insurance lines)
life_branches = branches.list_life()
non_life_branches = branches.list_non_life()
branch = branches.get_by_code("09")  # Home insurance branch

# Work with products
company_products = products.search_by_company("C0737")
print(f"Found {len(company_products)} products for company C0737")

product = products.get(product_id="urn:C0737-01")
if product and product.analysis:
    print(f"Product: {product.product_name}")
    print(f"Type: {product.analysis.product_summary.product_type}")
```

## API Reference

### Data Stores

The library provides four main data stores:

| Store | Description | Primary Key |
|-------|-------------|-------------|
| `companies` | Insurance companies (aseguradoras) | `company_key` |
| `distributors` | Insurance distributors (mediadores) | `distributor_key` |
| `branches` | Insurance branches/lines (ramos) | `code` |
| `products` | Insurance products with AI analysis | `product_id` |

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

### Products Store (additional methods)

```python
# Search products by company
products.search_by_company("C0737")

# Search products by type
products.search_by_type("Seguro de Hogar")

# Search products by branch code
products.search_by_branch("09")  # All home insurance products
```

### Branches Store (additional methods)

```python
# Get branch by code (supports both "01" and "1" formats)
branch = branches.get_by_code("09")

# List by category
life_branches = branches.list_life()
non_life_branches = branches.list_non_life()
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

### InsuranceProduct

Key fields:
- `product_id`: Unique identifier (e.g., "urn:C0737-01")
- `product_name`: Product name
- `product_branch`: Insurance branch code(s)
- `analysis`: AI-extracted structured analysis (coverages, exclusions, terms, etc.)

## For Users

This package ships with a pre-built SQLite database containing all data. Simply install and import - no setup required:

```python
from insurance_product_data_sp import companies, distributors, branches, products
```

The data is read-only and bundled with the package. You do not need to run any scripts or update any databases.

## Project Structure

```
insurance-product-data-spain/
├── insurance_product_data_sp/       # Package (pip installable)
│   ├── __init__.py                  # Public API
│   ├── core/                        # Data stores and utilities
│   ├── models/                      # SQLModel table definitions
│   ├── schemas/                     # Pydantic models
│   └── data/                        # Bundled SQLite database
│
├── scripts/                         # Admin scripts (not for users)
│   ├── sync_data.py                 # Sync regulatory data
│   ├── build_db.py                  # Build SQLite database
│   ├── analyze_products.py          # AI-powered product analysis
│   ├── process_pdfs.py              # PDF processing
│   └── fetchers/                    # Web scrapers
│
└── data/                            # Development data (not installed)
    ├── insurance_companies.json     # Source: insurance companies
    ├── insurance_distributors.json  # Source: insurance distributors
    ├── insurance_branches.json      # Source: insurance branches
    └── products_by_insurance_company/  
        └── {company_name}/
            ├── index.json           # Product index
            ├── analysis/            # AI-analyzed products
            ├── metadata/            # Processing metadata
            └── sources/             # Product documentation (PDFs, markdown)
```

## For Maintainers

### Data Sources

The library provides two types of data:

1. **Regulatory Data** (companies, distributors, branches): Fetched from the Spanish regulator (DGSFP/Mineco)
2. **Product Documents**: Stored in `data/products_by_insurance_company/` with AI-powered analysis

### Updating Data

To refresh the bundled data:

```bash
# Install sync dependencies
pip install insurance-product-data-sp[sync]

# Run sync script (fetches data and rebuilds the database)
uv run python -m scripts.sync_data
```

This will:
1. Fetch companies and distributors from the regulator website
2. Save JSON files to `data/` and `insurance_product_data_sp/data/`
3. Rebuild the SQLite database at `insurance_product_data_sp/data/insurance.db`

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
