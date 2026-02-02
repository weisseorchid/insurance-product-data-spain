from typing import Any

from sqlmodel import JSON, Column, Field, SQLModel


class CompanyTable(SQLModel, table=True):
    """SQLModel table for insurance companies.

    Stores company data with indexed fields for efficient lookups.
    Full company details are stored in details_json.
    """

    __tablename__ = "companies"

    company_key: str = Field(primary_key=True)
    nif: str | None = Field(default=None, index=True, unique=True)
    details_json: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
