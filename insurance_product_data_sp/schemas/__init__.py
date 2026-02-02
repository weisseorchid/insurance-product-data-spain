"""Insurance product data schemas.

This module exports all Pydantic models for insurance data structures.
"""

from .common import CustomerService
from .insurance_branches import InsuranceBranch
from .insurance_companies import InsuranceCompanyBase, InsuranceCompanyDetails
from .insurance_distributors import InsuranceDistributorBase, InsuranceDistributorDetails
from .insurance_product import (
    ContractTerms,
    # Supporting schemas
    Coverage,
    # Enums
    CoverageCategory,
    DocumentType,
    Exclusion,
    GeographicCoverage,
    # Main product schema
    InsuranceProduct,
    LimitOrRestriction,
    PolicyholderObligations,
    PricingInfo,
    ProductAnalysis,
    ProductSummary,
    SourceDocument,
)

__all__ = [
    # Common
    "CustomerService",
    # Insurance branches
    "InsuranceBranch",
    # Insurance companies
    "InsuranceCompanyBase",
    "InsuranceCompanyDetails",
    # Insurance distributors
    "InsuranceDistributorBase",
    "InsuranceDistributorDetails",
    # Insurance product - Enums
    "CoverageCategory",
    "DocumentType",
    # Insurance product - Supporting schemas
    "Coverage",
    "ContractTerms",
    "Exclusion",
    "GeographicCoverage",
    "LimitOrRestriction",
    "PolicyholderObligations",
    "PricingInfo",
    "ProductAnalysis",
    "ProductSummary",
    "SourceDocument",
    # Insurance product - Main schema
    "InsuranceProduct",
]
