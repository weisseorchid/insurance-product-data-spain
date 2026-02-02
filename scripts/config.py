"""Configuration settings for the sync scripts."""

from pathlib import Path

# Base paths
PROJECT_ROOT = Path(__file__).parent.parent
BASE_STORAGE_PATH: Path = PROJECT_ROOT / "data"

# Product data storage
PRODUCTS_STORAGE_PATH: Path = BASE_STORAGE_PATH / "products_by_insurance_company"

# Data file paths
INSURANCE_COMPANIES_JSON: Path = BASE_STORAGE_PATH / "insurance_companies.json"
INSURANCE_DISTRIBUTORS_JSON: Path = BASE_STORAGE_PATH / "insurance_distributors.json"

# Package data paths
PACKAGE_DATA_PATH: Path = PROJECT_ROOT / "insurance_product_data_sp" / "data"
PACKAGE_COMPANIES_JSON: Path = PACKAGE_DATA_PATH / "insurance_companies.json"
PACKAGE_DISTRIBUTORS_JSON: Path = PACKAGE_DATA_PATH / "insurance_distributors.json"

# API settings
DEFAULT_TIMEOUT: int = 30
MAX_RETRIES: int = 3
