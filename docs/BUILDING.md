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
- `insurance_companies.jsonl` - Insurance companies (1,068 records, ~2.8MB)
- `insurance_distributors.jsonl` - Distributors (~57,000 records, ~39MB)
- `insurance_branches.jsonl` - Insurance branches (20 records, ~2KB)

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
4. Sets `PRAGMA journal_mode=DELETE` (no WAL files, deterministic output)
5. Inserts data
6. Validates data consistency
7. Runs `VACUUM` to compact and ensure deterministic output

Output: `insurance_product_data_sp/data/insurance.db` (~52MB)

**Deterministic Build**: The combination of `journal_mode=DELETE` and `VACUUM` ensures that the same JSONL input always produces byte-identical database files, making builds reproducible.

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

## Document Cache

The package **does not require** source PDFs or markdown files at build/install time. The database is built from:
- JSONL source data (companies, distributors, branches)
- Product analysis JSON files (in `data/products_by_insurance_company/*/analysis/`)

PDFs and markdown are stored in a local cache (`.cache/insurance-docs/`) for development but are not needed for package builds. The cache is gitignored and content-addressed by SHA256.

## CI Checks

The repository runs automated checks on every PR and push to main:

### Running Checks Locally

```bash
# All pre-commit checks (fast)
uv run pre-commit run --all-files

# Individual checks
uv run python scripts/ci/check_repo_hygiene.py
uv run python scripts/ci/check_data_integrity.py
uv lock --check
uv run python -m scripts.build_db
uv build --wheel
uv run python scripts/ci/check_package.py
uv run pytest -m 'not live' -v
```

### What Each Check Does

1. **Repository Hygiene** (`check_repo_hygiene.py`)
   - No tracked files matching `.env`, `*.db`, `*.pdf`, `.cache/`, etc.
   - No files over 1MB except allowlisted data files
   
2. **Secrets** (gitleaks in CI)
   - Scans for committed secrets/credentials
   
3. **Lockfile** (`uv lock --check`)
   - Ensures `uv.lock` is in sync with `pyproject.toml`
   
4. **Data Integrity** (`check_data_integrity.py`)
   - All JSONL files are valid JSON
   - Required fields present
   - No duplicate keys (except 16 known distributor duplicates)
   - Sorted by primary key
   
5. **Package** (`check_package.py`)
   - Wheel contains `insurance.db` (>10MB)
   - Install works in clean venv
   - Data counts: companies > 1000, distributors > 50000
   
6. **Code Quality** (pre-commit)
   - Ruff formatter and linter
   - Ty type checker
   - Standard file checks (YAML, TOML, merge conflicts, large files)

7. **Tests** (pytest)
   - Full test suite with coverage
   - Database built fresh from JSONL
   - Multi-version Python matrix (3.10, 3.11, 3.12)

## For Package Users

**If you install from PyPI**: Just `pip install insurance-product-data-sp`. The wheel includes the pre-built database.

**If you install from source**:
```bash
git clone https://github.com/weisseorchid/insurance-product-data-spain
cd insurance-product-data-spain
uv run python -m scripts.build_db  # Build database first
pip install -e .
```

**If you install from sdist**: The sdist includes JSONL sources but not the built database. You'll need to build it manually (same as source install above).

## Development Workflow

### Initial Setup

```bash
# Clone and install
git clone https://github.com/weisseorchid/insurance-product-data-spain
cd insurance-product-data-spain
uv sync --all-extras

# Build database (required for running code/tests)
uv run python -m scripts.build_db
```

### Making Changes

**If you modify JSONL data**:
```bash
# Rebuild database
uv run python -m scripts.build_db

# Run tests to verify
uv run pytest -m 'not live' -v
```

**If you modify Python code only**:
No need to rebuild the database unless tests fail.

### Before Committing

```bash
# Run pre-commit checks
uv run pre-commit run --all-files

# Run tests
uv run pytest -m 'not live' -v
```

## Release Process

1. Update version in `insurance_product_data_sp/__version__.py`
2. Build database: `uv run python -m scripts.build_db`
3. Build package: `uv build`
4. Verify wheel: `unzip -l dist/*.whl | grep insurance.db`
5. Test wheel in clean environment:
   ```bash
   python -m venv test-env
   source test-env/bin/activate  # or test-env\Scripts\activate on Windows
   pip install dist/*.whl
   python -c "from insurance_product_data_sp import companies, distributors; print(len(companies), len(distributors))"
   ```
6. Push to PyPI: `uv publish` (after configuring credentials)

## Troubleshooting

### Database file locked error

If you see "Cannot delete database file - file is locked":
- Close any database viewers (DB Browser, SQLiteStudio, etc.)
- Check for running Python processes
- Manually delete `insurance_product_data_sp/data/insurance.db` and retry

### Wheel doesn't contain database

Verify build steps:
```bash
# 1. Database exists
ls -lh insurance_product_data_sp/data/insurance.db

# 2. Build wheel
uv build

# 3. Check contents
unzip -l dist/*.whl | grep insurance.db
```

If database is missing from wheel, check `pyproject.toml` has:
```toml
[tool.hatch.build.targets.wheel]
artifacts = [
    "insurance_product_data_sp/data/*.db",
]
```

### Tests fail after building database

The built database might be corrupt or incomplete. Try:
```bash
# Remove database and rebuild
rm insurance_product_data_sp/data/insurance.db
uv run python -m scripts.build_db

# Check database was created
ls -lh insurance_product_data_sp/data/insurance.db

# Run tests
uv run pytest -m 'not live' -v
```
