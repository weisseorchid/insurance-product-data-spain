from .public_urls import INSURANCE_REGULATOR_SPAIN_URL

base_url = INSURANCE_REGULATOR_SPAIN_URL

mineco_params = {
    "culture": "es-ES",
    "ui-culture": "es-ES"
}

mineco_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "es-ES,es;q=0.9",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": f"{base_url}/?culture=es-ES&ui-culture=es-ES"
}
