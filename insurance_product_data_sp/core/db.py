"""Data access layer for insurance data using SQLModel.

Provides a SQLModel-backed database implementation for insurance data,
with lazy loading and efficient querying via SQLite.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Generic, TypeVar

from pydantic import BaseModel
from sqlmodel import select

from insurance_product_data_sp.core.engine import get_session
from insurance_product_data_sp.models import BranchTable, CompanyTable, DistributorTable, ProductTable
from insurance_product_data_sp.schemas.insurance_branches import InsuranceBranch
from insurance_product_data_sp.schemas.insurance_companies import InsuranceCompanyDetails
from insurance_product_data_sp.schemas.insurance_distributors import InsuranceDistributorDetails
from insurance_product_data_sp.schemas.insurance_product import InsuranceProduct

T = TypeVar("T", bound=BaseModel)
TableT = TypeVar("TableT")


class SQLModelDatabase(Generic[T, TableT]):
    """SQLModel-backed database for Pydantic models."""

    def __init__(self, table: type[TableT], model: type[T], primary_key: str):
        self._table = table
        self._model = model
        self._pk = primary_key

    def _to_model(self, row: TableT) -> T:
        """Convert table row to Pydantic model."""
        return self._model.model_validate(row.details_json)  # type: ignore[attr-defined]

    def get(self, **kw: Any) -> T | None:
        """Get item by indexed field. Returns None if not found."""
        if len(kw) != 1:
            raise TypeError("Exactly one criterion required")

        field, value = next(iter(kw.items()))
        with get_session() as session:
            stmt = select(self._table).where(getattr(self._table, field) == value)
            row = session.exec(stmt).first()
            return self._to_model(row) if row else None

    def lookup(self, **kw: Any) -> T:
        """Get item by indexed field. Raises KeyError if not found."""
        result = self.get(**kw)
        if result is None:
            raise KeyError(f"No {self._model.__name__} found for {kw}")
        return result

    def search(self, **kw: Any) -> list[T]:
        """Search for items matching all criteria."""
        with get_session() as session:
            stmt = select(self._table)
            for field, value in kw.items():
                stmt = stmt.where(getattr(self._table, field) == value)
            rows = session.exec(stmt).all()
            return [self._to_model(row) for row in rows]

    def __iter__(self) -> Iterator[T]:
        with get_session() as session:
            stmt = select(self._table)
            for row in session.exec(stmt):
                yield self._to_model(row)

    def __len__(self) -> int:
        with get_session() as session:
            stmt = select(self._table)
            return len(session.exec(stmt).all())

    def __contains__(self, key: str) -> bool:
        return self.get(**{self._pk: key}) is not None


class CompanyDatabase(SQLModelDatabase[InsuranceCompanyDetails, CompanyTable]):
    """Database for insurance companies with synthetic entity support."""

    def __init__(self):
        super().__init__(CompanyTable, InsuranceCompanyDetails, "company_key")

    def resolve(self, key: str) -> InsuranceCompanyDetails:
        """Get company by key, returning synthetic entity if not found."""
        result = self.get(company_key=key)
        if result is not None:
            return result
        return InsuranceCompanyDetails.model_validate(
            {
                "clave": key,
                "denomination": f"Entity {key} (Unmapped)",
                "status": "UNKNOWN",
                "is_synthetic": True,
            }
        )


class DistributorDatabase(SQLModelDatabase[InsuranceDistributorDetails, DistributorTable]):
    """Database for insurance distributors."""

    def __init__(self):
        super().__init__(DistributorTable, InsuranceDistributorDetails, "distributor_key")


class BranchDatabase(SQLModelDatabase[InsuranceBranch, BranchTable]):
    """Database for insurance branches (ramos)."""

    def __init__(self):
        super().__init__(BranchTable, InsuranceBranch, "code")

    def get_by_code(self, code: str) -> InsuranceBranch | None:
        """Get branch by code, supporting both '01' and '1' formats."""
        # Try exact match first
        result = self.get(code=code)
        if result is not None:
            return result
        # Try with leading zero
        if code.isdigit() and len(code) == 1:
            return self.get(code=f"0{code}")
        # Try without leading zero
        if code.isdigit() and code.startswith("0") and len(code) == 2:
            return self.get(code=code[1])
        return None

    def list_life(self) -> list[InsuranceBranch]:
        """Return all life insurance branches."""
        return [b for b in self if b.is_life]

    def list_non_life(self) -> list[InsuranceBranch]:
        """Return all non-life insurance branches."""
        return [b for b in self if b.is_non_life]


class ProductDatabase(SQLModelDatabase[InsuranceProduct, ProductTable]):
    """Database for insurance products."""

    def __init__(self):
        super().__init__(ProductTable, InsuranceProduct, "product_id")

    def search_by_company(self, company_key: str) -> list[InsuranceProduct]:
        """Get all products for a specific company."""
        return self.search(company_key=company_key)

    def search_by_branch(self, branch_code: str) -> list[InsuranceProduct]:
        """Get all products for a specific branch."""
        with get_session() as session:
            token = f"|{branch_code.strip()}|"
            stmt = select(self._table).where(
                self._table.product_branch.contains(token)  # type: ignore[union-attr]
            )
            rows = session.exec(stmt).all()
            return [self._to_model(row) for row in rows]


# Module-level singletons
_companies: CompanyDatabase | None = None
_distributors: DistributorDatabase | None = None
_branches: BranchDatabase | None = None
_products: ProductDatabase | None = None


def get_companies() -> CompanyDatabase:
    """Get the companies store singleton."""
    global _companies
    if _companies is None:
        _companies = CompanyDatabase()
    return _companies


def get_distributors() -> DistributorDatabase:
    """Get the distributors store singleton."""
    global _distributors
    if _distributors is None:
        _distributors = DistributorDatabase()
    return _distributors


def get_branches() -> BranchDatabase:
    """Get the branches store singleton."""
    global _branches
    if _branches is None:
        _branches = BranchDatabase()
    return _branches


def get_products() -> ProductDatabase:
    """Get the products store singleton."""
    global _products
    if _products is None:
        _products = ProductDatabase()
    return _products


def reload_stores() -> None:
    """Clear all store singletons (for testing or reloading data)."""
    global _companies, _distributors, _branches, _products
    _companies = None
    _distributors = None
    _branches = None
    _products = None


# Backwards-compatible aliases
Database = type(
    "Database",
    (),
    {
        "companies": staticmethod(get_companies),
        "distributors": staticmethod(get_distributors),
        "branches": staticmethod(get_branches),
        "products": staticmethod(get_products),
        "reload": staticmethod(reload_stores),
    },
)()

CompanyStore = CompanyDatabase
DistributorStore = DistributorDatabase
BranchStore = BranchDatabase
ProductStore = ProductDatabase
