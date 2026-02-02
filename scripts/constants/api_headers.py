"""API headers and parameters for the Spanish insurance regulator website."""

from .public_urls import INSURANCE_REGULATOR_SPAIN_URL

base_url = INSURANCE_REGULATOR_SPAIN_URL

mineco_params = {"culture": "es-ES", "ui-culture": "es-ES"}

mineco_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "es-ES,es;q=0.9",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": f"{base_url}/?culture=es-ES&ui-culture=es-ES",
}

# Headers for endpoints returning HTML content (e.g., GetAseguradora)
mineco_html_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",  # noqa: E501
    "Accept": "text/html, */*; q=0.01",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "X-Requested-With": "XMLHttpRequest",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Referer": f"{base_url}/?culture=es-ES&ui-culture=es-ES",
}
