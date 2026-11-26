"""documents.jsonl + content-addressed cache: the source of truth for product documents.

Each company folder has a committed ``documents.jsonl`` (one record per product
document, provenance only) while the PDFs and their markdown live in the
gitignored cache (``.cache/insurance-docs/<sha[:2]>/<sha>.{pdf,md}``, see
``DocumentCache``). This module reads/writes those records and converts cached
PDFs to validated markdown, so fetching, conversion and analysis all share it.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any, NamedTuple

from scripts.utils.document_cache import DocumentCache
from scripts.utils.jsonl import load_jsonl, save_jsonl
from scripts.utils.pdf_processing import convert_pdf_to_markdown

DOCUMENTS_FILENAME = "documents.jsonl"


def documents_path(company_folder: Path) -> Path:
    return company_folder / DOCUMENTS_FILENAME


def document_sort_key(record: dict[str, Any]) -> tuple[str, str, str]:
    """Sort order used for documents.jsonl (same as backfill_documents_metadata)."""
    return (str(record.get("product_name", "")), str(record.get("doc_type", "")), str(record.get("filename", "")))


def load_documents(company_folder: Path) -> list[dict[str, Any]]:
    path = documents_path(company_folder)
    return load_jsonl(path) if path.exists() else []


def save_documents(company_folder: Path, records: Iterable[dict[str, Any]]) -> None:
    save_jsonl(list(records), documents_path(company_folder), sort_key=document_sort_key)


def upsert_document(records: list[dict[str, Any]], record: dict[str, Any]) -> list[dict[str, Any]]:
    """Replace the record with the same (product_id, filename), or append it."""
    key = (record.get("product_id"), record.get("filename"))
    kept = [r for r in records if (r.get("product_id"), r.get("filename")) != key]
    kept.append(record)
    return kept


class MarkdownInput(NamedTuple):
    """A markdown document to analyze: where it is and the name to show for it."""

    path: Path
    name: str


def markdown_inputs_from_documents(
    company_folder: Path,
    product_name: str,
    cache: DocumentCache | None = None,
) -> tuple[list[MarkdownInput], list[dict[str, Any]]]:
    """Resolve a product's markdown from documents.jsonl + cache.

    Returns:
        (inputs found in the cache, documents.jsonl records whose markdown is missing from the cache)
    """
    cache = cache or DocumentCache()
    found: list[MarkdownInput] = []
    missing: list[dict[str, Any]] = []
    for record in sorted(load_documents(company_folder), key=document_sort_key):
        if record.get("product_name") != product_name:
            continue
        md_hash = record.get("markdown_sha256")
        cached = cache.get_markdown(md_hash) if md_hash else None
        if cached and cached.exists:
            found.append(MarkdownInput(cached.cache_path, Path(str(record.get("filename", md_hash))).stem + ".md"))
        else:
            missing.append(record)
    return found, missing


class ConversionOutcome(NamedTuple):
    success: bool
    markdown_sha256: str | None
    error: str | None = None
    validation_failed: bool = False


def convert_cached_pdf(pdf_sha256: str, cache: DocumentCache | None = None) -> ConversionOutcome:
    """Convert a cached PDF to markdown, validate it and store the markdown in the cache."""
    cache = cache or DocumentCache()
    pdf = cache.get_pdf(pdf_sha256)
    if not pdf.exists:
        return ConversionOutcome(False, None, f"PDF {pdf_sha256} not in cache {cache.cache_root}")
    result = convert_pdf_to_markdown(pdf.cache_path, validate=True)
    if not result.success:
        return ConversionOutcome(False, result.markdown_sha256, result.error, result.validation_failed)
    stored = cache.store_markdown(result.markdown_content)
    return ConversionOutcome(True, stored.sha256)
