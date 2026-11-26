"""Per-company gap reports written after fetch and analysis runs.

Reports are local run artifacts (gitignored):

- ``metadata/fetch_gaps.json`` from ``fetch_product_documents``
- ``metadata/analysis_gaps.json`` from ``analyze_products``

They are stable (sorted, no timestamps). A full-company run replaces the file;
a ``--product`` run merges by ``product_id`` so other products' gaps are kept.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from insurance_product_data_sp.core.logging import logger
from scripts.utils.storage import ensure_directory, load_json, save_json

FETCH_GAPS_FILENAME = "fetch_gaps.json"
ANALYSIS_GAPS_FILENAME = "analysis_gaps.json"
# Backward-compatible name (no longer written)
GAPS_FILENAME = "gaps.json"

_GAP_SORT_KEYS = ("product_id", "product_name", "doc_id", "filename", "reason", "detail", "source")


def gaps_path(company_folder: Path, filename: str = FETCH_GAPS_FILENAME) -> Path:
    return company_folder / "metadata" / filename


def _gap_sort_key(gap: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(gap.get(k) or "") for k in _GAP_SORT_KEYS)


def write_gaps_report(
    company_folder: Path,
    company_key: str,
    script: str,
    gaps: list[dict[str, Any]],
    *,
    filename: str,
    replace_product_ids: set[str] | None = None,
) -> Path:
    """Write a script-specific gaps file (stable, no timestamps) and log one line per gap.

    Args:
        company_folder: Company product folder
        company_key: DGSFP company key
        script: Script name recorded in the report
        gaps: Gap rows for this run (at least ``reason``, plus product/doc identifiers)
        filename: Target under ``metadata/`` (e.g. ``fetch_gaps.json``)
        replace_product_ids: If set, keep existing gaps for other product_ids and replace
            only these (used for ``--product`` runs). If None, replace the whole file.
    """
    metadata_folder = company_folder / "metadata"
    ensure_directory(metadata_folder)
    path = gaps_path(company_folder, filename)

    kept: list[dict[str, Any]] = []
    if replace_product_ids is not None and path.exists():
        try:
            existing = load_json(path)
            for gap in existing.get("gaps") or []:
                if not isinstance(gap, dict):
                    continue
                pid = gap.get("product_id")
                if pid is None or str(pid) not in replace_product_ids:
                    kept.append(gap)
        except Exception:
            kept = []

    ordered = sorted(kept + list(gaps), key=_gap_sort_key)
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
