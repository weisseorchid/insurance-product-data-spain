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
print(company.denomination)

# Get a company by NIF
company = companies.get(nif="A28007748")

# Search companies
active = companies.search(status="Activa")
print(f"Found {len(active)} active companies")

# Iterate over all companies
for company in companies:
    print(f"{company.company_key}: {company.denomination}")

# Work with branches (insurance lines)
branch = branches.get_by_code("09")  # Home insurance
life_branches = branches.list_life()
non_life_branches = branches.list_non_life()

# Work with products
company_products = products.search_by_company("C0737")
product = products.get(product_id="urn:C0737-01")
if product and product.analysis:
    print(f"Product: {product.product_name}")
```

## API Reference

### Data Stores

| Store | Description | Primary Key |
|-------|-------------|-------------|
| `companies` | Insurance companies (aseguradoras) | `company_key` |
| `distributors` | Insurance distributors (mediadores) | `distributor_key` |
| `branches` | Insurance branches/lines (ramos) | `code` |
| `products` | Insurance products with AI analysis | `product_id` |

### Common Methods

```python
# Get by indexed field (returns None if not found)
company = companies.get(company_key="C0001")

# Lookup by indexed field (raises KeyError if not found)
company = companies.lookup(company_key="C0001")

# Search by field (returns list)
results = companies.search(status="Activa")

# Iteration, length, membership
for company in companies: ...
len(companies)
"C0001" in companies  # True
```

### Store-Specific Methods

```python
# Companies - synthetic entity resolution
company = companies.resolve("UNKNOWN_KEY")  # Never returns None

# Branches
branches.get_by_code("09")  # Supports "01" and "1" formats
branches.list_life()
branches.list_non_life()

# Products
products.search_by_company("C0737")
products.search_by_branch("09")
```

## For Users

The package ships with a pre-built SQLite database. Simply install and import:

```python
from insurance_product_data_sp import companies, distributors, branches, products
```

## For Maintainers

### Updating Data

```bash
# Install sync dependencies
pip install insurance-product-data-sp[sync]

# Sync regulatory data and rebuild database
uv run python -m scripts.sync_data
```

See [docs/GENERATING_PRODUCT_POOL.md](docs/GENERATING_PRODUCT_POOL.md) for adding product documentation.

## Development

```bash
git clone https://github.com/weisseorchid/insurance-product-data-SP.git
cd insurance-product-data-SP
uv sync --extra dev

uv run pytest
uv run ruff check .
uv run ruff format .
```

## License

Apache License 2.0 - see [LICENSE](LICENSE) for details.
