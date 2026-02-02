from typing import Any

from sqlmodel import JSON, Column, Field, SQLModel


class BranchTable(SQLModel, table=True):
    """SQLModel table for insurance branches."""

    __tablename__ = "branches"

    code: str = Field(primary_key=True)
    name_es: str
    name_en: str
    category: str
    details_json: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
