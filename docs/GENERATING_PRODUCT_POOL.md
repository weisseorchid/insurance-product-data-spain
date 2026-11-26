# Generating the Product Pool for an Insurer

This document explains how to generate the **pool of products** for an insurance company using the project scripts.

## Overview

The **product pool** is the set of commercial insurance products for a given insurer, including:
- **Source documents**: PDFs (IPIDs, general conditions, brochures) and their markdown conversions
- **Structured analysis**: AI-extracted information (coverages, exclusions, terms) stored as JSON

This differs from **regulatory products** (Ramos/Modalidades) from the DGSFP API - those are authorized lines of business, not commercial products.

## Pipeline

```
sync_data → write data/sources/<company_key>.jsonl → fetch_product_documents (robots, rate limit, validation)
          → [process_pdfs --source cache] → analyze_products (with validation & retry) → build_db
```

The source manifest and fetcher are described in [SOURCE_MANIFEST.md](SOURCE_MANIFEST.md). The legacy
flow (PDFs copied by hand into `sources/{product_name}/`, then `process_pdfs`) still works.

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
   - Mistral fallback when Gemini keeps failing (see "LLM providers and Mistral fallback")
   - Idempotency: skips re-analysis if inputs and schema unchanged
   - Provenance tracking (model, schema version, input hashes)
   - Quality flags: `has_known_quality_issues` / `untrusted` for known bad companies;
     `incomplete_inputs` when some documents were dropped as block pages
   - Writes local `metadata/analysis_gaps.json` (gitignored; see Gap reports below)

3. **CI Checks** (`scripts/ci/check_data_integrity.py`, committed files only, no cache needed):
   - Branch codes in `index.json` and analyses must exist in `data/insurance_branches.jsonl`
   - Analyses must use `branches` (list), not the deprecated singular `product_branch`
   - Analyses must have `metadata.quality_flags` with boolean `has_known_quality_issues` and `untrusted`
   - Block pages: `documents.jsonl` `markdown_sha256` checked against `data/quality/known_block_page_hashes.jsonl`;
     different PDFs sharing one markdown hash are also flagged
   - Known-issues baseline: `data/quality/known_data_issues.jsonl` lists the current violations; only NEW ones fail CI
   - PR hygiene: scans all blobs in commit range for size/extension violations

#### Known-issues baseline

`data/quality/known_data_issues.jsonl` holds one violation per line, keyed by `check`, `file`, `item`, `value`
(`detail` is informational). When you fix data, delete the matching lines (CI prints
`Resolved, remove from ...` for entries that no longer occur). Never add lines to hide a new problem
without a note in the PR. To regenerate the file from the current data:

```bash
uv run python scripts/ci/check_data_integrity.py --write-baseline
```

To add a newly discovered block-page markdown hash, append it to `data/quality/known_block_page_hashes.jsonl`
(sorted by `markdown_sha256`; fields `markdown_sha256`, `reason`, optional `company_key`, `note`).

## Quick Start

