"""Single source of truth for loading insurance company records.

The canonical companies file is ``data/insurance_companies.jsonl``. The legacy
``data/insurance_companies.json`` is only read as a fallback when the JSONL file
is missing (e.g. an old local checkout), so every script resolves companies the
same way as ``build_db``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.config import INSURANCE_COMPANIES_JSON, INSURANCE_COMPANIES_JSONL, PRODUCTS_STORAGE_PATH
from scripts.utils.jsonl import load_jsonl
from scripts.utils.storage import load_json
from scripts.utils.text_transformations import text_to_snake_case


def resolve_companies_path(path: Path | str | None = None) -> Path:
    """Return the companies file to read.

    Args:
        path: Explicit path (``.jsonl`` or legacy ``.json``). If None, the canonical
            JSONL is used, falling back to the legacy JSON only if the JSONL is missing.

    Raises:
        FileNotFoundError: If no companies file exists.
    """
    if path is not None:
        explicit = Path(path)
        if not explicit.exists():
            raise FileNotFoundError(f"Companies file not found: {explicit}")
        return explicit
    for candidate in (INSURANCE_COMPANIES_JSONL, INSURANCE_COMPANIES_JSON):
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"Companies file not found: {INSURANCE_COMPANIES_JSONL} (or legacy {INSURANCE_COMPANIES_JSON})"
    )


def load_companies(path: Path | str | None = None) -> list[dict[str, Any]]:
    """Load all company records (JSONL preferred, legacy JSON as fallback)."""
    resolved = resolve_companies_path(path)
    data = load_jsonl(resolved) if resolved.suffix == ".jsonl" else load_json(resolved)
    if not isinstance(data, list):
        raise TypeError(f"Companies data in {resolved} must be a list, got {type(data).__name__}")
    return data


def find_company(company_key: str, path: Path | str | None = None) -> dict[str, Any] | None:
    """Return the company record for ``company_key`` or None if absent."""
    for company in load_companies(path):
        if company.get("company_key") == company_key:
            return company
    return None


def company_display_name(company: dict[str, Any]) -> str:
    """Company name, preferring the canonical ``denomination`` over the legacy ``descripcion``."""
    return company.get("denomination") or company.get("descripcion") or ""


def company_folder_name(company: dict[str, Any]) -> str:
    """Folder name used under ``data/products_by_insurance_company``."""
    return text_to_snake_case(company_display_name(company))


def company_folder_path(company: dict[str, Any], base_path: Path | None = None) -> Path:
    """Absolute path of the company's product folder (may not exist yet)."""
    return (base_path or PRODUCTS_STORAGE_PATH) / company_folder_name(company)


def company_key_for_folder(folder_name: str, path: Path | str | None = None) -> str | None:
    """Reverse lookup: company key for a product folder name."""
    for company in load_companies(path):
        if company_folder_name(company) == folder_name:
            return company.get("company_key")
    return None
