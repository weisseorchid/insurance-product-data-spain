"""SQLModel table definitions for insurance data."""

from insurance_product_data_sp.models.branches import BranchTable
from insurance_product_data_sp.models.companies import CompanyTable
from insurance_product_data_sp.models.distributors import DistributorTable
from insurance_product_data_sp.models.products import ProductTable

__all__ = [
    "BranchTable",
    "CompanyTable",
    "DistributorTable",
    "ProductTable",
]
