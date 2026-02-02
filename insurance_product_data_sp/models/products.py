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
    product_name: str = Field(nullable=False)
    company_key: str = Field(foreign_key="companies.company_key", index=True)
    # Note: product_branch stores pipe-delimited tokens (e.g., '|09|' or '|00||01|')
    product_branch: str | None = Field(default=None, index=True)
    details_json: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
