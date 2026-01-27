"""Fetchers for scraping data from the Spanish insurance regulator website."""

from .companies import (
    enrich_insurance_companies,
    get_insurance_companies,
    get_insurance_company_details,
)
from .distributors import (
    enrich_insurance_distributors,
    get_insurance_distributor_details,
    get_insurance_distributors,
)

__all__ = [
    "get_insurance_companies",
    "get_insurance_company_details",
    "enrich_insurance_companies",
    "get_insurance_distributors",
    "get_insurance_distributor_details",
    "enrich_insurance_distributors",
]
