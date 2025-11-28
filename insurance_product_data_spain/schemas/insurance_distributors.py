from typing import Any

from pydantic import BaseModel, Field


class InsuranceDistributorBase(BaseModel):
    """Base model for insurance distributor with common fields."""

    distributor_key: str = Field(..., alias="clave", description="Distributor identifier (e.g., '00XF38295677X')")
    name: str | None = Field(None, description="Name / Company name (Razón Social)")
    status: str | None = Field(None, description="Status (Situación)")
    control_authority: str | None = Field(None, description="Control authority (Autoridad de Control)")
    mediator_class: str | None = Field(None, description="Mediator class (Clase de mediador)")
    registration_key: str | None = Field(None, description="Registration key (Clave Registro)")
    lei_code: str | None = Field(None, description="Legal Entity Identifier code")

    class Config:
        populate_by_name = True  # Allow both alias and field name


class InsuranceDistributorDetails(InsuranceDistributorBase):
    """Detailed insurance distributor information model.

    This represents the full distributor information returned by get_insurance_distributor_details().
    """

    # Additional general information fields
    accreditation: str | None = Field(None, description="Accreditation (Acreditación)")
    operation_scope: str | None = Field(None, description="Operation scope (Ámbito de operación)")
    auth_by_other_insurer: str | None = Field(
        None, description="Authorized by another insurer (Autorizada por otra entidad aseguradora)"
    )
    registration_date: str | None = Field(None, description="Registration date (Fecha Inscripción)")

    # Address fields
    address: str | None = Field(None, description="Address (Dirección)")
    postal_code: str | None = Field(None, description="Postal code")
    province: str | None = Field(None, description="Province")
    municipality: str | None = Field(None, description="Municipality (Municipio postal)")
    country_of_origin: str | None = Field(None, description="Country of origin (País de Origen)")
    website: str | None = Field(None, description="Website URL (Dirección Web)")

    # Nested structures (lists of dictionaries from JavaScript data)
    agency_contracts: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of agency contracts (Contratos) extracted from JavaScript grid data",
    )

    class Config:
        populate_by_name = True  # Allow both alias and field name

