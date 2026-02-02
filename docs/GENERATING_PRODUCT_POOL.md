# Generating the Product Pool for an Insurer

This document explains how to generate the **pool of products** for an insurance company using the project scripts, and documents the structure of the `data/` folder.

---

## 1. Overview

The **product pool** refers to the curated set of **commercial insurance products** for a given insurer, including:

- **Source documents**: PDFs (IPIDs, general conditions, brochures, etc.) and their markdown conversions
- **Structured analysis**: AI-extracted information (coverages, exclusions, contract terms, etc.) stored as JSON

This differs from the **regulatory products** (Ramos/Modalidades) available via the DGSFP API—those are authorized lines of business per company. The product pool here is about **actual commercial products** with full policy documentation and AI analysis.

---

## 2. Pipeline Overview

```
┌─────────────────────┐     ┌──────────────────────┐     ┌─────────────────────┐
│ 1. sync_data        │     │ 2. Sync folders      │     │ 3. Add PDFs to      │
│ (regulatory data)   │ ──► │  (sync_folders)      │ ──► │ sources/            │
└─────────────────────┘     └──────────────────────┘     └─────────────────────┘
                                                                  │
                                                                  ▼
┌─────────────────────┐     ┌──────────────────────┐     ┌─────────────────────┐
│ 6. build_db         │ ◄── │ 5. analyze_products  │ ◄── │ 4. process_pdfs     │
│ (SQLite + package)  │     │ (Gemini AI analysis) │     │ (PDF → markdown)    │
└─────────────────────┘     └──────────────────────┘     └─────────────────────┘
```

---

## 3. Step-by-Step Instructions

### Step 0: Prerequisites

- **uv** installed (see [CONTRIBUTING.md](../CONTRIBUTING.md))
- **Python environment** synced: `uv sync`
- **Company key** (e.g. `C0737` for Nationale-Nederlanden) — look it up in `data/insurance_companies.json`
- **GEMINI_API_KEY** in `.env` (required for `analyze_products`)

### Step 1: Sync Regulatory Data

Ensure companies and distributors are up to date:

```bash
uv run python -m scripts.sync_data
```

This fetches from the DGSFP/Mineco API and saves:

- `data/insurance_companies.json`
- `data/insurance_distributors.json`
- `data/insurance_branches.json` (if applicable)

### Step 2: Create Company Folder and Product Index

Create the folder structure for the insurer. The folder name must be the **snake_case** of the company denomination (as in `insurance_companies.json`).

**Option A: Use `sync_folders` script** (creates folders for all companies):

```bash
uv run python -m scripts.sync_folders
```

This creates folders for all companies in `insurance_companies.json` under `data/products_by_insurance_company/`.

**Option B: Create folder manually**

**Example** for `C0737` (Nationale-Nederlanden):
- Denomination: `NATIONALE-NEDERLANDEN GENERALES, COMPAÑIA DE SEGUROS Y REASEGUROS, SOCIEDAD ANONIMA ESPAÑOLA`
- Folder: `data/products_by_insurance_company/nationale_nederlanden_generales_compañia_de_seguros_y_reaseguros_sociedad_anonima_española/`

Create the following:

1. **Company folder**: `data/products_by_insurance_company/{company_name_snake_case}/`

2. **`index.json`** at the root of the company folder. Format:

```json
[
  {
    "fetched_at": "2026-01-27T00:00:00Z",
    "version": "1.0",
    "company_key": "C0737",
    "status": "Active",
    "products": [
      {
        "product_branch": "09",
        "product_name": "seguro_hogar",
        "product_id": "urn:C0737-01",
        "source_url": "https://www.nnespana.es/seguro-hogar"
      }
    ]
  }
]
```

- **`product_name`**: Must match the subfolder name under `sources/` (snake_case)
- **`product_id`**: Unique identifier, e.g. `urn:{company_key}-{seq}`
- **`product_branch`**: DGSFP branch code(s), e.g. `"09"` (hogar), `"00"` (vida), or array `["05","06"]` for multi-branch

### Step 3: Add Source PDFs

Place PDFs for each product under:

```
data/products_by_insurance_company/{company_folder}/sources/{product_name}/
```

Example for `seguro_hogar`:

```
sources/seguro_hogar/
├── NN_Condiciones_Generales_Mihogar_seguro.pdf
├── NN_Folleto_Mihogar_Seguro.pdf
└── PID_MIHOGAR_SEGURO.pdf
```

Typical document types: IPID (PID), Condiciones Generales (CG), Condiciones Limitativas (CL), Folletos.

### Step 4: Convert PDFs to Markdown

```bash
uv run python -m scripts.process_pdfs --company-key C0737
```

- Reads PDFs from `sources/{product_name}/*.pdf`
- Converts each to `.md` alongside the PDF (using markitdown)
- Writes `metadata/processing_summary.json` with per-file status

### Step 5: Run AI Analysis

