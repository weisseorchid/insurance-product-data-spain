import json
from pathlib import Path

from src.core.logging import logger
from src.insurance_data_spain.constants.storage_routes import BASE_STORAGE_PATH, INSURANCE_COMPANIES_STORAGE_PATH
from src.insurance_data_spain.utils.text_transformations import text_to_snake_case


def sync_insurance_company_folders(
    json_file_path: str = BASE_STORAGE_PATH + "/insurance_companies.json",
    base_folder_path: str = INSURANCE_COMPANIES_STORAGE_PATH
) -> None:
    """
    Iterate through insurance companies in the JSON file and create folders
    for each company if they don't exist.

    Args:
        json_file_path: Path to the insurance companies JSON file
        base_folder_path: Base path where insurance company folders should be created
    """
    # Read the JSON file and load the companies
    with open(json_file_path, encoding='utf-8') as f:
        companies = json.load(f)

    # Ensure base folder exists
    base_path = Path(base_folder_path)
    base_path.mkdir(parents=True, exist_ok=True)

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
