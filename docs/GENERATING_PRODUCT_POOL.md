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
uv run python -m scripts.process_pdfs --company-key M0083

# 5. Run AI analysis
uv run python -m scripts.analyze_products --company-key M0083

# 6. Rebuild database -- ensure there are no local open connections for this to work!
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

### index.json Format (Schema v1)

```json
[{
  "fetched_at": "2026-01-27T00:00:00Z",
  "version": "1.0",
  "company_key": "C0737",
  "status": "Active",
  "products": [{
    "product_id": "urn:C0737-01",
    "company_key": "C0737",
    "product_name": "seguro_hogar",
    "branches": ["09"],
    "source_url": "https://example.com/seguro-hogar",
    "document_references": [
      {
        "filename": "CG-seguro-hogar.pdf",
        "pdf_sha256": "2472561d...",
        "markdown_sha256": "58c44471...",
        "doc_type": "general_conditions"
      }
    ],
    "analysis_path": "analysis/seguro_hogar.json",
    "fetched_at": "2026-01-27T00:00:00Z",
    "metadata": {}
  }]
}]
```

**Schema v1 fields:**
- `product_id`: Unique identifier in URN format, e.g., `urn:{company_key}-{seq}`
- `company_key`: DGSFP company key (e.g., `C0737`)
- `product_name`: Must match subfolder name under `sources/` (snake_case)
- `branches`: List of DGSFP branch codes, e.g., `["09"]` or `["05", "06"]`
- `document_references`: Links to documents in `documents.jsonl` (auto-populated by migration)
- `analysis_path`: Relative path to analysis JSON (optional)

See [PRODUCT_SCHEMA.md](PRODUCT_SCHEMA.md) for complete schema documentation.

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

- [PRODUCT_SCHEMA.md](PRODUCT_SCHEMA.md) - Product data schema v1 specification
- [INSURANCE_PUBLIC_DATA_FETCH.md](INSURANCE_PUBLIC_DATA_FETCH.md) - Regulatory data API
- [README.md](../README.md) - Package usage
- [CONTRIBUTING.md](../CONTRIBUTING.md) - Development setup
