from __future__ import annotations

from typing import Any

from sqlmodel import JSON, Column, Field, SQLModel


class ProductTable(SQLModel, table=True):
    """SQLModel table for insurance products."""

    __tablename__ = "products"

    product_id: str = Field(primary_key=True)
    product_name: str = Field(nullable=False)
    company_key: str = Field(foreign_key="companies.company_key", index=True)
    # Note: product_branch stores pipe-delimited tokens (e.g., '|09|' or '|00||01|')
    # so it cannot be a foreign key to branches.code
    product_branch: str | None = Field(default=None, index=True)
    product_type: str | None = Field(default=None, index=True)
    target_audience: str | None = Field(default=None)

    # Extracted from ProductAnalysis.product_summary
    description_es: str | None = Field(default=None)
    description_en: str | None = Field(default=None)
    key_benefits: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    # Extracted from ProductAnalysis.contract_terms
    contract_duration: str | None = Field(default=None, index=True)
    renewal_type: str | None = Field(default=None, index=True)
    cancellation_notice_days_policyholder: int | None = Field(default=None)
    cancellation_notice_days_insurer: int | None = Field(default=None)
    payment_method: str | None = Field(default=None)
    payment_frequency: list[str] | None = Field(default_factory=list, sa_column=Column(JSON))

    # Extracted from ProductAnalysis.geographic_coverage
    primary_territory: str | None = Field(default=None, index=True)

    # Extracted from ProductAnalysis.obligations
    claim_notification_deadline_days: int | None = Field(default=None)

    # Extracted from ProductAnalysis.pricing
    base_premium: str | None = Field(default=None)

    # Counts for quick filtering
    coverage_count: int | None = Field(default=None, index=True)
    exclusion_count: int | None = Field(default=None)

    # Full JSON backup
    details_json: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))


class ProductCoverageTable(SQLModel, table=True):
    """SQLModel table for product coverages."""

    __tablename__ = "product_coverages"

    id: int | None = Field(default=None, primary_key=True)
    product_id: str = Field(foreign_key="products.product_id", index=True)
    name: str = Field(nullable=False, index=True)
    category: str = Field(nullable=False, index=True)  # basic, optional, included_service
    description: str | None = Field(default=None)
    capital_or_limit: str | None = Field(default=None)
    waiting_period_days: int | None = Field(default=None)
    covered_events: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    benefits: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    conditions: list[str] | None = Field(default_factory=list, sa_column=Column(JSON))


class ProductExclusionTable(SQLModel, table=True):
    """SQLModel table for product exclusions."""

    __tablename__ = "product_exclusions"

    id: int | None = Field(default=None, primary_key=True)
    product_id: str = Field(foreign_key="products.product_id", index=True)
    description: str = Field(nullable=False)
    category: str | None = Field(default=None, index=True)
    legal_reference: str | None = Field(default=None)


class ProductLimitTable(SQLModel, table=True):
    """SQLModel table for product limits and restrictions."""

    __tablename__ = "product_limits"

    id: int | None = Field(default=None, primary_key=True)
    product_id: str = Field(foreign_key="products.product_id", index=True)
    coverage_name: str = Field(nullable=False, index=True)
    limit_type: str = Field(nullable=False, index=True)
    limit_value: str = Field(nullable=False)
    conditions: str | None = Field(default=None)


class ProductSourceDocumentTable(SQLModel, table=True):
    """SQLModel table for product source documents."""

    __tablename__ = "product_source_documents"

    id: int | None = Field(default=None, primary_key=True)
    product_id: str = Field(foreign_key="products.product_id", index=True)
    filename: str = Field(nullable=False)
    document_type: str = Field(nullable=False, index=True)
    extraction_confidence: float = Field(nullable=False)
