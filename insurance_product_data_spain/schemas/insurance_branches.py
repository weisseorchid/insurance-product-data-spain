"""Insurance branches (ramos) dictionary for Spanish insurance market.

This module provides a comprehensive mapping of insurance branches as defined
by the Spanish insurance regulatory framework (DGSFP - Dirección General de
Seguros y Fondos de Pensiones).

The branches are categorized into:
- Life insurance (Vida): Code 0
- Non-life insurance (No Vida): Codes 1-19
"""

from typing import TypedDict


class InsuranceBranch(TypedDict):
    """Type definition for an insurance branch entry."""

    code: str
    name_es: str
    name_en: str
    category: str  # "life" or "non_life"


# Complete dictionary of insurance branches (ramos)
INSURANCE_BRANCHES: dict[str, InsuranceBranch] = {
    "00": {
        "code": "00",
        "name_es": "Vida",
        "name_en": "Life",
        "category": "life",
    },
    "01": {
        "code": "01",
        "name_es": "Accidentes",
        "name_en": "Accidents",
        "category": "non_life",
    },
    "02": {
        "code": "02",
        "name_es": "Enfermedad",
        "name_en": "Health / Illness",
        "category": "non_life",
    },
    "03": {
        "code": "03",
        "name_es": "Vehículos terrestres no ferroviarios",
        "name_en": "Non-railway land vehicles",
        "category": "non_life",
    },
    "04": {
        "code": "04",
        "name_es": "Vehículos ferroviarios",
        "name_en": "Railway vehicles",
        "category": "non_life",
    },
    "05": {
        "code": "05",
        "name_es": "Vehículos aéreos",
        "name_en": "Aircraft",
        "category": "non_life",
    },
    "06": {
        "code": "06",
        "name_es": "Vehículos marítimos, lacustres y fluviales",
        "name_en": "Maritime, lake and river vessels",
        "category": "non_life",
    },
    "07": {
        "code": "07",
        "name_es": "Mercancías transportadas",
        "name_en": "Goods in transit",
        "category": "non_life",
    },
    "08": {
        "code": "08",
        "name_es": "Incendio y elementos naturales",
        "name_en": "Fire and natural forces",
        "category": "non_life",
    },
    "09": {
        "code": "09",
        "name_es": "Otros daños a los bienes",
        "name_en": "Other property damage",
        "category": "non_life",
    },
    "10": {
        "code": "10",
        "name_es": "Responsabilidad civil vehículos terrestres automóviles",
        "name_en": "Motor vehicle liability",
        "category": "non_life",
    },
    "11": {
        "code": "11",
        "name_es": "Responsabilidad civil vehículos aéreos",
        "name_en": "Aircraft liability",
        "category": "non_life",
    },
    "12": {
        "code": "12",
        "name_es": "Responsabilidad civil vehículos marítimos, lacustres y fluviales",
        "name_en": "Maritime, lake and river vessel liability",
        "category": "non_life",
    },
    "13": {
        "code": "13",
        "name_es": "Responsabilidad civil general",
        "name_en": "General liability",
        "category": "non_life",
    },
    "14": {
        "code": "14",
        "name_es": "Crédito",
        "name_en": "Credit",
        "category": "non_life",
    },
    "15": {
        "code": "15",
        "name_es": "Caución",
        "name_en": "Suretyship",
        "category": "non_life",
    },
    "16": {
        "code": "16",
        "name_es": "Pérdidas pecuniarias diversas",
        "name_en": "Miscellaneous financial loss",
        "category": "non_life",
    },
    "17": {
        "code": "17",
        "name_es": "Defensa jurídica",
        "name_en": "Legal expenses",
        "category": "non_life",
    },
    "18": {
        "code": "18",
        "name_es": "Asistencia",
        "name_en": "Assistance",
        "category": "non_life",
    },
    "19": {
        "code": "19",
        "name_es": "Decesos",
        "name_en": "Funeral expenses",
        "category": "non_life",
    },
}

# Lookup helpers
BRANCH_BY_CODE: dict[str, InsuranceBranch] = INSURANCE_BRANCHES

# Also support lookup without leading zero (e.g., "1" -> "01")
BRANCH_BY_CODE_NORMALIZED: dict[str, InsuranceBranch] = {
    **INSURANCE_BRANCHES,
    **{str(int(k)): v for k, v in INSURANCE_BRANCHES.items()},
}


def get_branch_by_code(code: str) -> InsuranceBranch | None:
    """Get insurance branch by code.

    Args:
        code: Branch code (e.g., "01", "1", "00", "0")

    Returns:
        InsuranceBranch dictionary or None if not found
    """
    # Normalize code: strip whitespace and handle single digits
    normalized = code.strip().zfill(2)
    return INSURANCE_BRANCHES.get(normalized)


def get_branch_name(code: str, language: str = "es") -> str | None:
    """Get branch name by code in specified language.

    Args:
        code: Branch code (e.g., "01", "1")
        language: Language code ("es" for Spanish, "en" for English)

    Returns:
        Branch name or None if not found
    """
    branch = get_branch_by_code(code)
    if branch is None:
        return None
    return branch.get(f"name_{language}")


def list_life_branches() -> list[InsuranceBranch]:
    """Return all life insurance branches."""
    return [b for b in INSURANCE_BRANCHES.values() if b["category"] == "life"]


def list_non_life_branches() -> list[InsuranceBranch]:
    """Return all non-life insurance branches."""
    return [b for b in INSURANCE_BRANCHES.values() if b["category"] == "non_life"]


# For JSON export compatibility
INSURANCE_BRANCHES_LIST: list[InsuranceBranch] = list(INSURANCE_BRANCHES.values())
