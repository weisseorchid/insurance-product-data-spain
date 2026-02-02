from pydantic import BaseModel, Field


class CustomerService(BaseModel):
    """Customer Service (SAC - Servicio de atención al cliente) information."""

    name: str | None = Field(None, description="Customer service name")
    address: str | None = Field(None, description="Customer service address")
    post_office_box: str | None = Field(None, description="Post office box (Apto. Correos)")
    country: str | None = Field(None, description="Country")
    postal_code: str | None = Field(None, description="Postal code")
    province: str | None = Field(None, description="Province")
    municipality: str | None = Field(None, description="Municipality")
    city: str | None = Field(None, description="City/Population")
    phone: str | None = Field(None, description="Phone number")
    fax: str | None = Field(None, description="Fax number")
    mobile_phone: str | None = Field(None, description="Mobile phone number")
    email: str | None = Field(None, description="Email address")
    web: str | None = Field(None, description="Website URL")
