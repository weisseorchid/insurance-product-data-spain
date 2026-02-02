from typing import Any

from sqlmodel import JSON, Column, Field, SQLModel


class DistributorTable(SQLModel, table=True):
    """SQLModel table for insurance distributors.

    Stores distributor data with indexed fields for efficient lookups.
    Full distributor details are stored in details_json.
    """

    __tablename__ = "distributors"

    distributor_key: str = Field(primary_key=True)
    details_json: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
