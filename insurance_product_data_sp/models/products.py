from __future__ import annotations

from typing import Any

from sqlmodel import JSON, Column, Field, SQLModel


class ProductTable(SQLModel, table=True):
    """SQLModel table for insurance products.

    Stores product data with indexed fields for efficient lookups.
    Full product details are stored in details_json.
    """

    __tablename__ = "products"

    product_id: str = Field(primary_key=True)
    product_name: str = Field(nullable=False, index=True)
    company_key: str = Field(foreign_key="companies.company_key", index=True)
    fetched_at: str | None = Field(default=None, index=True)
    details_json: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))


class ProductBranchAssociation(SQLModel, table=True):
    """Many-to-many association table linking products to insurance branches."""

    __tablename__ = "product_branch_associations"

    product_id: str = Field(foreign_key="products.product_id", primary_key=True)
    branch_code: str = Field(foreign_key="branches.code", primary_key=True)
