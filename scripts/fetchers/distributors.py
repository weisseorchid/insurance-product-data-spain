"""Fetcher for insurance distributors from the Spanish insurance regulator website."""

import time
from typing import Any

from bs4 import BeautifulSoup
from pydantic import ValidationError

from insurance_product_data_spain.core.logging import logger
from insurance_product_data_spain.schemas.insurance_distributors import (
    AgencyContract,
    InsuranceDistributorBase,
    InsuranceDistributorDetails,
)
from scripts.clients.http_client import get_http_client
from scripts.constants.api_headers import mineco_html_headers, mineco_params
from scripts.constants.public_urls import INSURANCE_REGULATOR_SPAIN_URL
from scripts.utils.data_extraction import extract_js_data, extract_label_value


def get_insurance_distributors(
    base_url: str = INSURANCE_REGULATOR_SPAIN_URL,
    search_params: dict[str, Any] | None = None
) -> list[dict[str, Any]] | dict[str, Any]:
    """
    Fetch insurance distributor/mediator data from the Spanish insurance regulator website.

    Args:
        base_url: Base URL of the website
        search_params: Dictionary with search parameters matching the form fields

    Returns:
        JSON response from the API
    """
    url = f"{base_url}/MEDIADOR/GetMediadoresBusqueda"

    # Default parameters for mediator search
    default_params = {
        "OperadorClave": "4",  # equals
        "Clave": "",
        "OperadorNombre": "3",  # contains
        "Nombre": "",
        "Situacion": "1",  # active
        "Clase": "",
        "Ambito": "",
        "AutoridadControl": ""
    }

    # Merge provided search_params with defaults
    if search_params is None:
        search_params = default_params
    else:
        search_params = {**default_params, **search_params}

    # Add culture parameters
    params = mineco_params

    headers = mineco_html_headers

    response = get_http_client().post(url, data=search_params, params=params, headers=headers)
    response.raise_for_status()

    result: dict[str, Any] = response.json()

    # Validate response if it's a list of distributors
    if isinstance(result, list):
        validated_distributors = []
        for distributor_data in result:
            try:
                validated_distributor = InsuranceDistributorBase.model_validate(distributor_data)
                validated_distributors.append(validated_distributor.model_dump(by_alias=False))
            except ValidationError as e:
                logger.warning(f"Validation error for distributor data: {e.errors()}")
                # Include invalid data but log the warning
                validated_distributors.append(distributor_data)
        return validated_distributors

    return result


