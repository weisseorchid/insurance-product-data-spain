# Generating the Product Pool for an Insurer

This document explains how to generate the **pool of products** for an insurance company using the project scripts.

## Overview

The **product pool** is the set of commercial insurance products for a given insurer, including:
- **Source documents**: PDFs (IPIDs, general conditions, brochures) and their markdown conversions
- **Structured analysis**: AI-extracted information (coverages, exclusions, terms) stored as JSON

This differs from **regulatory products** (Ramos/Modalidades) from the DGSFP API - those are authorized lines of business, not commercial products.

## Pipeline

```
sync_data → sync_folders → Add PDFs → process_pdfs (with validation) → analyze_products (with validation & retry) → build_db
```

### Validation & Quality Control

The pipeline includes comprehensive validation at each stage:

1. **PDF Validation** (`process_pdfs`):
   - Magic bytes check (must be real PDF)
   - Block page detection (Cloudflare, captcha pages)
   - Empty/near-empty markdown rejection
   - Validation failures logged to `data/runs.jsonl`

2. **Analysis Validation** (`analyze_products`):
   - Pydantic v2 schema validation
   - Automatic retry with exponential backoff (max 3 attempts)
   - Idempotency: skips re-analysis if inputs and schema unchanged
   - Provenance tracking (model, schema version, input hashes)
   - Quality flags for known bad documents (e.g., Mutua Madrileña blocks)

3. **CI Checks**:
   - Block page detection in committed files
   - Duplicate markdown hash detection
   - Allowlist for known issues (doesn't fail CI but flags them)
   - PR hygiene: scans all blobs in commit range for size/extension violations

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
| `scripts.process_pdfs --company-key KEY` | Convert PDFs to markdown (with validation) |
| `scripts.analyze_products --company-key KEY` | AI analysis of products (with validation & retry) |
| `scripts.build_db` | Build SQLite database from JSON |
| `scripts.ci.check_data_integrity` | Check committed data for quality issues |
| `scripts.ci.check_repo_hygiene --base origin/main` | Check PR for blob size/extension violations |

### process_pdfs Details

Validates each PDF and its markdown output:
- Rejects non-PDF files (magic bytes check)
- Rejects block pages (Cloudflare, captcha)
- Rejects empty/near-empty markdown (< 100 chars by default)
- Logs failures to `data/runs.jsonl`
- Does not save invalid markdown

### analyze_products Options

- `--product NAME` - Analyze single product
- `--dry-run` - List products without analyzing
- `--force` - Force re-analysis (skip idempotency check)

**New features:**
- Idempotency: Skips analysis if input files and schema unchanged
- Retry logic: 3 attempts with exponential backoff on API/validation errors
- Provenance: Stores model name, schema version, input hashes
- Quality flags: Marks analyses with known bad input as `untrusted`
- Logs failures to `data/runs.jsonl`

## Logs and Provenance

### data/runs.jsonl

Append-only log of processing events (JSONL format, one event per line):
- `validation_failure`: Document rejected during PDF processing
- `analysis_failure`: Product analysis failed after all retries

Each event includes timestamp, script name, status, and event-specific details.

### Analysis Provenance

Each analysis JSON includes `metadata.analysis_provenance`:
```json
{
  "model": "gemini-3-flash-preview",
  "schema_version": "1.0",
  "input_hash": "abc123...",
  "markdown_hashes": {"doc1.md": "def456..."},
  "markdown_files": ["doc1.md", "doc2.md"]
}
```

Also includes `metadata.quality_flags`:
```json
{
  "has_known_quality_issues": true,
  "untrusted": true
}
```

## Known Issues

### Mutua Madrileña Cloudflare Blocks

19 Mutua Madrileña markdown files are Cloudflare "Pardon Our Interruption" block pages (hash `9c2fcc5d899fb2a6196360ee14dfbff58676911c57fda1b59578702c341b0ff4`).

**Quarantine approach:**
- Files remain in repository (not deleted)
- CI checks allowlist this hash (doesn't fail CI)
- Analyses using these files are flagged as `untrusted` in metadata
- Visible in reports but doesn't block pipeline

## Environment Variables

| Variable | Required |
|----------|----------|
| `GEMINI_API_KEY` | Yes, for `analyze_products` |

## Related Documentation

- [INSURANCE_PUBLIC_DATA_FETCH.md](INSURANCE_PUBLIC_DATA_FETCH.md) - Regulatory data API
- [README.md](../README.md) - Package usage
- [CONTRIBUTING.md](../CONTRIBUTING.md) - Development setup
