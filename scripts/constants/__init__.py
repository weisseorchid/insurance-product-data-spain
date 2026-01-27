"""Constants for scraping the Spanish insurance regulator website."""

from .api_headers import mineco_headers, mineco_html_headers, mineco_params
from .public_urls import INSURANCE_REGULATOR_SPAIN_URL

__all__ = [
    "INSURANCE_REGULATOR_SPAIN_URL",
    "mineco_headers",
    "mineco_html_headers",
    "mineco_params",
]
