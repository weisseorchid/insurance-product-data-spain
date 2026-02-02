from typing import Any

from sqlmodel import JSON, Column, Field, SQLModel


class BranchTable(SQLModel, table=True):
    """SQLModel table for insurance branches.

    Stores branch data with code as primary key.
    Full branch details are stored in details_json.
    """

    __tablename__ = "branches"

    code: str = Field(primary_key=True)
    details_json: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
