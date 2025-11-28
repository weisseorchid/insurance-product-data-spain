from pathlib import Path

from insurance_product_data_spain.core.config import (
    INSURANCE_COMPANIES_JSON,
    INSURANCE_COMPANIES_STORAGE_PATH,
)
from insurance_product_data_spain.core.logging import logger
from insurance_product_data_spain.core.storage import ensure_directory, load_json
from insurance_product_data_spain.utils.text_transformations import text_to_snake_case


def sync_insurance_company_folders(
    json_file_path: Path | str | None = None,
    base_folder_path: Path | str | None = None,
) -> None:
    """
    Iterate through insurance companies in the JSON file and create folders
    for each company if they don't exist.

    Args:
        json_file_path: Path to the insurance companies JSON file. Defaults to config value.
        base_folder_path: Base path where insurance company folders should be created. Defaults to config value.
    """
    # Use defaults from config if not provided
    json_path = Path(json_file_path) if json_file_path else INSURANCE_COMPANIES_JSON
    base_path = Path(base_folder_path) if base_folder_path else INSURANCE_COMPANIES_STORAGE_PATH

    # Read the JSON file and load the companies
    companies = load_json(json_path)

    # Ensure base folder exists
    ensure_directory(base_path)

    # Iterate through each company and create folders for each company
    for company in companies:
        company_name = company.get('descripcion', '')

        if not company_name:
            logger.warning(f"Company {company.get('clave')} has no name, skipping...")
            continue

        folder_name = text_to_snake_case(company_name)

        folder_path = base_path / folder_name

        if not folder_path.exists():
            folder_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created folder: {folder_path}")
        else:
            logger.info(f"Folder already exists: {folder_path}")


"""
# Example usage:
if __name__ == "__main__":
    sync_insurance_company_folders()
"""
