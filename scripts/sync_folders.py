"""Script to sync insurance company folder structure.

This creates folders for each insurance company based on data/insurance_companies.jsonl.
This is a legacy script that may be useful for organizing raw data.

Run with: uv run python -m scripts.sync_folders
"""

from pathlib import Path

from insurance_product_data_sp.core.logging import logger
from scripts.config import PRODUCTS_STORAGE_PATH
from scripts.utils.companies import company_display_name, company_folder_name, load_companies
from scripts.utils.storage import ensure_directory


def sync_insurance_company_folders(
    json_file_path: Path | str | None = None,
    base_folder_path: Path | str | None = None,
) -> None:
    """
    Iterate through insurance companies in the JSON file and create folders
    for each company if they don't exist.

    Args:
        json_file_path: Path to the companies file (.jsonl, or legacy .json). Defaults to data/insurance_companies.jsonl.
        base_folder_path: Base path where insurance company folders should be created. Defaults to config value.
    """
    # Use defaults from config if not provided
    base_path = Path(base_folder_path) if base_folder_path else PRODUCTS_STORAGE_PATH

    companies = load_companies(json_file_path)

    # Ensure base folder exists
    ensure_directory(base_path)

    # Iterate through each company and create folders for each company
    for company in companies:
        if not company_display_name(company):
            logger.warning(f"Company {company.get('company_key') or company.get('clave')} has no name, skipping...")
            continue

        folder_name = company_folder_name(company)

        folder_path = base_path / folder_name

        if not folder_path.exists():
            folder_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created folder: {folder_path}")
        else:
            logger.info(f"Folder already exists: {folder_path}")


if __name__ == "__main__":
    sync_insurance_company_folders()
