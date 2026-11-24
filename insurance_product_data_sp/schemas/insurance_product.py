"""Insurance product schema with structured analysis for policy documents.

This module provides Pydantic models for representing insurance products
and their analyzed content extracted from policy documents (PIDs, general
conditions, brochures, etc.) using AI-powered extraction.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# =============================================================================
# Enums
# =============================================================================


class CoverageCategory(str, Enum):
    """Category of insurance coverage."""

    BASIC = "basic"  # Mandatory/included coverages
    OPTIONAL = "optional"  # Add-on coverages
    INCLUDED_SERVICE = "included_service"  # Non-insurance services included


class DocumentType(str, Enum):
    """Type of insurance document."""

    PID = "pid"  # Product Information Document (IPID)
    GENERAL_CONDITIONS = "general_conditions"  # Condiciones Generales
    LIMITING_CONDITIONS = "limiting_conditions"  # Condiciones Limitativas
    BROCHURE = "brochure"  # Folleto
    USAGE_GUIDE = "usage_guide"  # Guía de Uso
    OTHER = "other"


# =============================================================================
# Supporting Sub-Schemas
# =============================================================================


class ProductSummary(BaseModel):
    """High-level product description and identity."""

    product_type: str = Field(..., description="Type of insurance (e.g., 'Seguro de Hogar', 'Seguro de Salud')")
    target_audience: str | None = Field(None, description="Target market (e.g., 'Autónomos', 'PYMES', 'Particulares')")
    description_es: str = Field(..., description="Product description in Spanish")
    description_en: str | None = Field(None, description="Product description in English")
    key_benefits: list[str] = Field(default_factory=list, description="Main selling points and benefits")
    insurance_company: str = Field(..., description="Name of the insurance company")
    administrative_code: str | None = Field(None, description="DGSFP administrative code (e.g., 'C-0737')")


class Coverage(BaseModel):
    """Individual coverage or guarantee offered by the policy."""

    name: str = Field(..., description="Name of the coverage")
    category: CoverageCategory = Field(..., description="Coverage category (basic/optional/service)")
    description: str = Field(..., description="Description of what this coverage provides")
    covered_events: list[str] = Field(
        default_factory=list, description="Events or situations that trigger this coverage"
    )
    benefits: list[str] = Field(default_factory=list, description="Benefits or compensation provided")
    capital_or_limit: str | None = Field(None, description="Maximum coverage amount (e.g., '100.000€', 'unlimited')")
    waiting_period_days: int | None = Field(
        None, description="Waiting period (carencia) in days before coverage applies"
    )
    conditions: list[str] | None = Field(None, description="Special conditions or requirements for this coverage")


class Exclusion(BaseModel):
    """Exclusion - what is NOT covered by the policy."""

    description: str = Field(..., description="Description of what is excluded")
    category: str | None = Field(None, description="Category of exclusion (e.g., 'General', 'Specific to coverage X')")
    legal_reference: str | None = Field(None, description="Legal article or clause reference if available")


class LimitOrRestriction(BaseModel):
    """Coverage limit or restriction."""

    coverage_name: str = Field(..., description="Name of the coverage this limit applies to")
    limit_type: str = Field(
        ...,
        description="Type of limit (e.g., 'maximum_amount', 'sessions_per_year', 'days_per_year')",
    )
    limit_value: str = Field(..., description="Value of the limit (e.g., '12.000€', '15 sessions', '90 days')")
    conditions: str | None = Field(None, description="Additional conditions for this limit")


class PolicyholderObligations(BaseModel):
    """Policyholder's duties and obligations under the contract."""

    general_obligations: list[str] = Field(
        default_factory=list,
        description="General obligations (e.g., 'Pay premiums', 'Truthful declaration')",
    )
    claim_notification_deadline_days: int | None = Field(
        None, description="Days to notify the insurer after a claim event"
    )
    claim_obligations: list[str] = Field(
        default_factory=list, description="Obligations when filing or managing a claim"
    )


class ContractTerms(BaseModel):
    """Contract duration, renewal, and termination terms."""

    duration: str = Field(..., description="Contract duration (e.g., 'Annual', 'Annual with automatic renewal')")
    renewal_type: str = Field(..., description="Type of renewal (e.g., 'automatic', 'manual')")
    cancellation_notice_days_policyholder: int | None = Field(
        None, description="Days of notice required from policyholder to cancel before renewal"
    )
    cancellation_notice_days_insurer: int | None = Field(
        None, description="Days of notice required from insurer to cancel before renewal"
    )
    termination_causes: list[str] = Field(default_factory=list, description="Causes that can terminate the contract")
    payment_method: str | None = Field(None, description="Payment method (e.g., 'Bank direct debit')")
    payment_frequency: list[str] | None = Field(
        None, description="Available payment frequencies (e.g., ['monthly', 'quarterly', 'annual'])"
    )


