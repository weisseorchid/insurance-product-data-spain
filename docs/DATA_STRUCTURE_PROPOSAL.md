# Data Structure Proposal: Products by Insurer

## Overview

This document proposes a new data organization that:
- **Adds** `products_by_insurer/` structure alongside existing `insurance_companies/` folder
- **Keeps** `insurance_companies/` for raw data gathering and processing files
- **Creates** `products_by_insurer/` with structured layers: raw → processed → structured
- **Enables** incremental processing (company by company)
- **Facilitates** querying and analysis of products per insurer

---

## Proposed Structure

```
data/
├── insurance_companies/                    # Raw data gathering (existing structure)
│   ├── {company_name_snake}/               # Company folders (existing)
│   │   └── [raw files, processing files]   # Files for processing and raw data
│   └── ...
├── products_by_insurer/                    # Structured products (new structure)
│   ├── index.json                          # Master index: all companies with metadata
│   ├── {company_key}_{company_name_snake}/ # One folder per company
│   │   ├── raw/                            # Original fetched data (immutable)
│   │   │   ├── company_details.json        # Full company details from GetAseguradora
│   │   │   └── metadata.json               # Fetch timestamp, source URL, version
│   │   ├── processed/                      # Extracted/cleaned data
│   │   │   ├── products.json               # Extracted insurance_branches (products)
│   │   │   ├── company_info.json           # Company metadata (key, name, status, etc.)
│   │   │   └── relationships.json          # Executives, shareholders, agencies (optional)
│   │   └── structured/                     # Normalized, queryable format
│   │       ├── products.json               # Products with company context, normalized
│   │       └── index.json                  # Quick lookup index for this company
│   └── ...
├── insurance_companies.json                # Full dataset (source for products_by_insurer)
└── insurance_distributors.json
```

**Note**: 
- `insurance_companies/` folder: Keep for gathering raw files and processing files
- `products_by_insurer/`: New structured layer focused on products (raw/processed/structured)
- Both structures coexist and serve different purposes

---

## Layer Details

### 1. Raw Layer (`raw/`)
**Purpose**: Store original, immutable data from the API

**Files**:
- `company_details.json`: Complete response from `GetAseguradora` (all fields)
- `metadata.json`: Fetch metadata
  ```json
  {
    "fetched_at": "2026-01-26T00:00:00Z",
    "source_url": "https://rrpp.dgsfp.mineco.es/Aseguradora/GetAseguradora/?clave=C0001",
    "version": "1.0",
    "company_key": "C0001"
  }
  ```

**Why**: Preserve original data for audit, reprocessing, debugging

---

### 2. Processed Layer (`processed/`)
**Purpose**: Extracted, cleaned, and validated data ready for use

**Files**:
- `products.json`: Extracted `insurance_branches` array
  ```json
  [
    {
      "codigo": "01",
      "ramo": "1/Accidentes",
      "modalidad": "(Ramo Completo)",
      "fechaAlta": "2008-07-15T00:00:00",
      "estado": "Activo"
    }
  ]
  ```
- `company_info.json`: Essential company metadata
  ```json
  {
    "company_key": "C0001",
    "denomination": "ASEGURADORES AGRUPADOS...",
    "nif": "A37001369",
    "status": "Activa",
    "website": "https://...",
    "authorization_date": "19/02/1947"
  }
  ```
- `relationships.json` (optional): Executives, shareholders, agencies if needed

**Why**: Clean separation of products from company metadata; easier to process

---

### 3. Structured Layer (`structured/`)
**Purpose**: Normalized, queryable format optimized for analysis

