"""Setup products_by_insurer folder structure for example companies.

This script creates the structured products_by_insurer folder structure
and extracts data from insurance_companies.json.

Note: This works alongside the existing insurance_companies/ folder structure.
- insurance_companies/ : For raw data gathering and processing files
- products_by_insurer/ : For structured, queryable products (raw/processed/structured)

Run with: uv run python -m scripts.setup_products
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.config import INSURANCE_COMPANIES_JSON, PRODUCTS_BY_INSURER_STORAGE_PATH
from insurance_product_data_spain.core.logging import logger
from scripts.utils.storage import ensure_directory, load_json, save_json
from scripts.utils.text_transformations import text_to_snake_case


def get_company_folder_name(company_key: str, company_name: str) -> str:
    """Generate folder name for a company: {key}_{name_snake_case}."""
    name_snake = text_to_snake_case(company_name)
    return f"{company_key.lower()}_{name_snake}"


def extract_products(company_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract insurance_branches (products) from company data."""
    return company_data.get("insurance_branches", [])


def extract_company_info(company_data: dict[str, Any]) -> dict[str, Any]:
    """Extract essential company metadata."""
    return {
        "company_key": company_data.get("company_key"),
        "denomination": company_data.get("denomination"),
        "nif": company_data.get("nif"),
        "status": company_data.get("status"),
        "website": company_data.get("website"),
        "email": company_data.get("email"),
        "authorization_date": company_data.get("authorization_date"),
        "country_of_origin": company_data.get("country_of_origin"),
        "scope": company_data.get("scope"),
    }


def normalize_product(product: dict[str, Any], company_key: str, company_name: str) -> dict[str, Any]:
    """Normalize a product for structured layer."""
    ramo = product.get("ramo", "")
    ramo_parts = ramo.split("/", 1) if "/" in ramo else ("", ramo)

    # Categorize product type
    ramo_code = ramo_parts[0].strip() if ramo_parts[0] else ""
    product_type = "vida" if ramo_code in ["0"] else "no_vida"

    return {
        "company_key": company_key,
        "company_name": company_name,
        "product_code": product.get("codigo", ""),
        "ramo_code": ramo_code,
        "ramo_name": ramo_parts[1].strip() if len(ramo_parts) > 1 else ramo,
        "modalidad": product.get("modalidad", ""),
        "status": product.get("estado", ""),
        "authorized_since": product.get("fechaAlta", ""),
        "normalized_ramo": text_to_snake_case(ramo_parts[1] if len(ramo_parts) > 1 else ramo),
        "product_type": product_type,
    }


def build_company_index(company_data: dict[str, Any], products: list[dict[str, Any]]) -> dict[str, Any]:
    """Build index for a single company."""
    active_products = [p for p in products if p.get("estado") == "Activo"]

    return {
        "company_key": company_data.get("company_key"),
        "company_name": company_data.get("denomination"),
        "product_count": len(products),
        "active_products": len(active_products),
        "product_codes": [p.get("codigo", "") for p in products if p.get("codigo")],
        "ramos": [p.get("ramo", "") for p in products],
        "last_updated": datetime.now(timezone.utc).isoformat() + "Z",
    }


def setup_company_structure(
    company_data: dict[str, Any],
    base_path: Path | None = None,
) -> Path:
    """Setup folder structure and files for a single company.

    Args:
        company_data: Full company data from insurance_companies.json
        base_path: Base path for products_by_insurer (defaults to config)

    Returns:
        Path to the company folder
    """
    if base_path is None:
        base_path = PRODUCTS_BY_INSURER_STORAGE_PATH

    company_key = company_data.get("company_key", "")
    company_name = company_data.get("denomination", "")

    if not company_key or not company_name:
        raise ValueError(f"Company data missing key or name: {company_data}")

    # Create folder structure
    folder_name = get_company_folder_name(company_key, company_name)
    company_path = base_path / folder_name

    raw_path = company_path / "raw"
    processed_path = company_path / "processed"
    structured_path = company_path / "structured"

    ensure_directory(raw_path)
    ensure_directory(processed_path)
    ensure_directory(structured_path)

    # Extract data
    products = extract_products(company_data)
    company_info = extract_company_info(company_data)

    # Save raw layer
    save_json(company_data, raw_path / "company_details.json")
    save_json(
        {
            "fetched_at": datetime.now(timezone.utc).isoformat() + "Z",
            "source_url": f"https://rrpp.dgsfp.mineco.es/Aseguradora/GetAseguradora/?clave={company_key}",
            "version": "1.0",
            "company_key": company_key,
        },
        raw_path / "metadata.json",
    )

    # Save processed layer
    save_json(products, processed_path / "products.json")
    save_json(company_info, processed_path / "company_info.json")

    # Save structured layer
    normalized_products = [
        normalize_product(p, company_key, company_name) for p in products
    ]
    save_json(normalized_products, structured_path / "products.json")

    company_index = build_company_index(company_data, products)
    save_json(company_index, structured_path / "index.json")

    logger.info(f"Created structure for {company_key}: {company_path}")

    return company_path


