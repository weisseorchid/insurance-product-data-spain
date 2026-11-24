"""Unit tests for store API with fixture database."""

import pytest

from insurance_product_data_sp.core.db import reload_stores
from insurance_product_data_sp.core.engine import DatabaseNotFoundError, init_database, set_database_path
from insurance_product_data_sp.models import BranchTable, CompanyTable, DistributorTable, ProductTable
from insurance_product_data_sp.models.products import ProductBranchAssociation
from insurance_product_data_sp.schemas.insurance_branches import InsuranceBranch
from insurance_product_data_sp.schemas.insurance_companies import InsuranceCompanyDetails
from insurance_product_data_sp.schemas.insurance_distributors import InsuranceDistributorDetails
from insurance_product_data_sp.schemas.insurance_product import InsuranceProduct


@pytest.fixture
def test_db(tmp_path):
    """Create a small fixture database for testing."""
    db_path = tmp_path / "test_insurance.db"

    # Initialize the database schema
    set_database_path(db_path)
    init_database(db_path)

    # Import after setting path to get fresh engine
    from sqlmodel import Session, create_engine

    engine = create_engine(f"sqlite:///{db_path}")

    # Create test data
    with Session(engine) as session:
        # Companies
        companies_data = [
            {
                "company_key": "C0001",
                "nif": "A28000001",
                "details_json": {
                    "clave": "C0001",
                    "denomination": "Test Insurance Company 1",
                    "nif": "A28000001",
                    "status": "Activa",
                    "website": "https://test1.example.com",
                    "is_synthetic": False,
                },
            },
            {
                "company_key": "C0002",
                "nif": "A28000002",
                "details_json": {
                    "clave": "C0002",
                    "denomination": "Test Insurance Company 2",
                    "nif": "A28000002",
                    "status": "Inactiva",
                    "is_synthetic": False,
                },
            },
            {
                "company_key": "C0737",
                "nif": "A28007748",
                "details_json": {
                    "clave": "C0737",
                    "denomination": "Test Insurance Company 737",
                    "nif": "A28007748",
                    "status": "Activa",
                    "is_synthetic": False,
                },
            },
        ]

        for data in companies_data:
            session.add(CompanyTable(**data))

        # Distributors
        distributors_data = [
            {
                "distributor_key": "D0001",
                "details_json": {
                    "clave": "D0001",
                    "name": "Test Distributor 1",
                    "type": "Agente",
                },
            },
            {
                "distributor_key": "D0002",
                "details_json": {
                    "clave": "D0002",
                    "name": "Test Distributor 2",
                    "type": "Corredor",
                },
            },
        ]

        for data in distributors_data:
            session.add(DistributorTable(**data))

        # Branches
        branches_data = [
            {
                "code": "00",
                "details_json": {
                    "code": "00",
                    "name_es": "Vida",
                    "name_en": "Life",
                    "category": "life",
                },
            },
            {
                "code": "01",
                "details_json": {
                    "code": "01",
                    "name_es": "Accidentes",
                    "name_en": "Accidents",
                    "category": "non_life",
                },
            },
            {
                "code": "09",
                "details_json": {
                    "code": "09",
                    "name_es": "Incendio y elementos naturales",
                    "name_en": "Fire and natural forces",
                    "category": "non_life",
                },
            },
            {
                "code": "11",
                "details_json": {
                    "code": "11",
                    "name_es": "Responsabilidad civil",
                    "name_en": "Liability",
                    "category": "non_life",
                },
            },
        ]

        for data in branches_data:
            session.add(BranchTable(**data))

        # Products (including multi-branch product)
        products_data = [
            {
                "product_id": "urn:C0737-01",
                "product_name": "Home Insurance Basic",
                "company_key": "C0737",
                "fetched_at": "2026-01-01T00:00:00Z",
                "details_json": {
                    "product_id": "urn:C0737-01",
                    "company_key": "C0737",
                    "product_name": "Home Insurance Basic",
                    "branches": ["09"],
                    "source_url": "https://example.com/product1.pdf",
                    "document_references": [],
                    "analysis_path": None,
                    "fetched_at": "2026-01-01T00:00:00Z",
                    "metadata": {},
                },
                "branches": ["09"],
            },
            {
                "product_id": "urn:C0737-02",
                "product_name": "Home Insurance Premium",
                "company_key": "C0737",
                "fetched_at": "2026-01-01T00:00:00Z",
                "details_json": {
                    "product_id": "urn:C0737-02",
                    "company_key": "C0737",
                    "product_name": "Home Insurance Premium",
                    "branches": ["09", "11"],
                    "source_url": "https://example.com/product2.pdf",
                    "document_references": [],
                    "analysis_path": None,
                    "fetched_at": "2026-01-01T00:00:00Z",
                    "metadata": {},
                },
                "branches": ["09", "11"],
            },
            {
                "product_id": "urn:C0001-01",
                "product_name": "Life Insurance",
                "company_key": "C0001",
                "fetched_at": "2026-01-01T00:00:00Z",
                "details_json": {
                    "product_id": "urn:C0001-01",
                    "company_key": "C0001",
                    "product_name": "Life Insurance",
                    "branches": ["00"],
                    "source_url": None,
                    "document_references": [],
                    "analysis_path": None,
                    "fetched_at": "2026-01-01T00:00:00Z",
                    "metadata": {},
                },
                "branches": ["00"],
            },
        ]

        for data in products_data:
            branches = data.pop("branches")
            session.add(ProductTable(**data))
            # Add branch associations
            for branch_code in branches:
                session.add(
                    ProductBranchAssociation(
                        product_id=data["product_id"],
                        branch_code=branch_code,
                    )
                )

        session.commit()

    # Reload stores to pick up the test database
    reload_stores()

    yield db_path

    # Cleanup
    set_database_path(None)
    reload_stores()