```bash
# 1. Sync regulatory data
uv run python -m scripts.sync_data

# 2. Create company folder (creates for all companies)
uv run python -m scripts.sync_folders

# 3. Describe the products and documents in data/sources/M0083.jsonl (see SOURCE_MANIFEST.md), then fetch
uv run python -m scripts.fetch_product_documents --company-key M0083 --dry-run
uv run python -m scripts.fetch_product_documents --company-key M0083

# 4. (Optional) re-convert cached PDFs to markdown (the fetcher already converts)
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
| `scripts.fetch_product_documents --company-key KEY` | Fetch documents listed in `data/sources/KEY.jsonl` (polite, validated) |
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
- `--provider auto|gemini|mistral` - LLM provider (default `auto`: Gemini, then Mistral)

**New features:**
- Idempotency: Skips analysis if input files and schema unchanged
- Retry logic: 3 attempts with exponential backoff on API/validation errors
- Provenance: Stores model name, schema version, input hashes
- Quality flags: Marks analyses with known bad input as `untrusted`
- Logs one run entry (counts, failures, fallbacks) to `data/runs.jsonl`

### LLM providers and Mistral fallback

`scripts/clients/llm.py` chains provider clients (`scripts/clients/gemini.py`,
`scripts/clients/mistral.py`). Both send the same prompt, use the same backoff
(2s, 4s, ... max 16s, 3 attempts) and validate the output with the same `ProductAnalysis` model.
Mistral uses JSON mode (`response_format={"type": "json_object"}`) with the schema in the system prompt.

| `--provider` | Behaviour |
|--------------|-----------|
| `auto` (default) | Gemini first. Falls back to Mistral only after Gemini's retries are exhausted with a retryable error (429, 5xx, 408, timeout, connection error) or invalid output (validation failure, empty response). No fallback when `MISTRAL_API_KEY` is unset (logged once). |
| `gemini` | Gemini only (previous behaviour). |
| `mistral` | Mistral only; exits 2 if `MISTRAL_API_KEY` is unset. |

Auth and config errors never fall back silently: 401/403, 400 (including an invalid API key),
404 (unknown model), a missing `GEMINI_API_KEY`, and unexpected exceptions fail the product with a
clear error. After the first auth/config error Gemini is not called again in that run. To use Mistral
anyway, rerun with `--provider mistral`. The reason: a broken key is a setup problem, and switching
every analysis to another model without anyone noticing would hide it.

Idempotency accepts an existing analysis made by any model in the current chain, so an analysis
produced by the fallback is not re-run (and re-billed) on the next `auto` run. Use `--force`, or
`--provider gemini`, to redo it with Gemini.

## Logs and Provenance

### data/runs.jsonl

Append-only log (JSONL, checked by CI for `script` and `started_at`):
- `fetch_product_documents` and `analyze_products` append one run entry each, with `counts`,
  `model` and `details`. For `analyze_products`, `counts` has `analyzed`, `skipped`, `failed`,
  `by_provider_<provider>` and `fallbacks`; `details` has `provider_mode`, the provider chain,
  `failures` (product and error) and `fallbacks` (from, to, reason).
- `process_pdfs` still appends `validation_failure` events (`timestamp`/`event_type` format).

### Analysis Provenance

Each analysis JSON includes `metadata.analysis_provenance`:
```json
{
  "provider": "gemini",
  "model": "gemini-3.8-flash",
  "schema_version": "1.0",
  "input_hash": "abc123...",
  "markdown_hashes": {"doc1.md": "def456..."},
  "markdown_files": ["doc1.md", "doc2.md"]
}
```

`provider` and `model` are the ones that actually produced the analysis. When Mistral answered as a
fallback, `provider` is `mistral` and `fallback_reason` says why Gemini was skipped
(e.g. `retryable: ServerError: 503 UNAVAILABLE...`).

Also includes `metadata.quality_flags`:
```json
{
  "has_known_quality_issues": true,
  "untrusted": true
}
```

## Known Issues

### Mutua Madrileña Cloudflare Blocks

19 Mutua Madrileña documents historically resolved to a Cloudflare "Pardon Our Interruption" page
(hash `9c2fcc5d899fb2a6196360ee14dfbff58676911c57fda1b59578702c341b0ff4`).

**Current approach (block pages are gaps, not knowledge):**
- The hash stays in `data/quality/known_block_page_hashes.jsonl` so the same page is recognized
- `fetch_product_documents` and `process_pdfs` refuse to keep that markdown hash in `documents.jsonl`
- `analyze_products` drops block-page inputs before calling Gemini; products with only block pages
  are reported as `no_usable_documents` gaps; mixed products set `incomplete_inputs` and still analyze
  the remaining documents (exit code 0 unless every document is unusable or analysis fails)
- Existing baselined issues in `data/quality/known_data_issues.jsonl` remain until Data Ops cleans
  the Mutua rows / analyses; NEW block-page hashes still fail CI

### Gap reports (local, gitignored)

Per-script reports under each company folder (not committed):

| File | Written by |
|------|------------|
| `metadata/fetch_gaps.json` | `fetch_product_documents` |
| `metadata/analysis_gaps.json` | `analyze_products` |

Stable JSON (sorted gaps, no timestamps). A full-company run replaces that script's file; `--product`
merges by `product_id` so other products' gaps are kept. Patterns live in
`scripts/utils/document_validation.py` (shared with CI).

## Environment Variables

| Variable | Required |
|----------|----------|
| `GEMINI_API_KEY` | Yes, for `analyze_products` (`auto` / `gemini`) |
| `MISTRAL_API_KEY` | Optional; enables the Mistral fallback, required for `--provider mistral` (from console.mistral.ai) |
| `MISTRAL_MODEL` | Optional; default `mistral-large-latest` |

## Related Documentation

- [PRODUCT_SCHEMA.md](PRODUCT_SCHEMA.md) - Product data schema v1 specification
- [SOURCE_MANIFEST.md](SOURCE_MANIFEST.md) - Per-insurer source manifest and document fetcher
- [INSURANCE_PUBLIC_DATA_FETCH.md](INSURANCE_PUBLIC_DATA_FETCH.md) - Regulatory data API
- [README.md](../README.md) - Package usage
- [CONTRIBUTING.md](../CONTRIBUTING.md) - Development setup
