"""Quick smoke test for the package."""

from insurance_product_data_sp import branches, companies, distributors, products


def test_companies_smoke():
    """Test that companies data is available and queryable."""
    assert len(companies) > 0, "Companies store should not be empty"
    c = companies.get(company_key="C0737")
    assert c is not None, "Should be able to get company C0737"
    assert c.denomination, "Company should have a denomination"


def test_distributors_smoke():
    """Test that distributors data is available."""
    assert len(distributors) > 0, "Distributors store should not be empty"


def test_branches_smoke():
    """Test that branches data is available and queryable."""
    assert len(branches) > 0, "Branches store should not be empty"
    life = branches.list_life()
    assert len(life) > 0, "Should have life branches"
    non_life = branches.list_non_life()
    assert len(non_life) > 0, "Should have non-life branches"


def test_products_smoke():
    """Test that products data is available and queryable."""
    assert len(products) > 0, "Products store should not be empty"
    company_prods = products.search_by_company("C0737")
    assert len(company_prods) > 0, "Should find products for C0737"
