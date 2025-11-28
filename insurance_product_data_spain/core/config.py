"""Configuration settings for the insurance data package."""

from pathlib import Path

# Base paths
BASE_STORAGE_PATH: Path = Path("data")
INSURANCE_COMPANIES_STORAGE_PATH: Path = BASE_STORAGE_PATH / "insurance_companies"
INSURANCE_DISTRIBUTORS_STORAGE_PATH: Path = BASE_STORAGE_PATH / "insurance_distributors"

# Data file paths
INSURANCE_COMPANIES_JSON: Path = BASE_STORAGE_PATH / "insurance_companies.json"
INSURANCE_DISTRIBUTORS_JSON: Path = BASE_STORAGE_PATH / "insurance_distributors.json"

# API settings
DEFAULT_REQUEST_DELAY: float = 0.1  # seconds between requests
DEFAULT_TIMEOUT: int = 30  # seconds for HTTP requests
MAX_RETRIES: int = 3 # number of retries for HTTP requests