**Files**:
- `products.json`: Products with company context, normalized fields
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
      "authorized_since": "2008-07-15",
      "normalized_ramo": "accidentes",  # For querying
      "product_type": "no_vida"         # Categorized
    }
  ]
  ```
- `index.json`: Quick lookup for this company
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

**Why**: Optimized for querying, analysis, and reporting

---

### 4. Master Index (`index.json`)
**Purpose**: Quick overview of all companies and their products

```json
{
  "total_companies": 1068,
  "last_updated": "2026-01-26T00:00:00Z",
  "companies": [
    {
      "company_key": "C0001",
      "company_name": "ASEGURADORES AGRUPADOS...",
      "folder_name": "c0001_aseguradores_agrupados_sociedad_anonima_de_seguros_asegrup",
      "status": "Activa",
      "product_count": 7,
      "last_processed": "2026-01-26T00:00:00Z"
    }
  ]
}
```

---

## Folder Naming Convention

**Format**: `{company_key}_{company_name_snake_case}`

**Examples**:
- `C0001_aseguradores_agrupados_sociedad_anonima_de_seguros_asegrup`
- `C0058_mapfre_espana_compania_de_seguros_y_reaseguros_s_a`
- `C0031_caja_de_seguros_reunidos_compania_de_seguros_y_reaseguros_s_a`

**Why**: 
- `company_key` ensures uniqueness and easy lookup
- `company_name` makes folders human-readable
- Snake_case avoids filesystem issues

---

## Example: Complete Structure for C0001

```
data/products_by_insurer/
├── index.json
└── C0001_aseguradores_agrupados_sociedad_anonima_de_seguros_asegrup/
    ├── raw/
    │   ├── company_details.json    # Full InsuranceCompanyDetails object
    │   └── metadata.json           # {fetched_at, source_url, version, company_key}
    ├── processed/
    │   ├── products.json           # Array of insurance_branches
    │   ├── company_info.json       # {company_key, denomination, nif, status, ...}
    │   └── relationships.json      # {executives, shareholders, agencies} (optional)
    └── structured/
        ├── products.json           # Normalized products with company context
        └── index.json              # Company-level index
```

---

## Migration Strategy

### Phase 1: Create Structure for Sample Companies
1. Select 2-3 companies (e.g., C0001, C0058, C0031)
2. Create `products_by_insurer/` folder structure with script
3. Extract data from `insurance_companies.json` into new structure
4. Validate structure and querying
5. **Keep** `insurance_companies/` folder for raw data gathering

### Phase 2: Add Processing Functions
1. Add `PRODUCTS_BY_INSURER_STORAGE_PATH` to `config.py` (keep existing paths)
2. Create processing functions:
   - `extract_products_from_company()` → `processed/products.json`
   - `normalize_products()` → `structured/products.json`
   - `build_company_index()` → `structured/index.json`
   - `build_master_index()` → `index.json`
3. Optionally sync from `insurance_companies/` folder files

### Phase 3: Incremental Processing
1. Process companies incrementally as needed
2. Source data from `insurance_companies.json` or `insurance_companies/` folder
3. Build structured products in `products_by_insurer/`
4. Both structures coexist: `insurance_companies/` for raw, `products_by_insurer/` for structured

---

## Benefits

1. **Dual Structure**: 
   - `insurance_companies/` for raw data gathering and processing files
   - `products_by_insurer/` for structured, queryable products
2. **Clear Separation**: Raw → Processed → Structured layers in products_by_insurer
3. **Incremental Processing**: Process one company at a time
4. **Easy Querying**: Structured layer optimized for queries
5. **Audit Trail**: Raw layer preserves original data
6. **Scalability**: Add new companies without reprocessing all
7. **Flexibility**: Can reprocess individual companies, source from either structure
8. **Human-Readable**: Folder names include company info
9. **Backward Compatible**: Existing `insurance_companies/` structure remains intact

---

## Querying Examples

### Get all products for a company
```python
company_key = "C0001"
folder = f"data/products_by_insurer/{company_key}_..."
products = load_json(f"{folder}/structured/products.json")
```

### Get all companies that sell a specific product
```python
# Query structured/products.json across all companies
ramo_code = "13"  # Responsabilidad civil general
# Filter products where ramo_code == "13"
```

### Get master index
```python
index = load_json("data/products_by_insurer/index.json")
active_companies = [c for c in index["companies"] if c["status"] == "Activa"]
```

---

## Next Steps

1. **Review this proposal** and adjust as needed
2. **Select 2-3 example companies** to start with
3. **Create folder structure** for examples
4. **Extract sample data** from `insurance_companies.json`
5. **Test querying** on structured data
6. **Iterate** on structure based on findings
