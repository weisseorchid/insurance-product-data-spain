# Quick Start: Products by Insurer Structure

## Overview

This guide helps you set up the new `products_by_insurer` folder structure for better data management and querying.

**Note**: This structure works alongside the existing `insurance_companies/` folder:
- `insurance_companies/` : Keep for raw data gathering and processing files
- `products_by_insurer/` : New structured layer for queryable products

---

## Quick Setup

### 1. Run the Setup Script

```bash
# From project root
uv run python -m insurance_product_data_spain.services.v1.insurance_companies.setup_products_structure
```

This will create the structure for example companies: **C0001** (ASEGRUP), **C0058** (MAPFRE), **C0031** (CAJA DE SEGUROS REUNIDOS).

### 2. Or Setup Custom Companies

```python
from insurance_product_data_spain.services.v1.insurance_companies.setup_products_structure import (
    setup_example_companies,
)

# Setup for specific companies
folders = setup_example_companies(["C0001", "C0058"])
```

---

## Structure Created

For each company, you'll get:

```
data/products_by_insurer/
├── index.json                                    # Master index
└── C0001_aseguradores_agrupados_.../
    ├── raw/
    │   ├── company_details.json                 # Full company data
    │   └── metadata.json                        # Fetch metadata
    ├── processed/
    │   ├── products.json                        # Extracted insurance_branches
    │   └── company_info.json                    # Company metadata
    └── structured/
        ├── products.json                        # Normalized products
        └── index.json                           # Company index
```

---

## Querying Examples

### Get all products for a company

```python
from pathlib import Path
from insurance_product_data_spain.core.storage import load_json

company_key = "C0001"
base = Path("data/products_by_insurer")

# Find company folder (you can also use the master index)
# For now, assume folder name pattern: {key}_...
folder = next(base.glob(f"{company_key.lower()}_*"))

# Load structured products
products = load_json(folder / "structured" / "products.json")
print(f"Company {company_key} has {len(products)} products")
```

### Get all companies that sell a specific product

```python
from pathlib import Path
from insurance_product_data_spain.core.storage import load_json

base = Path("data/products_by_insurer")
ramo_code = "13"  # Responsabilidad civil general

companies_with_product = []

for company_folder in base.glob("c*_*"):
    products_path = company_folder / "structured" / "products.json"
    if not products_path.exists():
        continue
    
    products = load_json(products_path)
    matching = [p for p in products if p.get("ramo_code") == ramo_code]
    
    if matching:
        company_index = load_json(company_folder / "structured" / "index.json")
        companies_with_product.append({
            "company_key": company_index["company_key"],
            "company_name": company_index["company_name"],
            "products": matching,
        })

print(f"Found {len(companies_with_product)} companies selling ramo {ramo_code}")
```

### Use master index

```python
from pathlib import Path
from insurance_product_data_spain.core.storage import load_json

index = load_json(Path("data/products_by_insurer/index.json"))

print(f"Total companies: {index['total_companies']}")
print(f"Last updated: {index['last_updated']}")

# Find active companies with most products
active = [
    c for c in index["companies"]
    if c.get("status") == "Activa"
]
active.sort(key=lambda x: x.get("product_count", 0), reverse=True)

print(f"\nTop 5 companies by product count:")
for company in active[:5]:
    print(f"  {company['company_key']}: {company['company_name']} ({company['product_count']} products)")
```

---

## File Contents Reference

### `raw/company_details.json`
Complete `InsuranceCompanyDetails` object from API (all fields).

### `raw/metadata.json`
```json
{
  "fetched_at": "2026-01-26T00:00:00Z",
  "source_url": "https://rrpp.dgsfp.mineco.es/Aseguradora/GetAseguradora/?clave=C0001",
  "version": "1.0",
  "company_key": "C0001"
}
```

### `processed/products.json`
Array of `insurance_branches` (products) as extracted from company details.

### `processed/company_info.json`
Essential company metadata (key, name, status, website, etc.).

### `structured/products.json`
Normalized products with company context:
```json
[
  {
    "company_key": "C0001",
    "company_name": "ASEGURADORES AGRUPADOS...",
    "product_code": "01",
    "ramo_code": "1",
    "ramo_name": "Accidentes",
    "modalidad": "(Ramo Completo)",
    "status": "Activo",
    "authorized_since": "2008-07-15T00:00:00",
    "normalized_ramo": "accidentes",
    "product_type": "no_vida"
  }
]
```

### `structured/index.json`
Company-level index:
```json
{
  "company_key": "C0001",
  "company_name": "ASEGURADORES AGRUPADOS...",
  "product_count": 7,
  "active_products": 7,
  "product_codes": ["01", "12", "13", "17", "18", "06", "07"],
  "ramos": ["1/Accidentes", "12/Responsabilidad civil vehículos marítimos...", ...],
  "last_updated": "2026-01-26T00:00:00Z"
}
```

### `index.json` (master)
Master index of all companies:
```json
{
  "total_companies": 3,
  "last_updated": "2026-01-26T00:00:00Z",
  "companies": [
    {
      "company_key": "C0001",
      "company_name": "ASEGURADORES AGRUPADOS...",
      "folder_name": "c0001_aseguradores_agrupados_...",
      "status": "Activa",
      "product_count": 7,
      "last_processed": "2026-01-26T00:00:00Z"
    }
  ]
}
```

---

## Next Steps

1. **Review the structure** created for example companies
2. **Test querying** using the examples above
3. **Adjust the structure** if needed (see `DATA_STRUCTURE_PROPOSAL.md`)
4. **Process more companies** incrementally
5. **Update code** to use the new structure (see migration plan in proposal)

---

## See Also

- **Full proposal**: `docs/DATA_STRUCTURE_PROPOSAL.md`
- **Setup script**: `insurance_product_data_spain/services/v1/insurance_companies/setup_products_structure.py`
