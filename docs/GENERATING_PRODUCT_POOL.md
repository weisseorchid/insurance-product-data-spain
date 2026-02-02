# Generating the Product Pool for an Insurer

This document explains how to generate the **pool of products** for an insurance company using the project scripts.

## Overview

The **product pool** is the set of commercial insurance products for a given insurer, including:
- **Source documents**: PDFs (IPIDs, general conditions, brochures) and their markdown conversions
- **Structured analysis**: AI-extracted information (coverages, exclusions, terms) stored as JSON

This differs from **regulatory products** (Ramos/Modalidades) from the DGSFP API - those are authorized lines of business, not commercial products.

## Pipeline

```
sync_data → sync_folders → Add PDFs → process_pdfs → analyze_products → build_db
```

## Quick Start

```bash
# 1. Sync regulatory data
uv run python -m scripts.sync_data

# 2. Create company folder (creates for all companies)
uv run python -m scripts.sync_folders

# 3. Add PDFs to sources/{product_name}/ (manual step)

# 4. Convert PDFs to markdown
uv run python -m scripts.process_pdfs --company-key C0737

# 5. Run AI analysis
uv run python -m scripts.analyze_products --company-key C0737

# 6. Rebuild database
uv run python -m scripts.build_db
```

## Folder Structure

```
data/products_by_insurance_company/{company_name}/
├── index.json              # Product catalog
├── analysis/               # AI analysis output (JSON per product)
├── metadata/               # Processing summaries
└── sources/{product_name}/ # PDFs and markdown
```

### index.json Format

```json
[{
  "fetched_at": "2026-01-27T00:00:00Z",
  "version": "1.0",
  "company_key": "C0737",
  "products": [{
    "product_branch": "09",
    "product_name": "seguro_hogar",
    "product_id": "urn:C0737-01",
    "source_url": "https://example.com/seguro-hogar"
  }]
}]
```

- `product_name`: Must match subfolder name under `sources/` (snake_case)
- `product_id`: Unique identifier, e.g., `urn:{company_key}-{seq}`
- `product_branch`: DGSFP branch code(s), e.g., `"09"` or `["05","06"]`

## Scripts Reference

| Script | Purpose |
|--------|---------|
| `scripts.sync_data` | Fetch regulatory data, rebuild database |
| `scripts.sync_folders` | Create company folders |
| `scripts.process_pdfs --company-key KEY` | Convert PDFs to markdown |
| `scripts.analyze_products --company-key KEY` | AI analysis of products |
| `scripts.build_db` | Build SQLite database from JSON |

### analyze_products Options

- `--product NAME` - Analyze single product
- `--dry-run` - List products without analyzing

## Environment Variables

| Variable | Required |
|----------|----------|
| `GEMINI_API_KEY` | Yes, for `analyze_products` |

## Related Documentation

- [INSURANCE_PUBLIC_DATA_FETCH.md](INSURANCE_PUBLIC_DATA_FETCH.md) - Regulatory data API
- [README.md](../README.md) - Package usage
- [CONTRIBUTING.md](../CONTRIBUTING.md) - Development setup
