# Building the Package

This package uses JSONL source files and builds a SQLite database at package build time. This document explains the build process for maintainers and contributors.

## Quick Start

To build the package locally:

```bash
# 1. Build the database from JSONL sources
uv run python -m scripts.build_db

# 2. Build the wheel and sdist
uv build

# 3. Verify the wheel contains the database
unzip -l dist/*.whl | grep insurance.db
```

## Why This Workflow?

**Problem**: Git doesn't handle binary files or large files well. Each commit of a 52MB database adds 52MB to repository history, even if only small changes were made.

**Solution**: Store source data as JSONL (one record per line), build the database from JSONL at package build time.

**Benefits**:
- **Diff-friendly**: Git diffs show only changed records, not entire files
- **Smaller repo**: JSONL compresses better and grows proportionally to actual changes
- **Deterministic builds**: Same JSONL input always produces the same database

## Build Process

### 1. Source Data (JSONL)

Data is stored as JSONL (JSON Lines) in `data/`:
- `insurance_companies.jsonl` - Insurance companies (1,068 records, 2.8MB)
- `insurance_distributors.jsonl` - Distributors (57,000 records, 39MB)  
- `insurance_branches.jsonl` - Insurance branches (20 records, 2.1KB)

Each file:
- One JSON object per line
- Records sorted by primary key (company_key, distributor_key, code)
- Keys within each record alphabetically sorted
- Compact format (no pretty-printing)

### 2. Database Build (`scripts/build_db.py`)

The build script:
1. Reads JSONL files
2. Validates with pydantic schemas
3. Creates SQLite tables
4. Sets `journal_mode=DELETE` (no WAL files)
5. Runs `VACUUM` for deterministic output
6. Validates data consistency

Output: `insurance_product_data_sp/data/insurance.db` (~52MB)

### 3. Package Build (`uv build`)

The wheel includes:
- Python code from `insurance_product_data_sp/`
- **Built database** at `insurance_product_data_sp/data/insurance.db`

The sdist includes:
- Python code
- **JSONL source files** (not the built database)
- Build scripts

### 4. CI Workflow

GitHub Actions automatically:
1. Checks out code (includes JSONL files)
2. Installs dependencies
3. Builds database: `uv run python -m scripts.build_db`
4. Runs tests (against built database)
5. Builds package: `uv build`
6. Verifies wheel contains database

See `.github/workflows/checks.yml`

## Why Not a Build Hook?

**Considered**: Hatchling custom build hook to auto-build the database

**Rejected because**:
- Complex: Requires custom hook plugin
- Hidden behavior: Users don't see the build step
- Harder to debug: Build failures buried in wheel creation
- Breaks editable installs: DB wouldn't auto-rebuild

**Chosen approach**: Explicit pre-build step
- ✅ Simple and transparent
- ✅ Easy to debug (see exactly what's happening)
- ✅ Works in CI and locally with same commands
- ✅ Forces maintainers to understand the build process
- ❌ Requires manual step before `uv build`

## For Package Users

**If you install from PyPI**: Just `pip install insurance-product-data-sp`. The wheel includes the pre-built database.

**If you install from sdist**: The database will be built automatically (future enhancement - currently sdist users must build manually).

**If you install in editable mode** (`pip install -e .`):
```bash
# One-time setup
uv run python -m scripts.build_db
pip install -e .
```

The database persists at `insurance_product_data_sp/data/insurance.db` and doesn't need rebuilding unless JSONL files change.

## Verifying Builds

### Check wheel contents:
```bash
unzip -l dist/*.whl | grep insurance.db
# Should show: insurance_product_data_sp/data/insurance.db (~52MB)
```

### Check database was built deterministically:
```bash
uv run python -m scripts.build_db
sha256sum insurance_product_data_sp/data/insurance.db

# Rebuild and compare
rm insurance_product_data_sp/data/insurance.db
uv run python -m scripts.build_db
sha256sum insurance_product_data_sp/data/insurance.db

# Hashes should match
```

### Test installed package:
```bash
# Create fresh venv
python -m venv test_env
source test_env/bin/activate

# Install from wheel
pip install dist/*.whl

# Verify database is accessible
python -c "from insurance_product_data_sp import companies; print(len(companies))"
# Should print: 1068
```

## Troubleshooting

### "Database not found" error when importing

**Cause**: Database wasn't built before package installation

**Fix**:
```bash
uv run python -m scripts.build_db
# Then reinstall: pip install --force-reinstall -e .
```

### Wheel doesn't contain database

**Cause**: Database must exist at `insurance_product_data_sp/data/insurance.db` before running `uv build`

**Fix**:
```bash
uv run python -m scripts.build_db
uv build
```

### Database file is locked

**Cause**: Another process (Python REPL, test run, DB viewer) has the database open

**Fix**: Close all processes using the database, then rebuild

## See Also

- [GENERATING_PRODUCT_POOL.md](GENERATING_PRODUCT_POOL.md) - Adding product data
- [INSURANCE_PUBLIC_DATA_FETCH.md](INSURANCE_PUBLIC_DATA_FETCH.md) - Fetching regulatory data
- [../README.md](../README.md) - Main documentation
