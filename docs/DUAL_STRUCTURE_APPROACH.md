# Dual Structure Approach

## Overview

The project uses **two complementary folder structures** that serve different purposes:

1. **`insurance_companies/`** - For raw data gathering and processing files
2. **`products_by_insurer/`** - For structured, queryable products (raw/processed/structured layers)

Both structures coexist and work together.

---

## Structure Comparison

### `insurance_companies/` (Existing)
```
data/insurance_companies/
└── {company_name_snake}/
    └── [raw files, processing files, etc.]
```

**Purpose**: 
- Gather raw data files
- Store processing scripts/temporary files
- Manual curation and data collection
- Flexible file organization per company

**Use when**:
- Collecting raw data from various sources
- Processing files that need manual review
- Storing intermediate processing results
- Files that don't fit a structured schema

---

### `products_by_insurer/` (New)
```
data/products_by_insurer/
├── index.json
└── {company_key}_{company_name_snake}/
    ├── raw/
    │   ├── company_details.json
    │   └── metadata.json
    ├── processed/
    │   ├── products.json
    │   └── company_info.json
    └── structured/
        ├── products.json
        └── index.json
```

**Purpose**:
- Structured, normalized products data
- Queryable format optimized for analysis
- Clear separation: raw → processed → structured
- Automated processing pipeline

**Use when**:
- Querying products per company
- Analyzing product distributions
- Building reports or APIs
- Automated data processing

---

## Data Flow

```
┌─────────────────────────────────────┐
│  insurance_companies.json            │
│  (source data)                       │
└──────────────┬──────────────────────┘
               │
               ├──────────────────────────┐
               │                           │
               ▼                           ▼
┌──────────────────────────┐  ┌──────────────────────────────┐
│ insurance_companies/     │  │ products_by_insurer/         │
│                          │  │                              │
│ • Raw files              │  │ • Structured products        │
│ • Processing files       │  │ • Queryable format           │
│ • Manual curation       │  │ • Automated pipeline         │
└──────────────────────────┘  └──────────────────────────────┘
```

---

## When to Use Which

### Use `insurance_companies/` for:
- ✅ Collecting raw data files (CSV, PDF, HTML, etc.)
- ✅ Storing processing scripts
- ✅ Manual data curation
- ✅ Temporary/intermediate files
- ✅ Files that need human review

### Use `products_by_insurer/` for:
- ✅ Querying products per company
- ✅ Automated data processing
- ✅ Building reports/APIs
- ✅ Product analysis and statistics
- ✅ Normalized, structured data

---

## Example Workflow

1. **Collect raw data** → Store in `insurance_companies/{company}/`
2. **Process and extract** → Create structured data in `products_by_insurer/{company_key}_{name}/`
3. **Query and analyze** → Use `products_by_insurer/structured/products.json`

---

## Configuration

Both paths are configured in `config.py`:

```python
INSURANCE_COMPANIES_STORAGE_PATH: Path = BASE_STORAGE_PATH / "insurance_companies"
PRODUCTS_BY_INSURER_STORAGE_PATH: Path = BASE_STORAGE_PATH / "products_by_insurer"
```

---

## Benefits

1. **Separation of Concerns**: Raw gathering vs. structured querying
2. **Flexibility**: `insurance_companies/` for any file type
3. **Structure**: `products_by_insurer/` for consistent, queryable data
4. **Backward Compatible**: Existing `insurance_companies/` structure remains
5. **Incremental**: Process companies one at a time as needed

---

## See Also

- **Full proposal**: `docs/DATA_STRUCTURE_PROPOSAL.md`
- **Quick start**: `docs/QUICK_START_PRODUCTS_STRUCTURE.md`
- **Setup script**: `insurance_product_data_spain/services/v1/insurance_companies/setup_products_structure.py`
