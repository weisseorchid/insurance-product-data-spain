"""Core modules for data access and logging."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from insurance_product_data_sp.core.db import (
        BranchStore,
        CompanyStore,
        Database,
        DistributorStore,
        ProductStore,
    )


def __getattr__(name: str):
    """Lazy load to avoid circular imports."""
    if name in ("Database", "CompanyStore", "DistributorStore", "BranchStore", "ProductStore"):
        from insurance_product_data_sp.core import db

        return getattr(db, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Database",
    "CompanyStore",
    "DistributorStore",
    "BranchStore",
    "ProductStore",
]
