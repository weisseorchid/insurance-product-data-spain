import time
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup, Tag
from pydantic import ValidationError

from insurance_product_data_spain.__version__ import __version__
from insurance_product_data_spain.clients.http_client import get_http_client
from insurance_product_data_spain.constants.api_headers import mineco_headers, mineco_params
from insurance_product_data_spain.constants.public_urls import INSURANCE_REGULATOR_SPAIN_URL
from insurance_product_data_spain.core.logging import logger
from insurance_product_data_spain.schemas.insurance_companies import (
    InsuranceCompanyBase,
    InsuranceCompanyDetails,
)
from insurance_product_data_spain.utils.data_extraction import extract_js_data, extract_label_value

MODULE_VERSION = __version__
MODULE_LAST_MODIFIED = datetime.now().isoformat()

def get_insurance_companies(
    base_url: str = INSURANCE_REGULATOR_SPAIN_URL,
    search_params: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Fetch insurance company data from the Spanish insurance regulator website.

    Args:
        base_url: Base URL of the website
        search_params: Dictionary with search parameters matching the form fields
                      (e.g., Clave, Cif, Descripcion, Situacion, etc.)

    Returns:
        JSON response from the API
    """
    url = f"{base_url}/Aseguradora/GetAseguradorasBusqueda"

    # Default parameters
    default_params = {
        "Gestora": False,
        "OperadorClave": "4",  # equals
        "Clave": "",
        "OperadorCif": "4",  # equals
        "Cif": "",
        "OperadorDescripcion": "3",  # contains
        "Descripcion": "",
        "Situacion": "1",  # active
        "Ambito": "",
        "TipoEntidad": "",
        "Espannola": False,
        "OpcionBusqueda": "actividad",
        "TipoActividadSeleccionada": "--",
        "Ramo": "--",
        "Modalidades": "",
        "Prestacion": "",
        "PaisOrigenLPS": False,
        "PaisOrigenDE": False,
        "PaisOrigen": "",
        "EEE": True,
        "BusquedaCombinadaRamos": True,
        "RamosTexto": "",
        "PrestacionesTexto": ""
    }

    if search_params is None:
        search_params = default_params
    else:
        search_params = {**default_params, **search_params}

    params = mineco_params

    headers = mineco_headers

    response = get_http_client().post(url, data=search_params, params=params, headers=headers)
    response.raise_for_status()

    result: dict[str, Any] = response.json()

    # Validate response if it's a list of companies
    if isinstance(result, list):
        validated_companies = []
        for company_data in result:
            try:
                validated_company = InsuranceCompanyBase.model_validate(company_data)
                validated_companies.append(validated_company.model_dump(by_alias=False))
            except ValidationError as e:
                logger.warning(f"Validation error for company data: {e.errors()}")
                # Include invalid data but log the warning
                validated_companies.append(company_data)
        return validated_companies

    return result


def get_insurance_company_details(
    company_key: str,
    base_url: str = INSURANCE_REGULATOR_SPAIN_URL,
    delay: float = 0.1
) -> dict[str, Any]:
    """
    Fetch detailed information for a specific insurance company by its company key.

    Args:
        company_key: The company identifier (e.g., "C0001")
        base_url: Base URL of the website
        delay: Delay in seconds between requests to avoid overwhelming the server

    Returns:
        Dictionary with detailed company information parsed from HTML
    """
    url = f"{base_url}/Aseguradora/GetAseguradora/"

    params = mineco_params

    headers = mineco_headers

    # Add delay to avoid overwhelming the server
    if delay > 0:
        time.sleep(delay)

    response = get_http_client().get(url, params=params, headers=headers)
    response.raise_for_status()

    # Check if response is empty
    if not response.text or not response.text.strip():
        raise ValueError(f"Empty response from server for company_key: {company_key}")

    # Parse HTML
    soup = BeautifulSoup(response.text, 'html.parser')

    # Extract general data from "Datos generales" tab
    details: dict[str, Any] = {}

    # General information fields
    details['company_key'] = extract_label_value(soup, 'Clave:') or company_key
    details['lei_code'] = extract_label_value(soup, 'Código LEI:')
    details['manager_key'] = extract_label_value(soup, 'Clave Gestora:')
    details['denomination'] = extract_label_value(soup, 'Denominación:')
    details['nif'] = extract_label_value(soup, 'NIF:')
    details['status'] = extract_label_value(soup, 'Situación:')
    details['website'] = extract_label_value(soup, 'Dirección Web:')
    details['email'] = extract_label_value(soup, 'Email:')
    details['authorization_date'] = extract_label_value(soup, 'Fecha Autorización:')
    details['subscribed_capital'] = extract_label_value(soup, 'Capital Suscrito:')
    details['paid_in_capital'] = extract_label_value(soup, 'Desembolsado:')

    # Branch address (Dirección Sucursal)
    details['branch_address'] = extract_label_value(soup, 'Dirección Sucursal:')
    details['postal_code'] = extract_label_value(soup, 'Código Postal:')
    details['province'] = extract_label_value(soup, 'Provincia:')
    details['autonomous_community'] = extract_label_value(soup, 'Comunidad:')
    details['country_of_origin'] = extract_label_value(soup, 'País de Origen:')
    details['phone'] = extract_label_value(soup, 'Teléfono:')
    details['fax'] = extract_label_value(soup, 'Fax:')
    details['scope'] = extract_label_value(soup, 'Ámbito:')

    # Extract data from JavaScript variables
    details['executives'] = extract_js_data(soup, 'loadGridCargos') or []
    details['insurance_branches'] = extract_js_data(soup, 'loadGridModalidades') or []
    details['shareholders'] = extract_js_data(soup, 'loadGridSocios') or []
    details['lps'] = extract_js_data(soup, 'loadGridLPS') or []  # LPS: Lista de Países de Servicio
    details['agencies'] = extract_js_data(soup, 'loadGridAgencias') or []

    # Extract SAC (Servicio de atención al cliente - Customer Service) data
    sac_container = soup.find('div', id='containerSac')
    if sac_container and isinstance(sac_container, Tag):
        sac_data: dict[str, Any] = {}
        sac_data['name'] = extract_label_value(sac_container, 'Nombre:')
        sac_data['address'] = extract_label_value(sac_container, 'Dirección:')
        sac_data['post_office_box'] = extract_label_value(sac_container, 'Apto. Correos:')
        sac_data['country'] = extract_label_value(sac_container, 'País:')
        sac_data['postal_code'] = extract_label_value(sac_container, 'Código Postal:')
        sac_data['province'] = extract_label_value(sac_container, 'Provincia:')
        sac_data['municipality'] = extract_label_value(sac_container, 'Municipio:')
        sac_data['city'] = extract_label_value(sac_container, 'Población:')
        sac_data['phone'] = extract_label_value(sac_container, 'Teléfono:')
        sac_data['fax'] = extract_label_value(sac_container, 'Fax:')
        sac_data['mobile_phone'] = extract_label_value(sac_container, 'Télefono Móvil:')
        sac_data['email'] = extract_label_value(sac_container, 'Email:')
        sac_data['web'] = extract_label_value(sac_container, 'Web:')
        details['customer_service'] = sac_data

    # Check for DE (Directorio de Entidades - Directory of Entities) - might be empty
    de_tab = soup.find('div', id='tabListadoDE')
    if de_tab and isinstance(de_tab, Tag):
        alert = de_tab.find('p', class_='alert')
        if alert and 'No se han encontrado datos' in alert.get_text():
            details['directory_of_entities'] = []
        else:
            de_data = extract_js_data(soup, 'loadGridDE')
            details['directory_of_entities'] = de_data or []

    # Validate the details against the schema
    try:
        validated_details = InsuranceCompanyDetails.model_validate(details)
        return validated_details.model_dump(by_alias=False)
    except ValidationError as e:
        logger.warning(f"Validation error for company details (key: {company_key}): {e.errors()}")
        # Return the original data even if validation fails
        return details


def enrich_insurance_companies(
    companies: list[dict[str, Any]],
    base_url: str = "https://rrpp.dgsfp.mineco.es/",
    delay: float = 0.1,
    verbose: bool = True
) -> list[dict[str, Any]]:
    """
    Enrich a list of insurance companies with detailed information.

    Args:
        companies: List of company dictionaries (must have 'company_key' or 'clave' field)
        base_url: Base URL of the website
        delay: Delay in seconds between requests
        verbose: Whether to print progress information

    Returns:
        List of enriched company dictionaries
    """
    enriched_companies = []
    total = len(companies)

    for idx, company in enumerate(companies, 1):
        company_key = company.get("clave") or company.get("company_key")
        if not company_key:
            if verbose:
                logger.warning(f" {idx-1} has no 'company_key' or 'clave', skipping...")
            enriched_companies.append(company)
            continue

        try:
            if verbose:
                logger.info(f"Fetching details for {company_key} ({idx}/{total})...", end="\r")

            details = get_insurance_company_details(company_key, base_url, delay)

            # Merge the original company data with the detailed information
            enriched_company = {**company, **details}

            # Validate the enriched company against the schema
            try:
                validated_company = InsuranceCompanyDetails.model_validate(enriched_company)
                enriched_companies.append(validated_company.model_dump(by_alias=False))
            except ValidationError as e:
                if verbose:
                    logger.warning(f"Validation error for enriched company {company_key}: {e.errors()}")
                # Include the enriched company even if validation fails
                enriched_companies.append(enriched_company)

        except Exception as e:
            if verbose:
                error_msg = str(e)
                # Truncate very long error messages
                if len(error_msg) > 200:
                    error_msg = error_msg[:200] + "..."
                logger.error(f"\nError fetching details for {company_key}: {error_msg}")
            # Keep the original company data if details fetch fails
            enriched_companies.append(company)

    if verbose:
        logger.info(f"\nCompleted: Enriched {len(enriched_companies)} companies")

    return enriched_companies

"""
# Example usage:
if __name__ == "__main__":
    # Step 1: Search for all active insurance companies
    logger.info("Step 1: Fetching list of all insurance companies...")
    data = get_insurance_companies()

    # Check if response contains an error
    if isinstance(data, dict) and "error" in data:
        logger.error(f"Error: {data['error']}")
        exit(1)

    if not isinstance(data, list):
        logger.error(f"Unexpected response type: {type(data).__name__}")
        exit(1)

    logger.info(f"Found {len(data)} insurance companies")

    # Step 2: Enrich each company with detailed information
    logger.info("\nStep 2: Fetching detailed information for each company...")
    enriched_data = enrich_insurance_companies(data, delay=0.1, verbose=True)

    # Step 3: Save enriched data to JSON file
    logger.info("\nStep 3: Saving enriched data to JSON file...")
    with open('data/insurance_companies.json', 'w', encoding='utf-8') as f:
        json.dump(enriched_data, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved {len(enriched_data)} to data/insurance_companies.json")
"""