```bash
uv run python -m scripts.analyze_products --company-key C0737
```

- Reads `index.json` and markdown files from `sources/`
- Uses Gemini to extract structured analysis (coverages, exclusions, terms, etc.)
- Writes `analysis/{product_name}.json` for each product
- Writes `metadata/analysis_summary.json`

**Options**:

- `--product seguro_hogar` — analyze only one product
- `--dry-run` — list products and markdown files without analyzing
- `--no-summary` — skip saving `analysis_summary.json`

### Step 6: Rebuild Database

```bash
uv run python -m scripts.build_db
```

Or run the full sync (which includes `build_db`):

```bash
uv run python -m scripts.sync_data
```

This compiles all JSON (companies, distributors, branches, and product analyses) into `insurance_product_data_sp/data/insurance.db` for the package.

---

## 4. Data Folder Structure

### 4.1 Root Layout

```
data/
├── insurance_branches.json      # DGSFP branch codes (ramos)
├── insurance_companies.json     # Companies from regulator (with insurance_branches)
├── insurance_distributors.json  # Distributors from regulator
└── products_by_insurance_company/
    └── {company_name_snake_case}/
        ├── index.json           # Product catalog for this insurer
        ├── analysis/            # AI analysis output (JSON per product)
        ├── metadata/            # Processing and analysis summaries
        └── sources/             # PDFs and markdown per product
```

### 4.2 File Reference

| File | Description | Source |
|------|-------------|--------|
| `insurance_branches.json` | List of insurance branches (ramos) with codes and names | Static/reference data |
| `insurance_companies.json` | All insurers with details (NIF, status, insurance_branches, etc.) | `sync_data` from DGSFP |
| `insurance_distributors.json` | All distributors with agency contracts | `sync_data` from DGSFP |

### 4.3 `products_by_insurance_company/{company}/`

| Path | Description |
|------|-------------|
| `index.json` | Product catalog: list of products with `product_id`, `product_name`, `product_branch`, `source_url` |
| `analysis/{product_name}.json` | Full AI analysis for each product (coverages, exclusions, terms, etc.) |
| `metadata/analysis_summary.json` | Summary of `analyze_products` run (success/fail per product) |
| `metadata/processing_summary.json` | Summary of `process_pdfs` run (success/fail per PDF) |
| `sources/{product_name}/*.pdf` | Original policy documents |
| `sources/{product_name}/*.md` | Markdown conversion of each PDF (from `process_pdfs`) |

### 4.4 Analysis JSON Schema (per product)

Each `analysis/{product_name}.json` follows the `InsuranceProduct` schema:

- `product_name`, `product_id`, `product_branch`, `source_urls`
- `metadata`: `analyzed_at`, `analyzer_version`
- `analysis`:
  - `product_summary`: type, target_audience, descriptions, key_benefits
  - `coverages`: name, category (basic/optional), description, limits, waiting periods
  - `exclusions`: description, category, legal references
  - `contract_terms`: duration, renewal, cancellation, payment
  - `geographic_coverage`, `obligations`, `pricing`, etc.

---

## 5. Scripts Reference

| Script | Purpose | Key args |
|--------|---------|----------|
| `scripts.sync_data` | Fetch companies, distributors; save JSON; rebuild DB | — |
| `scripts.sync_folders` | Create empty company folders from `insurance_companies.json` | — |
| `scripts.setup_products` | Create raw/processed/structured layout from regulatory data | (different layout; see script) |
| `scripts.process_pdfs` | Convert PDFs to markdown | `--company-key C0737` |
| `scripts.analyze_products` | AI analysis of product docs | `--company-key C0737` |
| `scripts.build_db` | Build SQLite DB from JSON | — |

---

## 6. Environment Variables

| Variable | Used by | Required |
|----------|---------|----------|
| `GEMINI_API_KEY` | `analyze_products` (Gemini AI client) | Yes, for analysis |

Define in project root `.env`:

```
GEMINI_API_KEY=your_key_here
```

---

## 7. Adding a New Insurer

1. Run `sync_data` so the company exists in `insurance_companies.json`.
2. Get `company_key` and `denomination` from that file.
3. Derive folder name: `text_to_snake_case(denomination)`.
4. Create `data/products_by_insurance_company/{folder}/index.json` and `sources/{product_name}/` for each product.
5. Download and place PDFs in `sources/{product_name}/`.
6. Run `process_pdfs --company-key {key}`.
7. Run `analyze_products --company-key {key}`.
8. Run `build_db` or `sync_data`.

---

## 8. Related Documentation

- [INSURANCE_PUBLIC_DATA_FETCH.md](INSURANCE_PUBLIC_DATA_FETCH.md) — Regulatory data (DGSFP/Mineco API, Ramos/Modalidades)
- [README.md](../README.md) — Package usage and API
- [CONTRIBUTING.md](../CONTRIBUTING.md) — Development setup and tools
