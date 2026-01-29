"""
Main script to sync insurance data from the Spanish regulator website.

This script fetches insurance companies and distributors from the Spanish regulator website
and saves the data to JSON files (both in data/ and in the package's bundled data folder).

Run with: uv run python -m scripts.sync_data
"""

import shutil
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from src.core.logging import logger
from src.schemas.insurance_companies import (
    InsuranceCompanyBase,
    InsuranceCompanyDetails,
)
from src.schemas.insurance_distributors import (
    InsuranceDistributorBase,
    InsuranceDistributorDetails,
)
from scripts.config import (
    INSURANCE_COMPANIES_JSON,
    INSURANCE_DISTRIBUTORS_JSON,
    PACKAGE_COMPANIES_JSON,
    PACKAGE_DISTRIBUTORS_JSON,
)
from scripts.fetchers import (
    enrich_insurance_companies,
    enrich_insurance_distributors,
    get_insurance_companies,
    get_insurance_distributors,
)
from scripts.utils.storage import ensure_directory, save_json


def _require_list(data: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(data, list):
        raise TypeError(f"{label} response is not a list: {type(data).__name__}")
    if not data:
        raise ValueError(f"{label} response is empty")
    return data


def _validate_items(
    items: list[dict[str, Any]],
    model: type[BaseModel],
    label: str,
) -> tuple[list[dict[str, Any]], int]:
    validated: list[dict[str, Any]] = []
    invalid_count = 0

    for item in items:
        try:
            validated_item = model.model_validate(item)
            validated.append(validated_item.model_dump(by_alias=False))
        except ValidationError as exc:
            invalid_count += 1
            logger.warning(f"Validation error for {label} item: {exc.errors()}")
            validated.append(item)

    logger.info(
        f"Validated {label}: {len(items) - invalid_count} ok, {invalid_count} invalid"
    )
    return validated, invalid_count


def _count_company_folders(base_path: Path) -> int:
    if not base_path.exists():
        return 0
    return sum(1 for path in base_path.iterdir() if path.is_dir())


def _copy_to_package(source: Path, dest: Path) -> None:
    """Copy data file to package's bundled data folder."""
    ensure_directory(dest.parent)
    shutil.copy2(source, dest)
    logger.info(f"Copied {source.name} to package data: {dest}")


def run() -> int:
    """Run the full sync pipeline."""
    logger.info("Step 1: Fetching insurance companies")
    companies = get_insurance_companies()
    if isinstance(companies, dict) and "error" in companies:
        raise RuntimeError(f"Error response from companies endpoint: {companies['error']}")

    companies_list = _require_list(companies, "companies")
    validated_companies, invalid_companies = _validate_items(
        companies_list,
        InsuranceCompanyBase,
        "companies",
    )

    logger.info("Step 2: Fetching insurance company details")
    enriched_companies = enrich_insurance_companies(validated_companies, verbose=True)
    validated_company_details, invalid_company_details = _validate_items(
        enriched_companies,
        InsuranceCompanyDetails,
        "company details",
    )

    # Save to data/ folder
    save_json(validated_company_details, INSURANCE_COMPANIES_JSON)
    logger.info(f"Saved {len(validated_company_details)} companies to {INSURANCE_COMPANIES_JSON}")

    # Copy to package data folder
    _copy_to_package(INSURANCE_COMPANIES_JSON, PACKAGE_COMPANIES_JSON)

    logger.info("Step 3: Fetching insurance distributors")
    distributors = get_insurance_distributors()
    if isinstance(distributors, dict) and "error" in distributors:
        raise RuntimeError(
            f"Error response from distributors endpoint: {distributors['error']}"
        )

    distributors_list = _require_list(distributors, "distributors")
    validated_distributors, invalid_distributors = _validate_items(
        distributors_list,
        InsuranceDistributorBase,
        "distributors",
    )

    logger.info("Step 4: Fetching insurance distributor details")
    enriched_distributors = enrich_insurance_distributors(validated_distributors, verbose=True)
    validated_distributor_details, invalid_distributor_details = _validate_items(
        enriched_distributors,
        InsuranceDistributorDetails,
        "distributor details",
    )

    # Save to data/ folder
    save_json(validated_distributor_details, INSURANCE_DISTRIBUTORS_JSON)
    logger.info(f"Saved {len(validated_distributor_details)} distributors to {INSURANCE_DISTRIBUTORS_JSON}")

    # Copy to package data folder
    _copy_to_package(INSURANCE_DISTRIBUTORS_JSON, PACKAGE_DISTRIBUTORS_JSON)

    invalid_total_companies = invalid_companies + invalid_company_details
    invalid_total_distributors = invalid_distributors + invalid_distributor_details
    if invalid_total_companies or invalid_total_distributors:
        logger.error(
            "Validation finished with errors: "
            f"{invalid_total_companies} companies, {invalid_total_distributors} distributors"
        )
        return 1

    logger.info("Sync completed successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