def setup_example_companies(
    company_keys: list[str],
    json_file_path: Path | str | None = None,
    base_path: Path | str | None = None,
) -> dict[str, Path]:
    """Setup structure for example companies.

    Args:
        company_keys: List of company keys (e.g., ["C0001", "C0058"])
        json_file_path: Path to insurance_companies.json (defaults to config)
        base_path: Base path for products_by_insurer (defaults to config)

    Returns:
        Dictionary mapping company_key -> folder_path
    """
    json_path = Path(json_file_path) if json_file_path else INSURANCE_COMPANIES_JSON
    base = Path(base_path) if base_path else PRODUCTS_BY_INSURER_STORAGE_PATH

    # Load companies
    companies_data = load_json(json_path)
    if not isinstance(companies_data, list):
        raise ValueError(f"Expected list of companies, got {type(companies_data).__name__}")

    # Create index mapping
    companies_by_key = {c.get("company_key"): c for c in companies_data if c.get("company_key")}

    # Ensure base directory exists
    ensure_directory(base)

    # Process each company
    created_folders: dict[str, Path] = {}

    for company_key in company_keys:
        if company_key not in companies_by_key:
            logger.warning(f"Company {company_key} not found in data, skipping...")
            continue

        try:
            company_data = companies_by_key[company_key]
            folder_path = setup_company_structure(company_data, base)
            created_folders[company_key] = folder_path
        except Exception as e:
            logger.error(f"Error setting up {company_key}: {e}")
            continue

    # Create/update master index
    update_master_index(base, created_folders, companies_by_key)

    logger.info(f"Setup complete for {len(created_folders)} companies")
    return created_folders


def update_master_index(
    base_path: Path,
    created_folders: dict[str, Path],
    companies_by_key: dict[str, dict[str, Any]],
) -> None:
    """Create or update master index.json."""
    index_path = base_path / "index.json"

    # Load existing index if it exists
    existing_index: dict[str, Any] = {}
    if index_path.exists():
        try:
            existing_index = load_json(index_path)
        except Exception as e:
            logger.warning(f"Could not load existing index: {e}")

    # Update with new companies
    companies_list = existing_index.get("companies", [])
    companies_by_key_existing = {c["company_key"]: c for c in companies_list if c.get("company_key")}

    for company_key, folder_path in created_folders.items():
        company_data = companies_by_key.get(company_key, {})
        folder_name = folder_path.name

        # Get product count from structured index
        structured_index_path = folder_path / "structured" / "index.json"
        product_count = 0
        if structured_index_path.exists():
            try:
                company_index = load_json(structured_index_path)
                product_count = company_index.get("product_count", 0)
            except Exception:
                pass

        company_entry = {
            "company_key": company_key,
            "company_name": company_data.get("denomination", ""),
            "folder_name": folder_name,
            "status": company_data.get("status", ""),
            "product_count": product_count,
            "last_processed": datetime.now(timezone.utc).isoformat() + "Z",
        }

        companies_by_key_existing[company_key] = company_entry

    # Build final index
    master_index = {
        "total_companies": len(companies_by_key_existing),
        "last_updated": datetime.now(timezone.utc).isoformat() + "Z",
        "companies": list(companies_by_key_existing.values()),
    }

    save_json(master_index, index_path)
    logger.info(f"Updated master index: {index_path}")


if __name__ == "__main__":
    # Example: Setup structure for a few companies
    example_companies = ["C0001", "C0058", "C0031"]  # ASEGRUP, MAPFRE, CAJA DE SEGUROS REUNIDOS

    logger.info(f"Setting up structure for example companies: {example_companies}")
    folders = setup_example_companies(example_companies)

    logger.info(f"Created folders: {list(folders.keys())}")