# =============================================================================
# Company Store Tests
# =============================================================================


def test_companies_get_found(test_db):
    """Test getting a company by key when it exists."""
    from insurance_product_data_sp import companies

    company = companies.get(company_key="C0001")
    assert company is not None
    assert company.company_key == "C0001"
    assert company.denomination == "Test Insurance Company 1"
    assert company.nif == "A28000001"
    assert company.status == "Activa"
    assert company.is_synthetic is False


def test_companies_get_by_nif(test_db):
    """Test getting a company by NIF."""
    from insurance_product_data_sp import companies

    company = companies.get(nif="A28007748")
    assert company is not None
    assert company.company_key == "C0737"


def test_companies_get_not_found(test_db):
    """Test getting a non-existent company returns None."""
    from insurance_product_data_sp import companies

    company = companies.get(company_key="C9999")
    assert company is None


def test_companies_lookup_found(test_db):
    """Test lookup raises KeyError when not found."""
    from insurance_product_data_sp import companies

    company = companies.lookup(company_key="C0001")
    assert company.company_key == "C0001"


def test_companies_lookup_not_found(test_db):
    """Test lookup raises KeyError when not found."""
    from insurance_product_data_sp import companies

    with pytest.raises(KeyError, match="No InsuranceCompanyDetails found"):
        companies.lookup(company_key="C9999")


def test_companies_search(test_db):
    """Test searching companies by indexed field."""
    from insurance_product_data_sp import companies

    # Search by NIF (indexed field)
    result = companies.search(nif="A28000001")
    assert len(result) == 1
    assert result[0].company_key == "C0001"

    # Search by company_key
    result = companies.search(company_key="C0002")
    assert len(result) == 1
    assert result[0].company_key == "C0002"


def test_companies_iter(test_db):
    """Test iterating over all companies."""
    from insurance_product_data_sp import companies

    all_companies = list(companies)
    assert len(all_companies) == 3
    keys = {c.company_key for c in all_companies}
    assert keys == {"C0001", "C0002", "C0737"}


def test_companies_len(test_db):
    """Test getting the count of companies."""
    from insurance_product_data_sp import companies

    assert len(companies) == 3


def test_companies_contains(test_db):
    """Test membership check for companies."""
    from insurance_product_data_sp import companies

    assert "C0001" in companies
    assert "C0737" in companies
    assert "C9999" not in companies


def test_companies_resolve_existing(test_db):
    """Test resolve returns existing company."""
    from insurance_product_data_sp import companies

    company = companies.resolve("C0001")
    assert company.company_key == "C0001"
    assert company.denomination == "Test Insurance Company 1"
    assert company.is_synthetic is False


def test_companies_resolve_synthetic(test_db):
    """Test resolve returns synthetic entity for unknown key."""
    from insurance_product_data_sp import companies

    company = companies.resolve("C9999")
    assert company.company_key == "C9999"
    assert company.denomination == "Entity C9999 (Unmapped)"
    assert company.status == "UNKNOWN"
    assert company.is_synthetic is True


def test_companies_json_roundtrip(test_db):
    """Test that company data round-trips through JSON to pydantic model."""
    from insurance_product_data_sp import companies

    company = companies.get(company_key="C0001")
    assert company is not None

    # Serialize to JSON and back
    json_str = company.model_dump_json()
    parsed = InsuranceCompanyDetails.model_validate_json(json_str)

    assert parsed.company_key == company.company_key
    assert parsed.denomination == company.denomination
    assert parsed.nif == company.nif
    assert parsed.status == company.status


# =============================================================================
# Distributor Store Tests
# =============================================================================


def test_distributors_get_found(test_db):
    """Test getting a distributor by key."""
    from insurance_product_data_sp import distributors

    distributor = distributors.get(distributor_key="D0001")
    assert distributor is not None
    assert distributor.distributor_key == "D0001"
    assert distributor.name == "Test Distributor 1"


