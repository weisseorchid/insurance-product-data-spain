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

    def __init__(
        self,
        table: type[TableT],
        model: type[T],
        primary_key: str,
        extra_indices: list[str] | None = None,
    ):
        self._table = table
        self._model = model
        self._pk = primary_key
        self._indices = extra_indices or []

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
        super().__init__(
            CompanyTable,
            InsuranceCompanyDetails,
            "company_key",
            extra_indices=["nif"],
        )

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
        super().__init__(
            DistributorTable,
            InsuranceDistributorDetails,
            "distributor_key",
        )


class BranchDatabase(SQLModelDatabase[InsuranceBranch, BranchTable]):
    """Database for insurance branches (ramos)."""

    def __init__(self):
        super().__init__(
            BranchTable,
            InsuranceBranch,
            "code",
        )
        # Additional index for normalized codes (without leading zero)
        self._normalized_index: dict[str, InsuranceBranch] | None = None

    def _build_normalized_index(self) -> dict[str, InsuranceBranch]:
        """Build normalized index for codes without leading zeros."""
        if self._normalized_index is None:
            self._normalized_index = {}
            for branch in self:
                normalized = str(int(branch.code)) if branch.code.isdigit() else branch.code
                self._normalized_index[normalized] = branch
        return self._normalized_index

    def get_by_code(self, code: str) -> InsuranceBranch | None:
        """Get branch by code, supporting both '01' and '1' formats.

        Args:
            code: Branch code (e.g., "01", "1", "00", "0")

        Returns:
            InsuranceBranch or None if not found
        """
        # Try exact match first
        result = self.get(code=code)
        if result is not None:
            return result
        # Try normalized (without leading zero)
        normalized_index = self._build_normalized_index()
        return normalized_index.get(code.strip())

    def list_life(self) -> list[InsuranceBranch]:
        """Return all life insurance branches."""
        return [b for b in self if b.is_life]

    def list_non_life(self) -> list[InsuranceBranch]:
        """Return all non-life insurance branches."""
        return [b for b in self if b.is_non_life]


class ProductDatabase(SQLModelDatabase[InsuranceProduct, ProductTable]):
    """Database for insurance products."""

    def __init__(self):
        super().__init__(
            ProductTable,
            InsuranceProduct,
            "product_id",
            extra_indices=["company_key"],
        )

    def search_by_company(self, company_key: str) -> list[InsuranceProduct]:
        """Get all products for a specific company."""
        return self.search(company_key=company_key)

    def search_by_type(self, product_type: str) -> list[InsuranceProduct]:
        """Get all products of a specific type."""
        return self.search(product_type=product_type)

    def search_by_branch(self, branch_code: str) -> list[InsuranceProduct]:
        """Get all products for a specific branch.

        Note: branch_code is stored as pipe-delimited tokens (e.g., '|09|' or '|00||01|')
        """
        with get_session() as session:
            token = f"|{branch_code.strip()}|"
            stmt = select(self._table).where(
                self._table.product_branch.contains(token)  # type: ignore[union-attr]
            )
            rows = session.exec(stmt).all()
            return [self._to_model(row) for row in rows]


# Singleton instances
_companies: CompanyDatabase | None = None
_distributors: DistributorDatabase | None = None
_branches: BranchDatabase | None = None
_products: ProductDatabase | None = None


class _Database:
    """Factory for database singletons."""

    @staticmethod
    def companies() -> CompanyDatabase:
        global _companies
        if _companies is None:
            _companies = CompanyDatabase()
        return _companies

    @staticmethod
    def distributors() -> DistributorDatabase:
        global _distributors
        if _distributors is None:
            _distributors = DistributorDatabase()
        return _distributors

    @staticmethod
    def branches() -> BranchDatabase:
        global _branches
        if _branches is None:
            _branches = BranchDatabase()
        return _branches

    @staticmethod
    def products() -> ProductDatabase:
        global _products
        if _products is None:
            _products = ProductDatabase()
        return _products

    @staticmethod
    def reload() -> None:
        global _companies, _distributors, _branches, _products
        _companies = None
        _distributors = None
        _branches = None
        _products = None


# Public API
Database = _Database
CompanyStore = CompanyDatabase
DistributorStore = DistributorDatabase
BranchStore = BranchDatabase
ProductStore = ProductDatabase