class PricingInfo(BaseModel):
    """Pricing information when available in the documents."""

    base_premium: str | None = Field(None, description="Base premium amount if specified")
    copay_info: str | None = Field(None, description="Copayment information if applicable")
    pricing_factors: list[str] = Field(default_factory=list, description="Factors that affect the premium price")
    discounts: list[str] | None = Field(None, description="Available discounts")


class GeographicCoverage(BaseModel):
    """Geographic scope of the coverage."""

    primary_territory: str = Field(..., description="Primary coverage territory (e.g., 'Spain', 'European Union')")
    worldwide_coverage: list[str] | None = Field(None, description="List of coverages that apply worldwide")
    special_conditions_abroad: str | None = Field(None, description="Special conditions for coverage abroad")


class SourceDocument(BaseModel):
    """Reference to a source document used in the analysis."""

    filename: str = Field(..., description="Name of the source file")
    document_type: DocumentType = Field(..., description="Type of document")
    extraction_confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score of extraction (0.0 to 1.0)")


# =============================================================================
# Main Analysis Schema
# =============================================================================


class ProductAnalysis(BaseModel):
    """Structured analysis extracted from insurance policy documents.

    This schema is designed to capture comprehensive information about an
    insurance product from various document types (PIDs, general conditions,
    brochures, etc.) using AI-powered extraction.
    """

    # Core product identity
    product_summary: ProductSummary = Field(..., description="High-level product information")

    # What's covered
    coverages: list[Coverage] = Field(default_factory=list, description="List of coverages/guarantees offered")

    # What's NOT covered
    exclusions: list[Exclusion] = Field(default_factory=list, description="List of exclusions (what is not covered)")

    # Limits and restrictions
    limits_and_restrictions: list[LimitOrRestriction] = Field(
        default_factory=list, description="Coverage limits and restrictions"
    )

    # Policyholder obligations
    obligations: PolicyholderObligations = Field(..., description="Policyholder duties and obligations")

    # Contract terms
    contract_terms: ContractTerms = Field(..., description="Contract duration and termination terms")

    # Pricing info (when available)
    pricing: PricingInfo | None = Field(None, description="Pricing information (may not be available in all documents)")

    # Geographic scope
    geographic_coverage: GeographicCoverage = Field(..., description="Geographic scope of coverage")

    # Document sources used for this analysis
    source_documents: list[SourceDocument] = Field(
        default_factory=list, description="Source documents used for this analysis"
    )


# =============================================================================
# Main Product Schema
# =============================================================================


class DocumentReference(BaseModel):
    """Reference to a document in documents.jsonl."""

    filename: str = Field(..., description="Document filename")
    pdf_sha256: str = Field(..., description="SHA256 hash of the PDF document")
    markdown_sha256: str | None = Field(None, description="SHA256 hash of the markdown conversion")
    doc_type: str | None = Field(None, description="Document type (ipid, general_conditions, etc.)")


class InsuranceProduct(BaseModel):
    """Complete insurance product model with structured analysis.

    Represents an insurance product with its metadata and AI-extracted
    analysis from policy documents.

    Schema version 1 (product_id, company_key, branches, document_references).
    """

    product_id: str = Field(..., description="Unique product identifier (e.g., 'urn:C0737-01')")
    company_key: str = Field(..., description="DGSFP company key (e.g., 'C0737')")
    product_name: str = Field(..., description="Product name (snake_case identifier)")
    branches: list[str] = Field(..., description="Insurance branch codes (e.g., ['00', '09'])")
    source_url: str | None = Field(None, description="Primary source URL for the product")
    document_references: list[DocumentReference] = Field(
        default_factory=list, description="References to documents in documents.jsonl"
    )
    analysis_path: str | None = Field(None, description="Path to analysis JSON file (e.g., 'analysis/product.json')")
    fetched_at: str | None = Field(None, description="ISO8601 timestamp when product was fetched")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    # Legacy field for backward compatibility with analysis JSON files
    product_branch: str | list[str] | None = Field(None, description="Deprecated: use branches field")
    source_urls: list[str] = Field(default_factory=list, description="Deprecated: use source_url field")
    analysis: ProductAnalysis | None = Field(None, description="Structured analysis extracted from policy documents")