def get_insurance_distributor_details(
    distributor_key: str,
    base_url: str = INSURANCE_REGULATOR_SPAIN_URL,
    delay: float = 0.1
) -> dict[str, Any]:
    """
    Fetch detailed information for a specific insurance distributor/mediator by its key.

    Args:
        distributor_key: The distributor identifier (e.g., "002938295677X")
        base_url: Base URL of the website
        delay: Delay in seconds between requests to avoid overwhelming the server

    Returns:
        Dictionary with detailed distributor information parsed from HTML
    """
    url = f"{base_url}/MEDIADOR/GetMediador/"

    # Add distributor_key (clave) to request params
    params = {
        **mineco_params,
        "clave": distributor_key
    }

    headers = mineco_html_headers

    # Add delay to avoid overwhelming the server
    if delay > 0:
        time.sleep(delay)

    response = get_http_client().get(url, params=params, headers=headers)
    response.raise_for_status()

    # Check if response is empty
    if not response.text or not response.text.strip():
        raise ValueError(f"Empty response from server for distributor_key: {distributor_key}")

    # Parse HTML
    soup = BeautifulSoup(response.text, 'html.parser')

    # Extract general data from "Datos generales" tab
    details: dict[str, Any] = {}

    # General information fields
    details['distributor_key'] = extract_label_value(soup, 'Clave inscripción:') or distributor_key
    details['mediator_class'] = extract_label_value(soup, 'Clase de mediador:')
    details['control_authority'] = extract_label_value(soup, 'Autoridad de Control:')
    details['registration_date'] = extract_label_value(soup, 'Fecha Inscripción:')
    details['name'] = extract_label_value(soup, 'Nombre / Razón Social:')
    details['accreditation'] = extract_label_value(soup, 'Acreditación:')
    details['operation_scope'] = extract_label_value(soup, 'Ámbito de operación:')
    details['lei_code'] = extract_label_value(soup, 'Código LEI:')
    details['auth_by_other_insurer'] = extract_label_value(
        soup,
        'Autorizada por otra entidad aseguradora:'
        )

    # Address fields
    details['address'] = extract_label_value(soup, 'Dirección:')
    details['postal_code'] = extract_label_value(soup, 'Código Postal:')
    details['province'] = extract_label_value(soup, 'Provincia:')
    details['municipality'] = extract_label_value(soup, 'Municipio postal:')
    details['country_of_origin'] = extract_label_value(soup, 'País de Origen:')
    details['website'] = extract_label_value(soup, 'Dirección Web:')

    # Extract contracts data from JavaScript variables
    contracts_raw = extract_js_data(soup, 'loadGridContratos') or []

    # Validate and convert contracts to AgencyContract models
    # Store as dicts for now; Pydantic will validate them when creating InsuranceDistributorDetails
    validated_contracts = []
    for contract_dict in contracts_raw:
        try:
            contract = AgencyContract.model_validate(contract_dict)
            # Store as dict for the details dict, Pydantic will re-validate when creating the full model
            validated_contracts.append(contract.model_dump(by_alias=False))
        except ValidationError as e:
            logger.warning(f"Validation error for contract in distributor {distributor_key}: {e.errors()}")
            # Skip invalid contracts but continue processing
            continue

    details['agency_contracts'] = validated_contracts

    # Validate the details against the schema
    try:
        validated_details = InsuranceDistributorDetails.model_validate(details)
        return validated_details.model_dump(by_alias=False)
    except ValidationError as e:
        logger.warning(f"Validation error for distributor details (key: {distributor_key}): {e.errors()}")
        # Return the original data even if validation fails
        return details


def enrich_insurance_distributors(
    distributors: list[dict[str, Any]],
    base_url: str = INSURANCE_REGULATOR_SPAIN_URL,
    delay: float = 0.1,
    verbose: bool = True
) -> list[dict[str, Any]]:
    """
    Enrich a list of insurance distributors with detailed information.

    Args:
        distributors: List of distributor dictionaries (requires 'clave' field)
        base_url: Base URL of the website
        delay: Delay in seconds between requests
        verbose: Whether to print progress information

    Returns:
        List of enriched distributor dictionaries
    """
    enriched_distributors = []
    total = len(distributors)

    for idx, distributor in enumerate(distributors, 1):
        distributor_key = distributor.get("clave") or distributor.get("distributor_key")
        if not distributor_key:
            if verbose:
                logger.warning(f" {idx-1} has no 'distributor_key' or 'clave', skipping...")
            enriched_distributors.append(distributor)
            continue

        try:
            if verbose:
                logger.info(f"Fetching details for {distributor_key} ({idx}/{total})...")

            details = get_insurance_distributor_details(distributor_key, base_url, delay)

            # Merge the original distributor data with the detailed information
            enriched_distributor = {**distributor, **details}

            # Validate the enriched distributor against the schema
            try:
                validated_distributor = InsuranceDistributorDetails.model_validate(enriched_distributor)
                enriched_distributors.append(validated_distributor.model_dump(by_alias=False))
            except ValidationError as e:
                if verbose:
                    logger.warning(f"Validation error for enriched distributor {distributor_key}: {e.errors()}")
                # Include the enriched distributor even if validation fails
                enriched_distributors.append(enriched_distributor)

        except Exception as e:
            if verbose:
                error_msg = str(e)
                # Truncate very long error messages
                if len(error_msg) > 200:
                    error_msg = error_msg[:200] + "..."
                logger.error(f"Error fetching details for {distributor_key}: {error_msg}")
            # Keep the original distributor data if details fetch fails
            enriched_distributors.append(distributor)

    if verbose:
        logger.info(f"Completed: Enriched {len(enriched_distributors)} distributors")

    return enriched_distributors
