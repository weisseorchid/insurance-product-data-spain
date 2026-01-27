"""Configuration settings for the sync scripts."""

from pathlib import Path

# Base paths - relative to project root
PROJECT_ROOT = Path(__file__).parent.parent
BASE_STORAGE_PATH: Path = PROJECT_ROOT / "data"

# Legacy paths (for folder sync)
INSURANCE_COMPANIES_STORAGE_PATH: Path = BASE_STORAGE_PATH / "products_by_insurance_company"
INSURANCE_DISTRIBUTORS_STORAGE_PATH: Path = BASE_STORAGE_PATH / "insurance_distributors"

# Data file paths - these are the source files that get synced to the package
INSURANCE_COMPANIES_JSON: Path = BASE_STORAGE_PATH / "insurance_companies.json"
INSURANCE_DISTRIBUTORS_JSON: Path = BASE_STORAGE_PATH / "insurance_distributors.json"

# Package data paths - where bundled data lives in the installed package
PACKAGE_DATA_PATH: Path = PROJECT_ROOT / "insurance_product_data_spain" / "data"
PACKAGE_COMPANIES_JSON: Path = PACKAGE_DATA_PATH / "insurance_companies.json"
PACKAGE_DISTRIBUTORS_JSON: Path = PACKAGE_DATA_PATH / "insurance_distributors.json"

# API settings
DEFAULT_REQUEST_DELAY: float = 0.1  # seconds between requests
DEFAULT_TIMEOUT: int = 30  # seconds for HTTP requests
MAX_RETRIES: int = 3  # number of retries for HTTP requests
