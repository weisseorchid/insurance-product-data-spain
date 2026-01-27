"""Data access layer for insurance data.

Inspired by pycountry's database implementation, but using Pydantic models.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from insurance_product_data_spain.schemas.insurance_branches import InsuranceBranch
from insurance_product_data_spain.schemas.insurance_companies import InsuranceCompanyDetails
from insurance_product_data_spain.schemas.insurance_distributors import InsuranceDistributorDetails

T = TypeVar("T", bound=BaseModel)


def _get_data_path() -> Path:
    """Get the path to bundled data files."""
    return Path(__file__).parent.parent.parent / "data"


class BaseDatabase(Generic[T]):
    """Generic database for Pydantic models with lazy loading and indexing."""

    def __init__(self, filename: str, model: type[T], primary_key: str, extra_indices: list[str] | None = None):
        self.filename = _get_data_path() / filename
        self.model = model
        self.primary_key = primary_key
        self.extra_indices = extra_indices or []

        self._is_loaded = False
        self._load_lock = threading.Lock()
        self._objects: list[T] = []
        self._indices: dict[str, dict[str, T]] = {}

    def _load(self) -> None:
        """Load data from JSON file."""
        if self._is_loaded:
            return

        self._objects = []
        self._indices = {self.primary_key: {}}
        for key in self.extra_indices:
            self._indices[key] = {}

        if not self.filename.exists():
            self._is_loaded = True
            return

        with open(self.filename, encoding="utf-8") as f:
            data = json.load(f)

        for entry in data if isinstance(data, list) else []:
            try:
                obj = self.model.model_validate(entry)
                self._objects.append(obj)
                self._index_object(obj)
            except Exception:
                continue

        self._is_loaded = True

    def _index_object(self, obj: T) -> None:
        """Add object to indices."""
        for key in self._indices:
            value = getattr(obj, key, None)
            if value is not None:
                self._indices[key][value] = obj

    def _ensure_loaded(self) -> None:
        """Ensure data is loaded (thread-safe)."""
        if not self._is_loaded:
            with self._load_lock:
                self._load()

    def __iter__(self) -> Iterator[T]:
        self._ensure_loaded()
        return iter(self._objects)

    def __len__(self) -> int:
        self._ensure_loaded()
        return len(self._objects)

    def __contains__(self, key: str) -> bool:
        self._ensure_loaded()
        return key in self._indices.get(self.primary_key, {})

    def get(self, **kw: Any) -> T | None:
        """Get item by indexed field. Returns None if not found."""
        self._ensure_loaded()
        if len(kw) != 1:
            raise TypeError("Exactly one criterion required")

        field, value = next(iter(kw.items()))
        if field in self._indices and value in self._indices[field]:
            return self._indices[field][value]
        return None

    def lookup(self, **kw: Any) -> T:
        """Get item by indexed field. Raises KeyError if not found."""
        result = self.get(**kw)
        if result is None:
            raise KeyError(f"No {self.model.__name__} found for {kw}")
        return result

    def search(self, **kw: Any) -> list[T]:
        """Search for items matching all criteria."""
        self._ensure_loaded()
        if not kw:
            return list(self._objects)

        return [
            obj for obj in self._objects
            if all(getattr(obj, k, None) == v for k, v in kw.items())
        ]


class CompanyDatabase(BaseDatabase[InsuranceCompanyDetails]):
    """Database for insurance companies with synthetic entity support."""

    def __init__(self):
        super().__init__(
            "insurance_companies.json",
            InsuranceCompanyDetails,
            "company_key",
            extra_indices=["nif"],
        )

    def resolve(self, key: str) -> InsuranceCompanyDetails:
        """Get company by key, returning synthetic entity if not found."""
        result = self.get(company_key=key)
        if result is not None:
            return result
        return InsuranceCompanyDetails.model_validate({
            "clave": key,
            "denomination": f"Entity {key} (Unmapped)",
            "status": "UNKNOWN",
            "is_synthetic": True,
        })


class DistributorDatabase(BaseDatabase[InsuranceDistributorDetails]):
    """Database for insurance distributors."""

    def __init__(self):
        super().__init__(
            "insurance_distributors.json",
            InsuranceDistributorDetails,
            "distributor_key",
        )


class BranchDatabase(BaseDatabase[InsuranceBranch]):
    """Database for insurance branches (ramos)."""

    def __init__(self):
        super().__init__(
            "insurance_branches.json",
            InsuranceBranch,
            "code",
        )
        # Additional index for normalized codes (without leading zero)
        self._normalized_index: dict[str, InsuranceBranch] = {}

    def _load(self) -> None:
        """Load data and build normalized index."""
        super()._load()
        # Build normalized index for codes without leading zeros
        for obj in self._objects:
            normalized = str(int(obj.code)) if obj.code.isdigit() else obj.code
            self._normalized_index[normalized] = obj

    def get_by_code(self, code: str) -> InsuranceBranch | None:
        """Get branch by code, supporting both '01' and '1' formats.

        Args:
            code: Branch code (e.g., "01", "1", "00", "0")

        Returns:
            InsuranceBranch or None if not found
        """
        self._ensure_loaded()
        # Try exact match first
        result = self._indices.get("code", {}).get(code)
        if result is not None:
            return result
        # Try normalized (without leading zero)
        return self._normalized_index.get(code.strip())

    def list_life(self) -> list[InsuranceBranch]:
        """Return all life insurance branches."""
        self._ensure_loaded()
        return [b for b in self._objects if b.is_life]

    def list_non_life(self) -> list[InsuranceBranch]:
        """Return all non-life insurance branches."""
        self._ensure_loaded()
        return [b for b in self._objects if b.is_non_life]


# Singleton instances
_companies: CompanyDatabase | None = None
_distributors: DistributorDatabase | None = None
_branches: BranchDatabase | None = None


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
    def reload() -> None:
        global _companies, _distributors, _branches
        _companies = None
        _distributors = None
        _branches = None


# Public API
Database = _Database
CompanyStore = CompanyDatabase
DistributorStore = DistributorDatabase
BranchStore = BranchDatabase
