from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .common import CustomerService


class InsuranceCompanyBase(BaseModel):
    """Base model for insurance company with common fields."""

    model_config = ConfigDict(populate_by_name=True)

    company_key: str = Field(..., alias="clave", description="Company identifier (e.g., 'C0001')")
    denomination: str | None = Field(None, description="Company denomination/name")
    nif: str | None = Field(None, description="NIF (Tax Identification Number)")
    status: str | None = Field(None, description="Company status (Situación)")
    # --- Synthetic Entity Pattern ---
    is_synthetic: bool = Field(False, description="Whether this is a synthetic/virtual entity")


class InsuranceCompanyDetails(InsuranceCompanyBase):
    """Detailed insurance company information model.

    This represents the full company information returned by get_insurance_company_details().
    """

    # General information fields
    lei_code: str | None = Field(None, description="Legal Entity Identifier code")
    manager_key: str | None = Field(None, description="Manager key (Clave Gestora)")
    website: str | None = Field(None, description="Company website URL")
    email: str | None = Field(None, description="Company email address")
    authorization_date: str | None = Field(None, description="Authorization date (Fecha Autorización)")
    subscribed_capital: str | None = Field(None, description="Subscribed capital (Capital Suscrito)")
    paid_in_capital: str | None = Field(None, description="Paid-in capital (Desembolsado)")

    # Branch address fields
    branch_address: str | None = Field(None, description="Branch address (Dirección Sucursal)")
    postal_code: str | None = Field(None, description="Postal code")
    province: str | None = Field(None, description="Province")
    autonomous_community: str | None = Field(None, description="Autonomous community (Comunidad)")
    country_of_origin: str | None = Field(None, description="Country of origin (País de Origen)")
    phone: str | None = Field(None, description="Phone number")
    fax: str | None = Field(None, description="Fax number")
    scope: str | None = Field(None, description="Scope (Ámbito)")

    # Nested structures (lists of dictionaries from JavaScript data)
    executives: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of executives (Cargos) extracted from JavaScript grid data",
    )
    insurance_branches: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of insurance branches/modalidades extracted from JavaScript grid data",
    )
    shareholders: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of shareholders (Socios) extracted from JavaScript grid data",
    )
    lps: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of service countries (LPS - Lista de Países de Servicio)",
    )
    agencies: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of agencies (Agencias) extracted from JavaScript grid data",
    )
    directory_of_entities: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Directory of entities (DE - Directorio de Entidades)",
    )

    # Customer service nested model
    customer_service: CustomerService | None = Field(
        None, description="Customer service information (SAC - Servicio de atención al cliente)"
    )
