"""documents.jsonl + cache as the source of truth for analysis and conversion."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts import analyze_products, process_pdfs
from scripts.utils.document_cache import DocumentCache
from scripts.utils.document_store import load_documents, markdown_inputs_from_documents, upsert_document

PDF = b"%PDF-1.4\n" + b"x" * 200


@pytest.fixture
def cache(tmp_path, monkeypatch):
    root = tmp_path / "cache"
    monkeypatch.setenv("INSURANCE_DOCS_CACHE", str(root))
    return DocumentCache(root)


def _write_documents(folder: Path, records: list[dict]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "documents.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def test_upsert_replaces_same_product_and_filename():
    records = [{"product_id": "p", "filename": "a.pdf", "pdf_sha256": "old"}]
    records = upsert_document(records, {"product_id": "p", "filename": "a.pdf", "pdf_sha256": "new"})
    records = upsert_document(records, {"product_id": "q", "filename": "a.pdf", "pdf_sha256": "new"})
    assert [(r["product_id"], r["pdf_sha256"]) for r in records] == [("p", "new"), ("q", "new")]


def test_analysis_reads_markdown_from_cache(tmp_path, cache):
    md = cache.store_markdown("# IPID\n" + "contenido " * 30)
    company = tmp_path / "company"
    _write_documents(
        company,
        [
            {
                "product_id": "urn:X0001-01",
                "product_name": "hogar",
                "filename": "IPID-hogar.pdf",
                "doc_type": "ipid",
                "pdf_sha256": "p1",
                "markdown_sha256": md.sha256,
            },
            {
                "product_id": "urn:X0001-01",
                "product_name": "hogar",
                "filename": "CG-hogar.pdf",
                "doc_type": "condiciones_generales",
                "pdf_sha256": "p2",
                "markdown_sha256": "f" * 64,
            },
            {
                "product_id": "urn:X0001-02",
                "product_name": "auto",
                "filename": "x.pdf",
                "pdf_sha256": "p3",
                "markdown_sha256": md.sha256,
            },
        ],
    )
    found, missing = markdown_inputs_from_documents(company, "hogar", cache)
    assert [(i.path, i.name) for i in found] == [(md.cache_path, "IPID-hogar.md")]
    assert [r["filename"] for r in missing] == ["CG-hogar.pdf"]
    inputs = analyze_products.get_product_markdown_inputs(company, "hogar")
    assert [i.name for i in inputs] == ["IPID-hogar.md"]


def test_analysis_prefers_legacy_sources_folder(tmp_path, cache):
    company = tmp_path / "company"
    legacy = company / "sources" / "hogar"
    legacy.mkdir(parents=True)
    (legacy / "a.md").write_text("legacy", encoding="utf-8")
    assert analyze_products.get_product_markdown_files(company, "hogar") == [legacy / "a.md"]


def test_process_pdfs_converts_cached_pdfs_and_updates_documents(tmp_path, cache):
    pdf_path = cache.get_pdf_path("a" * 64)
    pdf_path.parent.mkdir(parents=True)
    pdf_path.write_bytes(PDF)
    company = tmp_path / "company"
    _write_documents(
        company,
        [
            {
                "product_id": "u1",
                "product_name": "hogar",
                "filename": "a.pdf",
                "doc_type": "ipid",
                "pdf_sha256": "a" * 64,
                "markdown_sha256": "stale",
            },
            {
                "product_id": "u2",
                "product_name": "auto",
                "filename": "a.pdf",
                "doc_type": "ipid",
                "pdf_sha256": "a" * 64,
                "markdown_sha256": "stale",
            },
        ],
    )
    with patch("scripts.utils.pdf_processing.MarkItDown") as mock:
        result = MagicMock()
        result.text_content = "Texto del IPID " * 20
        mock.return_value.convert.return_value = result
        results = process_pdfs.process_cached_documents(company, company_key="X0001", cache=cache)
        assert mock.return_value.convert.call_count == 1  # shared PDF converted once
    assert sum(len(v) for v in results.values()) == 1
    records = load_documents(company)
    assert {r["markdown_sha256"] for r in records} != {"stale"}
    assert len({r["markdown_sha256"] for r in records}) == 1
    assert cache.get_markdown(records[0]["markdown_sha256"]).exists
