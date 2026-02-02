"""SQLModel table definitions for insurance data."""

from insurance_product_data_sp.models.branches import BranchTable
from insurance_product_data_sp.models.companies import CompanyStatus, CompanyTable
from insurance_product_data_sp.models.distributors import DistributorStatus, DistributorTable
from insurance_product_data_sp.models.products import (
    ProductCoverageTable,
    ProductExclusionTable,
    ProductLimitTable,
    ProductSourceDocumentTable,
    ProductTable,
)

__all__ = [
    "BranchTable",
    "CompanyStatus",
    "CompanyTable",
    "DistributorStatus",
    "DistributorTable",
    "ProductCoverageTable",
    "ProductExclusionTable",
    "ProductLimitTable",
    "ProductSourceDocumentTable",
    "ProductTable",
]
