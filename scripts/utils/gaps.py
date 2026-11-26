"""Per-company gap reports written after fetch and analysis runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from insurance_product_data_sp.core.logging import logger
from scripts.utils.storage import ensure_directory, save_json

GAPS_FILENAME = "gaps.json"

_GAP_SORT_KEYS = ("product_id", "product_name", "doc_id", "filename", "reason", "detail", "source")


def gaps_path(company_folder: Path) -> Path:
    return company_folder / "metadata" / GAPS_FILENAME


def _gap_sort_key(gap: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(gap.get(k) or "") for k in _GAP_SORT_KEYS)


def write_gaps_report(
    company_folder: Path,
    company_key: str,
    script: str,
    gaps: list[dict[str, Any]],
) -> Path:
    """Write ``metadata/gaps.json`` (stable, no timestamps) and log one line per gap.

    Each gap dict should include at least ``reason``, plus identifying fields such as
    ``product_id``, ``product_name``, ``doc_id`` and/or ``filename``.
    """
    metadata_folder = company_folder / "metadata"
    ensure_directory(metadata_folder)
    path = gaps_path(company_folder)
    ordered = sorted(gaps, key=_gap_sort_key)
    payload = {
        "schema_version": "1.0",
        "company_key": company_key,
        "script": script,
        "gap_count": len(ordered),
        "gaps": ordered,
    }
    save_json(payload, path, indent=2)

    if ordered:
        logger.warning(f"{len(ordered)} gap(s) for {company_key} ({script}); see {path}")
        for gap in ordered:
            product_id = gap.get("product_id") or "-"
            product_name = gap.get("product_name") or "-"
            doc = gap.get("filename") or gap.get("doc_id") or "-"
            reason = gap.get("reason") or "unknown"
            detail = gap.get("detail") or ""
            logger.warning(f"GAP {product_id} {product_name} {doc} {reason} {detail}".rstrip())
    else:
        logger.info(f"No gaps for {company_key} ({script})")

    return path
