from typing import Any

import pytest

from insurance_product_data_spain.services.v1.insurance_companies.get_insurance_companies import (
    get_insurance_companies,
    get_insurance_company_details,
)
from insurance_product_data_spain.services.v1.insurance_distributors.get_insurance_distributors import (
    get_insurance_distributor_details,
    get_insurance_distributors,
)


def _extract_key(item: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = item.get(key)
        if value:
            return str(value)
    return None


@pytest.mark.live
def test_companies_pipeline_live() -> None:
    companies = get_insurance_companies()
    assert isinstance(companies, list)
    assert companies

    company_key = _extract_key(companies[0], "clave", "company_key", "Clave")
    assert company_key

    details = get_insurance_company_details(company_key)
    assert isinstance(details, dict)
    assert details.get("company_key") == company_key or details.get("company_key")


@pytest.mark.live
def test_distributors_pipeline_live() -> None:
    distributors = get_insurance_distributors()
    assert isinstance(distributors, list)
    assert distributors

    distributor_key = _extract_key(distributors[0], "clave", "distributor_key", "Clave")
    assert distributor_key

    details = get_insurance_distributor_details(distributor_key)
    assert isinstance(details, dict)
    assert details.get("distributor_key") == distributor_key or details.get("distributor_key")
