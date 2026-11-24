# Product Schema v1

This document describes the product data schema version 1 used in the `insurance-product-data-spain` package.

## Overview

The product schema defines how insurance products are stored and represented in the database and data files. Version 1 introduces:

- **Consistent product identifiers** (URN format)
- **Company references** (linking to DGSFP company keys)
- **Many-to-many branch associations** (products can belong to multiple insurance branches)
- **Document references** (linking to source documents in `documents.jsonl`)
- **Analysis metadata** (optional path to AI-extracted analysis JSON)
- **Provenance fields** (timestamps and source URLs)

## Schema Fields

### Core Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `product_id` | `str` | Yes | Unique product identifier in URN format (e.g., `urn:C0737-01`) |
| `company_key` | `str` | Yes | DGSFP company key (e.g., `C0737`) |
| `product_name` | `str` | Yes | Product name in snake_case (e.g., `seguro_hogar`) |
| `branches` | `list[str]` | Yes | List of insurance branch codes (e.g., `["00", "09"]`) |

### Reference Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `document_references` | `list[DocumentReference]` | No | References to documents in `documents.jsonl` |
| `analysis_path` | `str \| None` | No | Relative path to analysis JSON file (e.g., `analysis/product.json`) |
| `source_url` | `str \| None` | No | Primary source URL for the product |

### Provenance Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `fetched_at` | `str \| None` | No | ISO8601 timestamp when product was fetched |
| `metadata` | `dict[str, Any]` | No | Additional metadata |

### DocumentReference Schema

Each document reference contains:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `filename` | `str` | Yes | Document filename |
| `pdf_sha256` | `str` | Yes | SHA256 hash of the PDF document |
| `markdown_sha256` | `str \| None` | No | SHA256 hash of the markdown conversion |
| `doc_type` | `str \| None` | No | Document type (e.g., `ipid`, `general_conditions`) |

## Database Schema

### ProductTable

Stores core product metadata with indexed fields for efficient lookups:

```sql
CREATE TABLE products (
    product_id TEXT PRIMARY KEY,
    product_name TEXT NOT NULL,
    company_key TEXT NOT NULL,
    fetched_at TEXT,
    details_json JSON NOT NULL,
    FOREIGN KEY (company_key) REFERENCES companies(company_key)
);

CREATE INDEX ix_products_product_name ON products(product_name);
CREATE INDEX ix_products_company_key ON products(company_key);
CREATE INDEX ix_products_fetched_at ON products(fetched_at);
```

### ProductBranchAssociation

Many-to-many association table linking products to insurance branches:

```sql
CREATE TABLE product_branch_associations (
    product_id TEXT NOT NULL,
    branch_code TEXT NOT NULL,
    PRIMARY KEY (product_id, branch_code),
    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (branch_code) REFERENCES branches(code)
);
```

## Data File Format

Products are stored in `data/products_by_insurance_company/<company>/index.json`:

```json
[
    {
        "fetched_at": "2026-01-27T00:00:00Z",
        "version": "1.0",
        "company_key": "C0737",
        "status": "Active",
        "products": [
            {
                "product_id": "urn:C0737-01",
                "company_key": "C0737",
                "product_name": "seguro_hogar",
                "branches": ["09"],
                "source_url": "https://www.nnespana.es/seguro-hogar",
                "document_references": [
                    {
                        "filename": "CG-seguro-hogar.pdf",
                        "pdf_sha256": "2472561d7b280c14b9c343ed8edeb1bf77930d74a71c2d921ef277b10e37426e",
                        "markdown_sha256": "58c44471b3c21b8d72d2c0fe24ea6fa2c82e0e5f6ededfdc1664c0f14bb224c7",
                        "doc_type": "general_conditions"
                    }
                ],
                "analysis_path": "analysis/seguro_hogar.json",
                "fetched_at": "2026-01-27T00:00:00Z",
                "metadata": {}
            }
        ]
    }
]
```

## Querying Products

### Python API

```python
from insurance_product_data_sp import products

# Get product by ID
product = products.get(product_id="urn:C0737-01")

# Search by company
company_products = products.search_by_company("C0737")

# Search by branch (uses association table)
home_products = products.search_by_branch("09")

# Iterate all products
for product in products:
    print(f"{product.product_id}: {product.product_name}")
```

### SQL Queries

```sql
-- Get all products for a company
SELECT * FROM products WHERE company_key = 'C0737';

-- Get all products in a specific branch
SELECT p.*
FROM products p
JOIN product_branch_associations pba ON p.product_id = pba.product_id
WHERE pba.branch_code = '09';

-- Get multi-branch products
SELECT p.product_id, COUNT(pba.branch_code) as branch_count
FROM products p
JOIN product_branch_associations pba ON p.product_id = pba.product_id
GROUP BY p.product_id
HAVING COUNT(pba.branch_code) > 1;
```

## Migration from Legacy Format

Products in the old format (with `product_branch` string field and `prduct_id` typo) can be migrated using:

```bash
python scripts/migrate_product_schema_v1.py
```

This script:
1. Fixes the `prduct_id` → `product_id` typo
2. Converts `product_branch` to `branches` list
3. Adds `company_key`, `fetched_at`, and other schema v1 fields
4. Links documents from `documents.jsonl`
5. Removes deprecated fields (`source_folder`, `files`)

## Validation

Product data is validated in CI using `scripts/ci/check_data_integrity.py`, which checks:

- Required fields are present
- `branches` is a non-empty list
- `document_references` structure is valid
- No deprecated fields remain (`product_branch`, `source_folder`, `files`)
- Branch codes (in `index.json` and analysis files) exist in `data/insurance_branches.jsonl`
- Analysis files use `branches` (not `product_branch`) and carry `metadata.quality_flags`
- `documents.jsonl` entries are not known block pages (by `markdown_sha256`)

Pre-existing violations are tracked in `data/quality/known_data_issues.jsonl` so that only new
violations fail CI; see [GENERATING_PRODUCT_POOL.md](GENERATING_PRODUCT_POOL.md#known-issues-baseline).

## Related Documentation

- [GENERATING_PRODUCT_POOL.md](GENERATING_PRODUCT_POOL.md) - How to generate product data
- [README.md](../README.md) - Package usage
- [Database Schema](../insurance_product_data_sp/models/) - SQLModel definitions
