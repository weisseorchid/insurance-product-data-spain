from typing import Any

from sqlmodel import JSON, Column, Field, SQLModel


class DistributorTable(SQLModel, table=True):
    """SQLModel table for insurance distributors."""

    __tablename__ = "distributors"

    distributor_key: str = Field(primary_key=True)
    name: str | None = Field(default=None)
    status: str | None = Field(default=None, index=True)
    mediator_class: str | None = Field(default=None)
    province: str | None = Field(default=None)
    details_json: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))


# Legacy alias for backwards compatibility
DistributorStatus = str