def test_distributors_get_not_found(test_db):
    """Test getting a non-existent distributor returns None."""
    from insurance_product_data_sp import distributors

    distributor = distributors.get(distributor_key="D9999")
    assert distributor is None


def test_distributors_lookup_not_found(test_db):
    """Test lookup raises KeyError when not found."""
    from insurance_product_data_sp import distributors

    with pytest.raises(KeyError):
        distributors.lookup(distributor_key="D9999")


def test_distributors_iter(test_db):
    """Test iterating over all distributors."""
    from insurance_product_data_sp import distributors

    all_distributors = list(distributors)
    assert len(all_distributors) == 2


def test_distributors_len(test_db):
    """Test getting the count of distributors."""
    from insurance_product_data_sp import distributors

    assert len(distributors) == 2


def test_distributors_contains(test_db):
    """Test membership check for distributors."""
    from insurance_product_data_sp import distributors

    assert "D0001" in distributors
    assert "D9999" not in distributors


def test_distributors_json_roundtrip(test_db):
    """Test that distributor data round-trips through JSON."""
    from insurance_product_data_sp import distributors

    distributor = distributors.get(distributor_key="D0001")
    assert distributor is not None

    json_str = distributor.model_dump_json()
    parsed = InsuranceDistributorDetails.model_validate_json(json_str)

    assert parsed.distributor_key == distributor.distributor_key
    assert parsed.name == distributor.name


# =============================================================================
# Branch Store Tests
# =============================================================================


def test_branches_get_found(test_db):
    """Test getting a branch by code."""
    from insurance_product_data_sp import branches

    branch = branches.get(code="09")
    assert branch is not None
    assert branch.code == "09"
    assert branch.name_es == "Incendio y elementos naturales"
    assert branch.is_non_life is True


def test_branches_get_not_found(test_db):
    """Test getting a non-existent branch returns None."""
    from insurance_product_data_sp import branches

    branch = branches.get(code="99")
    assert branch is None


def test_branches_get_by_code_exact_match(test_db):
    """Test get_by_code with exact match."""
    from insurance_product_data_sp import branches

    branch = branches.get_by_code("09")
    assert branch is not None
    assert branch.code == "09"


def test_branches_get_by_code_normalization_1_to_01(test_db):
    """Test get_by_code normalizes '1' to '01'."""
    from insurance_product_data_sp import branches

    branch = branches.get_by_code("1")
    assert branch is not None
    assert branch.code == "01"


def test_branches_get_by_code_normalization_01_to_1(test_db):
    """Test get_by_code tries removing leading zero (not found in this dataset)."""
    from insurance_product_data_sp import branches

    # We have '01' in the database, so '01' should find it
    branch = branches.get_by_code("01")
    assert branch is not None
    assert branch.code == "01"


def test_branches_get_by_code_unknown(test_db):
    """Test get_by_code with unknown code."""
    from insurance_product_data_sp import branches

    branch = branches.get_by_code("99")
    assert branch is None


def test_branches_list_life(test_db):
    """Test listing life insurance branches."""
    from insurance_product_data_sp import branches

    life_branches = branches.list_life()
    assert len(life_branches) == 1
    assert life_branches[0].code == "00"
    assert life_branches[0].is_life is True


def test_branches_list_non_life(test_db):
    """Test listing non-life insurance branches."""
    from insurance_product_data_sp import branches

    non_life = branches.list_non_life()
    assert len(non_life) == 3
    codes = {b.code for b in non_life}
    assert codes == {"01", "09", "11"}
    assert all(b.is_non_life for b in non_life)


def test_branches_iter(test_db):
    """Test iterating over all branches."""
    from insurance_product_data_sp import branches

    all_branches = list(branches)
    assert len(all_branches) == 4


def test_branches_len(test_db):
    """Test getting the count of branches."""
    from insurance_product_data_sp import branches

    assert len(branches) == 4


def test_branches_contains(test_db):
    """Test membership check for branches."""
    from insurance_product_data_sp import branches

    assert "09" in branches
    assert "99" not in branches


def test_branches_json_roundtrip(test_db):
    """Test that branch data round-trips through JSON."""
    from insurance_product_data_sp import branches

    branch = branches.get(code="09")
    assert branch is not None

    json_str = branch.model_dump_json()
    parsed = InsuranceBranch.model_validate_json(json_str)

    assert parsed.code == branch.code
    assert parsed.name_es == branch.name_es
    assert parsed.category == branch.category


# =============================================================================
# Product Store Tests
# =============================================================================


def test_products_get_found(test_db):
    """Test getting a product by ID."""
    from insurance_product_data_sp import products

    product = products.get(product_id="urn:C0737-01")
    assert product is not None
    assert product.product_id == "urn:C0737-01"
    assert product.product_name == "Home Insurance Basic"


