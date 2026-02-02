"""Build the SQLite database from JSON sources."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine, select

from insurance_product_data_sp.core.db import BranchDatabase, CompanyDatabase, DistributorDatabase, ProductDatabase
from insurance_product_data_sp.models import BranchTable, CompanyTable, DistributorTable, ProductTable
from insurance_product_data_sp.schemas import (
    InsuranceBranch,
    InsuranceCompanyDetails,
    InsuranceDistributorDetails,
    InsuranceProduct,
)
from scripts.config import BASE_STORAGE_PATH, PACKAGE_DATA_PATH
from scripts.utils.storage import load_json


def _branch_token(value: str) -> str:
    return f"|{value.strip()}|"


def _normalize_branches(branches: str | list[str]) -> str:
    """Convert branch codes to pipe-delimited format for searching."""
    if isinstance(branches, list):
        return "".join(_branch_token(v) for v in branches)
    return _branch_token(branches)


def _check_db_locked(db_path: Path) -> bool:
    """Check if database file is locked by attempting to open it exclusively."""
    if not db_path.exists():
        return False
    try:
        # Try to open the file in exclusive mode to check if it's locked
        with open(db_path, "r+b"):
            return False
    except PermissionError:
        return True
    except Exception:
        # Other exceptions (like file not found) mean it's not locked
        return False


def _prepare_db(db_path: Path, max_retries: int = 3, retry_delay: float = 1.0) -> Session:
    """Prepare database: delete existing, create schema, return session.
    
    Args:
        db_path: Path to the database file
        max_retries: Maximum number of retry attempts if deletion fails
        retry_delay: Delay in seconds between retry attempts
        
    Returns:
        Session: Database session
        
    Raises:
        SystemExit: If database file cannot be deleted after retries
    """
    if db_path.exists():
        # Check if file is locked before attempting deletion
        if _check_db_locked(db_path):
            _handle_locked_database(db_path)
            sys.exit(1)
        
        # Attempt deletion with retries
        for attempt in range(max_retries):
            try:
                db_path.unlink()
                break  # Successfully deleted
            except PermissionError:
                if attempt < max_retries - 1:
                    print(
                        f"Warning: Cannot delete {db_path} (attempt {attempt + 1}/{max_retries}). "
                        f"Retrying in {retry_delay} seconds...",
                        file=sys.stderr,
                    )
                    time.sleep(retry_delay)
                    # Re-check if still locked
                    if _check_db_locked(db_path):
                        _handle_locked_database(db_path)
                        sys.exit(1)
                else:
                    # Final attempt failed
                    _handle_locked_database(db_path)
                    sys.exit(1)
            except Exception as e:
                # Other errors (not permission-related)
                print(
                    f"Error: Failed to delete {db_path}: {e}",
                    file=sys.stderr,
                )
                sys.exit(1)
    
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _handle_locked_database(db_path: Path) -> None:
    """Print helpful error message when database is locked."""
    print("\n" + "=" * 70, file=sys.stderr)
    print("ERROR: Cannot delete database file - file is locked", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print(f"\nDatabase path: {db_path}", file=sys.stderr)
    print("\nThe database file is currently in use by another process.", file=sys.stderr)
    print("\nPossible causes:", file=sys.stderr)
    print("  • Another Python process is using the database", file=sys.stderr)
    print("  • A database viewer/editor (DB Browser, SQLiteStudio, etc.) has it open", file=sys.stderr)
    print("  • SQLite WAL (Write-Ahead Logging) files are still active", file=sys.stderr)
    print("  • File system permissions issue", file=sys.stderr)
    print("\nSolutions:", file=sys.stderr)
    print("  1. Close any applications that might be using the database", file=sys.stderr)
    print("  2. Check for running Python processes: `tasklist | findstr python` (Windows)", file=sys.stderr)
    print("  3. Manually delete the database file and try again", file=sys.stderr)
    print("  4. If using WAL mode, ensure all connections are closed", file=sys.stderr)
    print("\n" + "=" * 70 + "\n", file=sys.stderr)


def _insert_companies(session: Session) -> list[dict]:
    """Insert companies from JSON into database."""
    data = load_json(BASE_STORAGE_PATH / "insurance_companies.json")
    if not isinstance(data, list):
        raise TypeError("companies JSON must be a list")

    for item in data:
        company = InsuranceCompanyDetails.model_validate(item)
        session.add(
            CompanyTable(
                company_key=company.company_key,
                nif=company.nif,
                details_json=company.model_dump(mode="json"),
            )
        )
    return data


def _insert_distributors(session: Session) -> list[dict]:
    """Insert distributors from JSON into database, skipping duplicates."""
    data = load_json(BASE_STORAGE_PATH / "insurance_distributors.json")
    if not isinstance(data, list):
        raise TypeError("distributors JSON must be a list")

    seen_keys: set[str] = set()
    unique: list[dict] = []

    for item in data:
        distributor = InsuranceDistributorDetails.model_validate(item)
        if distributor.distributor_key in seen_keys:
            continue
        seen_keys.add(distributor.distributor_key)
        unique.append(item)
        session.add(
            DistributorTable(
                distributor_key=distributor.distributor_key,
                details_json=distributor.model_dump(mode="json"),
            )
        )
    return unique


def _insert_branches(session: Session) -> list[dict]:
    """Insert branches from JSON into database."""
    data = load_json(BASE_STORAGE_PATH / "insurance_branches.json")
    if not isinstance(data, list):
        raise TypeError("branches JSON must be a list")

    for item in data:
        branch = InsuranceBranch.model_validate(item)
        session.add(
            BranchTable(
                code=branch.code,
                details_json=branch.model_dump(mode="json"),
            )
        )
    return data


def _insert_products(session: Session) -> tuple[set[str], list[dict]]:
    """Insert products from analysis folders into database."""
    products_path = BASE_STORAGE_PATH / "products_by_insurance_company"
    product_ids: set[str] = set()
    product_samples: list[dict] = []

    if not products_path.exists():
        return product_ids, product_samples

    for company_folder in products_path.iterdir():
        if not company_folder.is_dir():
            continue
        analysis_folder = company_folder / "analysis"
        if not analysis_folder.exists():
            continue

        # Get company_key from index.json
        index_path = company_folder / "index.json"
        company_key = "UNKNOWN"
        if index_path.exists():
            index_data = load_json(index_path)
            if isinstance(index_data, list) and index_data:
                company_key = index_data[0].get("company_key", "UNKNOWN")

        for product_file in analysis_folder.glob("*.json"):
            product_data = load_json(product_file)
            product = InsuranceProduct.model_validate(product_data)

            product_ids.add(product.product_id)
            if len(product_samples) < 25:
                product_samples.append(product_data)

            session.add(
                ProductTable(
                    product_id=product.product_id,
                    product_name=product.product_name,
                    company_key=company_key,
                    product_branch=_normalize_branches(product.product_branch),
                    details_json=product.model_dump(mode="json"),
                )
            )

    return product_ids, product_samples


def _validate_keys(session: Session, table, key_field: str, expected: set[str]) -> None:
    """Validate all expected keys exist in database."""
    stmt = select(getattr(table, key_field))
    db_keys = set(session.exec(stmt).all())
    if db_keys != expected:
        missing = expected - db_keys
        extra = db_keys - expected
        raise ValueError(
            f"{table.__tablename__} key mismatch. Missing: {sorted(missing)[:5]}, Extra: {sorted(extra)[:5]}"
        )


def _validate_sample(session: Session, table, model, items: list[dict], key_field: str) -> None:
    """Validate a sample of items have correct details_json."""
    for item in items[:25]:
        key = item.get(key_field)
        if key is None:
            raise ValueError(f"Missing key {key_field} in item")
        stmt = select(table).where(getattr(table, key_field) == key)
        row = session.exec(stmt).first()
        if row is None:
            raise ValueError(f"Missing {table.__tablename__} row for {key_field}={key}")
        expected = model.model_validate(item).model_dump(mode="json")
        if row.details_json != expected:
            raise ValueError(f"Mismatch for {table.__tablename__} {key_field}={key}")


def _validate_store_queries(
    companies: list[dict], distributors: list[dict], branches: list[dict], products: list[dict]
) -> None:
    """Validate store queries return correct data."""
    if companies:
        store = CompanyDatabase()
        sample = companies[0]
        expected = InsuranceCompanyDetails.model_validate(sample).model_dump(mode="json")
        result = store.get(company_key=sample["company_key"])
        if result is None or result.model_dump(mode="json") != expected:
            raise ValueError("Company store query mismatch")

    if distributors:
        store = DistributorDatabase()
        sample = distributors[0]
        expected = InsuranceDistributorDetails.model_validate(sample).model_dump(mode="json")
        result = store.get(distributor_key=sample["distributor_key"])
        if result is None or result.model_dump(mode="json") != expected:
            raise ValueError("Distributor store query mismatch")

    if branches:
        store = BranchDatabase()
        sample = branches[0]
        expected = InsuranceBranch.model_validate(sample).model_dump(mode="json")
        result = store.get_by_code(sample["code"])
        if result is None or result.model_dump(mode="json") != expected:
            raise ValueError("Branch store query mismatch")

    if products:
        store = ProductDatabase()
        sample = products[0]
        expected = InsuranceProduct.model_validate(sample).model_dump(mode="json")
        result = store.get(product_id=sample["product_id"])
        if result is None or result.model_dump(mode="json") != expected:
            raise ValueError("Product store query mismatch")


def build_database() -> Path:
    """Build SQLite database from JSON sources and validate consistency."""
    db_path = PACKAGE_DATA_PATH / "insurance.db"
    session = _prepare_db(db_path)

    try:
        companies = _insert_companies(session)
        distributors = _insert_distributors(session)
        branches = _insert_branches(session)
        product_ids, product_samples = _insert_products(session)

        session.commit()

        # Validate keys
        _validate_keys(session, CompanyTable, "company_key", {c["company_key"] for c in companies})
        _validate_keys(session, DistributorTable, "distributor_key", {d["distributor_key"] for d in distributors})
        _validate_keys(session, BranchTable, "code", {b["code"] for b in branches})
        _validate_keys(session, ProductTable, "product_id", product_ids)

        # Validate samples
        _validate_sample(session, CompanyTable, InsuranceCompanyDetails, companies, "company_key")
        _validate_sample(session, DistributorTable, InsuranceDistributorDetails, distributors, "distributor_key")
        _validate_sample(session, BranchTable, InsuranceBranch, branches, "code")
        if product_samples:
            _validate_sample(session, ProductTable, InsuranceProduct, product_samples, "product_id")
    finally:
        session.close()

    _validate_store_queries(companies, distributors, branches, product_samples)

    return db_path


if __name__ == "__main__":
    path = build_database()
    print(f"Database built and validated at: {path}")
