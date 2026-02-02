"""Build the SQLite database from JSON sources and validate consistency."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine, select

from insurance_product_data_sp.core.db import BranchDatabase, CompanyDatabase, DistributorDatabase, ProductDatabase
from insurance_product_data_sp.models import (
    BranchTable,
    CompanyTable,
    DistributorTable,
    ProductCoverageTable,
    ProductExclusionTable,
    ProductLimitTable,
    ProductSourceDocumentTable,
    ProductTable,
)
from insurance_product_data_sp.schemas import (
    InsuranceBranch,
    InsuranceCompanyDetails,
    InsuranceDistributorDetails,
    InsuranceProduct,
)
from scripts.config import BASE_STORAGE_PATH, PACKAGE_DATA_PATH
from scripts.utils.storage import load_json

SAMPLE_SIZE = 25


@dataclass(frozen=True)
class ProductInsertContext:
    company_key: str
    product_ids: set[str]
    product_samples: list[dict]


def _branch_token(value: str) -> str:
    return f"|{value.strip()}|"


def _normalize_branches(branches: str | list[str]) -> str:
    if isinstance(branches, list):
        tokens = [_branch_token(value) for value in branches]
        return "".join(tokens)
    return _branch_token(branches)


def _build_engine(db_path: Path):
    return create_engine(f"sqlite:///{db_path}")


def _prepare_db(db_path: Path):
    """Prepare database and return a context manager for the session."""
    if db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = _build_engine(db_path)
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _load_company_key(index_path: Path) -> str | None:
    index_data = load_json(index_path)
    if isinstance(index_data, list) and index_data:
        return index_data[0].get("company_key")
    return None


def _insert_companies(session: Session) -> list[dict]:
    companies_data = load_json(BASE_STORAGE_PATH / "insurance_companies.json")
    if not isinstance(companies_data, list):
        raise TypeError("companies JSON must be a list")

    for item in companies_data:
        company = InsuranceCompanyDetails.model_validate(item)
        session.add(
            CompanyTable(
                company_key=company.company_key,
                nif=company.nif,
                denomination=company.denomination,
                status=company.status,
                province=company.province,
                details_json=company.model_dump(mode="json"),
            )
        )
    return companies_data


def _insert_distributors(session: Session) -> list[dict]:
    distributors_data = load_json(BASE_STORAGE_PATH / "insurance_distributors.json")
    if not isinstance(distributors_data, list):
        raise TypeError("distributors JSON must be a list")

    seen_keys: set[str] = set()
    unique_distributors: list[dict] = []

    for item in distributors_data:
        distributor = InsuranceDistributorDetails.model_validate(item)
        if distributor.distributor_key in seen_keys:
            continue  # Skip duplicates
        seen_keys.add(distributor.distributor_key)
        unique_distributors.append(item)
        session.add(
            DistributorTable(
                distributor_key=distributor.distributor_key,
                name=distributor.name,
                status=distributor.status,
                mediator_class=distributor.mediator_class,
                province=distributor.province,
                details_json=distributor.model_dump(mode="json"),
            )
        )
    return unique_distributors


def _insert_branches(session: Session) -> list[dict]:
    branches_data = load_json(BASE_STORAGE_PATH / "insurance_branches.json")
    if not isinstance(branches_data, list):
        raise TypeError("branches JSON must be a list")

    for item in branches_data:
        branch = InsuranceBranch.model_validate(item)
        session.add(
            BranchTable(
                code=branch.code,
                name_es=branch.name_es,
                name_en=branch.name_en,
                category=branch.category,
                details_json=branch.model_dump(mode="json"),
            )
        )
    return branches_data


def _insert_products(session: Session) -> ProductInsertContext:
    products_path = BASE_STORAGE_PATH / "products_by_insurance_company"
    product_ids: set[str] = set()
    product_samples: list[dict] = []
    company_key: str | None = None

    if not products_path.exists():
        return ProductInsertContext(
            company_key="UNKNOWN",
            product_ids=product_ids,
            product_samples=product_samples,
        )

    for company_folder in products_path.iterdir():
        if not company_folder.is_dir():
            continue
        analysis_folder = company_folder / "analysis"
        if not analysis_folder.exists():
            continue

        index_path = company_folder / "index.json"
        if index_path.exists():
            company_key = _load_company_key(index_path) or "UNKNOWN"
        else:
            company_key = "UNKNOWN"

        for product_file in analysis_folder.glob("*.json"):
            product_data = load_json(product_file)
            product = InsuranceProduct.model_validate(product_data)

            # Extract basic fields
            product_type = None
            target_audience = None
            description_es = None
            description_en = None
            key_benefits: list[str] = []

            # Extract contract terms
            contract_duration = None
            renewal_type = None
            cancellation_notice_days_policyholder = None
            cancellation_notice_days_insurer = None
            payment_method = None
            payment_frequency: list[str] = []

            # Extract geographic coverage
            primary_territory = None

            # Extract obligations
            claim_notification_deadline_days = None

            # Extract pricing
            base_premium = None

            # Extract counts
            coverage_count = None
            exclusion_count = None

            if product.analysis:
                # Extract from product_summary
                if product.analysis.product_summary:
                    product_type = product.analysis.product_summary.product_type
                    target_audience = product.analysis.product_summary.target_audience
                    description_es = product.analysis.product_summary.description_es
                    description_en = product.analysis.product_summary.description_en
                    key_benefits = product.analysis.product_summary.key_benefits or []

                # Extract from contract_terms
                if product.analysis.contract_terms:
                    contract_duration = product.analysis.contract_terms.duration
                    renewal_type = product.analysis.contract_terms.renewal_type
                    cancellation_notice_days_policyholder = (
                        product.analysis.contract_terms.cancellation_notice_days_policyholder
                    )
                    cancellation_notice_days_insurer = product.analysis.contract_terms.cancellation_notice_days_insurer
                    payment_method = product.analysis.contract_terms.payment_method
                    payment_frequency = product.analysis.contract_terms.payment_frequency or []

                # Extract from geographic_coverage
                if product.analysis.geographic_coverage:
                    primary_territory = product.analysis.geographic_coverage.primary_territory

                # Extract from obligations
                if product.analysis.obligations:
                    claim_notification_deadline_days = product.analysis.obligations.claim_notification_deadline_days

                # Extract from pricing
                if product.analysis.pricing:
                    base_premium = product.analysis.pricing.base_premium

                # Count coverages and exclusions
                coverage_count = len(product.analysis.coverages) if product.analysis.coverages else 0
                exclusion_count = len(product.analysis.exclusions) if product.analysis.exclusions else 0

            product_ids.add(product.product_id)
            if len(product_samples) < SAMPLE_SIZE:
                product_samples.append(product_data)

            # Create product record
            product_record = ProductTable(
                product_id=product.product_id,
                product_name=product.product_name,
                company_key=company_key,
                product_branch=_normalize_branches(product.product_branch),
                product_type=product_type,
                target_audience=target_audience,
                description_es=description_es,
                description_en=description_en,
                key_benefits=key_benefits,
                contract_duration=contract_duration,
                renewal_type=renewal_type,
                cancellation_notice_days_policyholder=cancellation_notice_days_policyholder,
                cancellation_notice_days_insurer=cancellation_notice_days_insurer,
                payment_method=payment_method,
                payment_frequency=payment_frequency,
                primary_territory=primary_territory,
                claim_notification_deadline_days=claim_notification_deadline_days,
                base_premium=base_premium,
                coverage_count=coverage_count,
                exclusion_count=exclusion_count,
                details_json=product.model_dump(mode="json"),
            )
            session.add(product_record)

            # Create related records if analysis exists
            if product.analysis:
                # Create coverage records
                if product.analysis.coverages:
                    for coverage in product.analysis.coverages:
                        # Handle enum value (CoverageCategory)
                        category_value = (
                            coverage.category.value if hasattr(coverage.category, "value") else str(coverage.category)
                        )
                        session.add(
                            ProductCoverageTable(
                                product_id=product.product_id,
                                name=coverage.name,
                                category=category_value,
                                description=coverage.description,
                                capital_or_limit=coverage.capital_or_limit,
                                waiting_period_days=coverage.waiting_period_days,
                                covered_events=coverage.covered_events or [],
                                benefits=coverage.benefits or [],
                                conditions=coverage.conditions or [],
                            )
                        )

                # Create exclusion records
                if product.analysis.exclusions:
                    for exclusion in product.analysis.exclusions:
                        session.add(
                            ProductExclusionTable(
                                product_id=product.product_id,
                                description=exclusion.description,
                                category=exclusion.category,
                                legal_reference=exclusion.legal_reference,
                            )
                        )

                # Create limit records
                if product.analysis.limits_and_restrictions:
                    for limit in product.analysis.limits_and_restrictions:
                        session.add(
                            ProductLimitTable(
                                product_id=product.product_id,
                                coverage_name=limit.coverage_name,
                                limit_type=limit.limit_type,
                                limit_value=limit.limit_value,
                                conditions=limit.conditions,
                            )
                        )

                # Create source document records
                if product.analysis.source_documents:
                    for doc in product.analysis.source_documents:
                        # Handle enum value (DocumentType)
                        doc_type_value = (
                            doc.document_type.value if hasattr(doc.document_type, "value") else str(doc.document_type)
                        )
                        session.add(
                            ProductSourceDocumentTable(
                                product_id=product.product_id,
                                filename=doc.filename,
                                document_type=doc_type_value,
                                extraction_confidence=doc.extraction_confidence,
                            )
                        )

    return ProductInsertContext(
        company_key=company_key or "UNKNOWN",
        product_ids=product_ids,
        product_samples=product_samples,
    )


def _validate_keys(session: Session, table, key_field: str, expected_keys: set[str]) -> None:
    stmt = select(getattr(table, key_field))
    db_keys = set(session.exec(stmt).all())
    if db_keys != expected_keys:
        missing = expected_keys - db_keys
        extra = db_keys - expected_keys
        raise ValueError(
            f"{table.__tablename__} key mismatch. Missing: {sorted(missing)[:5]}, Extra: {sorted(extra)[:5]}"
        )


def _validate_sample(
    session: Session,
    table,
    model,
    items: list[dict],
    key_field: str,
    sample_size: int = SAMPLE_SIZE,
) -> None:
    for item in items[:sample_size]:
        key = item.get(key_field)
        if key is None:
            raise ValueError(f"Missing key {key_field} in item: {item}")
        stmt = select(table).where(getattr(table, key_field) == key)
        row = session.exec(stmt).first()
        if row is None:
            raise ValueError(f"Missing {table.__tablename__} row for {key_field}={key}")
        expected = model.model_validate(item).model_dump(mode="json")
        if row.details_json != expected:
            raise ValueError(f"Mismatch for {table.__tablename__} {key_field}={key}")


def validate_database(
    session: Session,
    companies: list[dict],
    distributors: list[dict],
    branches: list[dict],
    product_ids: set[str],
    product_samples: list[dict],
) -> None:
    """Validate that SQLite data matches JSON sources."""
    _validate_keys(session, CompanyTable, "company_key", {c["company_key"] for c in companies})
    _validate_keys(
        session,
        DistributorTable,
        "distributor_key",
        {d["distributor_key"] for d in distributors},
    )
    _validate_keys(session, BranchTable, "code", {b["code"] for b in branches})
    _validate_keys(session, ProductTable, "product_id", product_ids)

    _validate_sample(session, CompanyTable, InsuranceCompanyDetails, companies, "company_key")
    _validate_sample(session, DistributorTable, InsuranceDistributorDetails, distributors, "distributor_key")
    _validate_sample(session, BranchTable, InsuranceBranch, branches, "code")
    if product_samples:
        _validate_sample(session, ProductTable, InsuranceProduct, product_samples, "product_id")


def validate_store_queries(
    companies: list[dict],
    distributors: list[dict],
    branches: list[dict],
    product_samples: list[dict],
) -> None:
    """Validate store queries return the same validated data."""
    company_store = CompanyDatabase()
    distributor_store = DistributorDatabase()
    branch_store = BranchDatabase()
    product_store = ProductDatabase()

    if companies:
        sample = companies[0]
        expected = InsuranceCompanyDetails.model_validate(sample).model_dump(mode="json")
        result = company_store.get(company_key=sample["company_key"])
        if result is None or result.model_dump(mode="json") != expected:
            raise ValueError("Company store query mismatch")

    if distributors:
        sample = distributors[0]
        expected = InsuranceDistributorDetails.model_validate(sample).model_dump(mode="json")
        result = distributor_store.get(distributor_key=sample["distributor_key"])
        if result is None or result.model_dump(mode="json") != expected:
            raise ValueError("Distributor store query mismatch")

    if branches:
        sample = branches[0]
        expected = InsuranceBranch.model_validate(sample).model_dump(mode="json")
        result = branch_store.get_by_code(sample["code"])
        if result is None or result.model_dump(mode="json") != expected:
            raise ValueError("Branch store query mismatch")

    if product_samples:
        sample = product_samples[0]
        expected = InsuranceProduct.model_validate(sample).model_dump(mode="json")
        result = product_store.get(product_id=sample["product_id"])
        if result is None or result.model_dump(mode="json") != expected:
            raise ValueError("Product store query mismatch")


def build_database() -> Path:
    """Compile JSON files into a SQLite database and validate consistency."""
    db_path = PACKAGE_DATA_PATH / "insurance.db"
    session = _prepare_db(db_path)
    try:
        companies = _insert_companies(session)
        distributors = _insert_distributors(session)
        branches = _insert_branches(session)
        product_context = _insert_products(session)

        session.commit()

        validate_database(
            session=session,
            companies=companies,
            distributors=distributors,
            branches=branches,
            product_ids=product_context.product_ids,
            product_samples=product_context.product_samples,
        )
    finally:
        session.close()

    validate_store_queries(
        companies=companies,
        distributors=distributors,
        branches=branches,
        product_samples=product_context.product_samples,
    )

    return db_path


if __name__ == "__main__":
    path = build_database()
    print(f"Database built and validated at: {path}")
