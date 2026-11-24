"""One-time migration script to convert existing JSON files to JSONL format.

Run with: uv run python -m scripts.migrate_to_jsonl
"""


from insurance_product_data_sp.core.logging import logger
from scripts.config import (
    BASE_STORAGE_PATH,
    INSURANCE_BRANCHES_JSONL,
    INSURANCE_COMPANIES_JSONL,
    INSURANCE_DISTRIBUTORS_JSONL,
)
from scripts.utils.jsonl import save_jsonl
from scripts.utils.storage import load_json


def migrate_json_to_jsonl():
    """Convert existing JSON files to JSONL format with stable sorting."""

    # Companies
    logger.info("Converting companies to JSONL...")
    companies_json = BASE_STORAGE_PATH / "insurance_companies.json"
    if companies_json.exists():
        companies = load_json(companies_json)
        if isinstance(companies, list):
            save_jsonl(companies, INSURANCE_COMPANIES_JSONL, sort_key=lambda x: x.get("company_key", ""))
            logger.info(f"✓ Saved {len(companies)} companies to {INSURANCE_COMPANIES_JSONL}")
        else:
            logger.error("companies.json is not a list")
    else:
        logger.warning(f"File not found: {companies_json}")

    # Distributors
    logger.info("Converting distributors to JSONL...")
    distributors_json = BASE_STORAGE_PATH / "insurance_distributors.json"
    if distributors_json.exists():
        distributors = load_json(distributors_json)
        if isinstance(distributors, list):
            save_jsonl(distributors, INSURANCE_DISTRIBUTORS_JSONL, sort_key=lambda x: x.get("distributor_key", ""))
            logger.info(f"✓ Saved {len(distributors)} distributors to {INSURANCE_DISTRIBUTORS_JSONL}")
        else:
            logger.error("distributors.json is not a list")
    else:
        logger.warning(f"File not found: {distributors_json}")

    # Branches
    logger.info("Converting branches to JSONL...")
    branches_json = BASE_STORAGE_PATH / "insurance_branches.json"
    if branches_json.exists():
        branches = load_json(branches_json)
        if isinstance(branches, list):
            save_jsonl(branches, INSURANCE_BRANCHES_JSONL, sort_key=lambda x: x.get("code", ""))
            logger.info(f"✓ Saved {len(branches)} branches to {INSURANCE_BRANCHES_JSONL}")
        else:
            logger.error("branches.json is not a list")
    else:
        logger.warning(f"File not found: {branches_json}")

    logger.info("Migration complete!")
    logger.info(f"JSONL files created in: {BASE_STORAGE_PATH}")
    logger.info("Original JSON files are preserved for now")


if __name__ == "__main__":
    migrate_json_to_jsonl()