def test_products_get_not_found(test_db):
    """Test getting a non-existent product returns None."""
    from insurance_product_data_sp import products

    product = products.get(product_id="urn:C9999-99")
    assert product is None


def test_products_lookup_not_found(test_db):
    """Test lookup raises KeyError when not found."""
    from insurance_product_data_sp import products

    with pytest.raises(KeyError):
        products.lookup(product_id="urn:C9999-99")


def test_products_search_by_company(test_db):
    """Test searching products by company."""
    from insurance_product_data_sp import products

    company_products = products.search_by_company("C0737")
    assert len(company_products) == 2
    assert all(p.product_id.startswith("urn:C0737") for p in company_products)

    other_products = products.search_by_company("C0001")
    assert len(other_products) == 1
    assert other_products[0].product_id == "urn:C0001-01"


def test_products_search_by_branch_single(test_db):
    """Test searching products by branch (single-branch product)."""
    from insurance_product_data_sp import products

    branch_09_products = products.search_by_branch("09")
    assert len(branch_09_products) == 2
    ids = {p.product_id for p in branch_09_products}
    assert ids == {"urn:C0737-01", "urn:C0737-02"}


def test_products_search_by_branch_multi_branch(test_db):
    """Test searching products by branch (finds multi-branch products)."""
    from insurance_product_data_sp import products

    # Branch 11 is in the multi-branch product only
    branch_11_products = products.search_by_branch("11")
    assert len(branch_11_products) == 1
    assert branch_11_products[0].product_id == "urn:C0737-02"


def test_products_search_by_branch_no_false_positive(test_db):
    """Test that search_by_branch doesn't match '1' to '11'."""
    from insurance_product_data_sp import products

    # Branch '01' should not match products with '11'
    branch_01_products = products.search_by_branch("01")
    assert len(branch_01_products) == 0

    # Branch '1' should not match products with '11'
    branch_1_products = products.search_by_branch("1")
    assert len(branch_1_products) == 0


def test_products_iter(test_db):
    """Test iterating over all products."""
    from insurance_product_data_sp import products

    all_products = list(products)
    assert len(all_products) == 3


def test_products_len(test_db):
    """Test getting the count of products."""
    from insurance_product_data_sp import products

    assert len(products) == 3


def test_products_contains(test_db):
    """Test membership check for products."""
    from insurance_product_data_sp import products

    assert "urn:C0737-01" in products
    assert "urn:C9999-99" not in products


def test_products_json_roundtrip(test_db):
    """Test that product data round-trips through JSON."""
    from insurance_product_data_sp import products

    product = products.get(product_id="urn:C0737-01")
    assert product is not None

    json_str = product.model_dump_json()
    parsed = InsuranceProduct.model_validate_json(json_str)

    assert parsed.product_id == product.product_id
    assert parsed.product_name == product.product_name


def test_products_schema_v1_fields(test_db):
    """Test that products have all schema v1 fields."""
    from insurance_product_data_sp import products

    product = products.get(product_id="urn:C0737-01")
    assert product is not None
    assert product.product_id == "urn:C0737-01"
    assert product.company_key == "C0737"
    assert product.product_name == "Home Insurance Basic"
    assert product.branches == ["09"]
    assert product.fetched_at is not None
    assert isinstance(product.document_references, list)
    assert isinstance(product.metadata, dict)


def test_product_branch_association(test_db):
    """Test that product-branch associations work correctly."""
    from insurance_product_data_sp import products

    # Test multi-branch product
    multi_branch = products.get(product_id="urn:C0737-02")
    assert multi_branch is not None
    assert set(multi_branch.branches) == {"09", "11"}

    # Verify we can search by both branches
    branch_09_products = products.search_by_branch("09")
    assert len(branch_09_products) == 2
    ids = {p.product_id for p in branch_09_products}
    assert ids == {"urn:C0737-01", "urn:C0737-02"}

    branch_11_products = products.search_by_branch("11")
    assert len(branch_11_products) == 1
    assert branch_11_products[0].product_id == "urn:C0737-02"


# =============================================================================
# Error Handling Tests
# =============================================================================


def test_database_not_found_error(tmp_path):
    """Test that DatabaseNotFoundError is raised when database is missing."""
    # Reset to default path
    set_database_path(None)
    reload_stores()

    # Set to a non-existent path
    missing_db = tmp_path / "missing.db"
    set_database_path(missing_db)
    reload_stores()

    from insurance_product_data_sp import companies

    with pytest.raises(DatabaseNotFoundError) as exc_info:
        # This should trigger database access
        _ = len(companies)

    assert str(missing_db) in str(exc_info.value)
    assert "not found" in str(exc_info.value).lower()

    # Cleanup
    set_database_path(None)
    reload_stores()
