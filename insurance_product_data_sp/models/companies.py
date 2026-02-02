from typing import Any

from sqlmodel import JSON, Column, Field, SQLModel


class CompanyTable(SQLModel, table=True):
    """SQLModel table for insurance companies."""

    __tablename__ = "companies"

    company_key: str = Field(primary_key=True)
    nif: str | None = Field(default=None, index=True, unique=True)
    denomination: str | None = Field(default=None)
    status: str | None = Field(default=None, index=True)
    province: str | None = Field(default=None)
    details_json: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))


# Legacy alias for backwards compatibility
CompanyStatus = str
