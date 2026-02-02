"""Insurance Product Data Spain - A pycountry-style library for Spanish insurance data.

This package provides easy access to Spanish insurance market data including:
- Insurance companies (aseguradoras)
- Insurance distributors (mediadores)
- Insurance branches/lines of business (ramos)
- Insurance products with AI-extracted analysis

Example usage:
    >>> from insurance_product_data_sp import companies, distributors, products
    >>>
    >>> # Get a company by key
    >>> company = companies.get(company_key="C0001")
    >>> print(company.denomination)

    >>> # Search for active companies
    >>> active = companies.search(status="Activa")
    >>> print(f"Found {len(active)} active companies")

    >>> # Iterate over all distributors
    >>> for distributor in distributors:
    ...     print(distributor.name)

    >>> # Search for products by company
    >>> company_products = products.search_by_company("C0737")
    >>> print(f"Found {len(company_products)} products")
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from insurance_product_data_sp.__version__ import __version__
from insurance_product_data_sp.schemas.insurance_branches import InsuranceBranch
from insurance_product_data_sp.schemas.insurance_companies import (
    InsuranceCompanyBase,
    InsuranceCompanyDetails,
)
from insurance_product_data_sp.schemas.insurance_distributors import (
    AgencyContract,
    InsuranceDistributorBase,
    InsuranceDistributorDetails,
)
from insurance_product_data_sp.schemas.insurance_product import InsuranceProduct

if TYPE_CHECKING:
    from insurance_product_data_sp.core.db import (
        BranchStore,
        CompanyStore,
        DistributorStore,
        ProductStore,
    )

# Lazy-loaded module-level data stores
_companies: CompanyStore | None = None
_distributors: DistributorStore | None = None
_branches: BranchStore | None = None
_products: ProductStore | None = None


def __getattr__(name: str):
    """Lazy load data stores on first access."""
    global _companies, _distributors, _branches, _products

    # Lazy import to avoid circular imports
    from insurance_product_data_sp.core.db import Database

    if name == "companies":
        if _companies is None:
            _companies = Database.companies()
        return _companies

    if name == "distributors":
        if _distributors is None:
            _distributors = Database.distributors()
        return _distributors

    if name == "branches":
        if _branches is None:
            _branches = Database.branches()
        return _branches

    if name == "products":
        if _products is None:
            _products = Database.products()
        return _products

    # Lazy load store classes
    if name in ("CompanyStore", "DistributorStore", "BranchStore", "ProductStore", "Database"):
        from insurance_product_data_sp.core import db

        return getattr(db, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Version
    "__version__",
    # Data stores
    "companies",
    "distributors",
    "branches",
    "products",
    # Store classes
    "CompanyStore",
    "DistributorStore",
    "BranchStore",
    "ProductStore",
    "Database",
    # Schema models
    "InsuranceCompanyBase",
    "InsuranceCompanyDetails",
    "InsuranceDistributorBase",
    "InsuranceDistributorDetails",
    "InsuranceBranch",
    "InsuranceProduct",
    "AgencyContract",
]
