"""Insurance Product Data Spain - A pycountry-style library for Spanish insurance data.

This package provides easy access to Spanish insurance market data including:
- Insurance companies (aseguradoras)
- Insurance distributors (mediadores)
- Insurance branches/lines of business (ramos)

Example usage:
    >>> from insurance_product_data_spain import companies, distributors
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
"""

from insurance_product_data_spain.__version__ import __version__
from insurance_product_data_spain.core.db import (
    BranchStore,
    CompanyStore,
    Database,
    DistributorStore,
)
from insurance_product_data_spain.schemas.insurance_companies import (
    InsuranceCompanyBase,
    InsuranceCompanyDetails,
)
from insurance_product_data_spain.schemas.insurance_distributors import (
    AgencyContract,
    InsuranceDistributorBase,
    InsuranceDistributorDetails,
)
from insurance_product_data_spain.schemas.insurance_branches import InsuranceBranch

# Lazy-loaded module-level data stores
_companies: CompanyStore | None = None
_distributors: DistributorStore | None = None
_branches: BranchStore | None = None


def __getattr__(name: str):
    """Lazy load data stores on first access."""
    global _companies, _distributors, _branches

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

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Version
    "__version__",
    # Data stores
    "companies",
    "distributors",
    "branches",
    # Store classes
    "CompanyStore",
    "DistributorStore",
    "BranchStore",
    "Database",
    # Schema models
    "InsuranceCompanyBase",
    "InsuranceCompanyDetails",
    "InsuranceDistributorBase",
    "InsuranceDistributorDetails",
    "InsuranceBranch",
    "AgencyContract",
]
