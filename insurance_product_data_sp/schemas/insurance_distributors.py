from pydantic import BaseModel, ConfigDict, Field


class AgencyContract(BaseModel):
    """Model for an agency contract between a distributor and an insurer."""

    model_config = ConfigDict(populate_by_name=True)

    contract_id: int = Field(..., alias="idContrato", description="Contract identifier")
    operator_id: str | None = Field(None, alias="idOperador", description="Operator identifier")
    company_key: str | None = Field(None, alias="claveDGSFP", description="Reference to the insurer (company key)")
    denomination: str | None = Field(None, description="Company denomination/name")
    start_date: str = Field(..., alias="fechaAlta", description="Contract start date")
    end_date: str | None = Field(None, alias="fechaBaja", description="Contract end date (if terminated)")
    contract_type: str = Field(..., alias="tipo", description="Contract type (e.g., 'Principal')")


class InsuranceDistributorBase(BaseModel):
    """Base model for insurance distributor with common fields."""

    model_config = ConfigDict(populate_by_name=True)

    distributor_key: str = Field(..., alias="clave", description="Distributor identifier (e.g., '00XF38295677X')")
    name: str | None = Field(None, description="Name / Company name (Razón Social)")
    status: str | None = Field(None, description="Status (Situación)")
    control_authority: str | None = Field(None, description="Control authority (Autoridad de Control)")
    mediator_class: str | None = Field(None, description="Mediator class (Clase de mediador)")
    registration_key: str | None = Field(None, description="Registration key (Clave Registro)")
    lei_code: str | None = Field(None, description="Legal Entity Identifier code")


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

    # Nested structures - now strictly typed
    agency_contracts: list[AgencyContract] = Field(
        default_factory=list,
        description="List of agency contracts (Contratos) between this distributor and insurers",
    )
