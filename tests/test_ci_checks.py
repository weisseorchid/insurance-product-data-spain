"""Tests for the baseline-gated product quality checks in scripts/ci/check_data_integrity.py."""

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
MUTUA_BLOCK_HASH = "9c2fcc5d899fb2a6196360ee14dfbff58676911c57fda1b59578702c341b0ff4"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "check_data_integrity", REPO_ROOT / "scripts/ci/check_data_integrity.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cdi = _load_module()

GOOD_ANALYSIS = {
    "product_id": "urn:X0001-01",
    "company_key": "X0001",
    "product_name": "hogar",
    "branches": ["09"],
    "metadata": {"quality_flags": {"has_known_quality_issues": False, "untrusted": False}},
}


def _make_company(root: Path, *, branches=("09",), analysis=None, documents=()):
    company = root / "data" / "products_by_insurance_company" / "foo"
    (company / "analysis").mkdir(parents=True)
    index = [{"company_key": "X0001", "products": [{"product_id": "urn:X0001-01", "branches": list(branches)}]}]
    (company / "index.json").write_text(json.dumps(index), encoding="utf-8")
    (company / "analysis" / "hogar.json").write_text(json.dumps(analysis or GOOD_ANALYSIS), encoding="utf-8")
    (company / "documents.jsonl").write_text("".join(json.dumps(d) + "\n" for d in documents), encoding="utf-8")
    return root / "data" / "products_by_insurance_company"


def _collect(root, products_dir, known=None):
    return cdi.collect_product_quality_issues(products_dir, root, {"00", "01", "09"}, known or {})


def test_clean_company_has_no_issues(tmp_path):
    products = _make_company(tmp_path)
    assert _collect(tmp_path, products) == []


def test_invalid_branch_code_in_index(tmp_path):
    products = _make_company(tmp_path, branches=("09", "21"))
    issues = _collect(tmp_path, products)
    assert [(i["check"], i["value"]) for i in issues] == [("invalid_branch_code", "21")]


def test_deprecated_product_branch_and_its_code(tmp_path):
    analysis = {**GOOD_ANALYSIS, "product_branch": "21"}
    del analysis["branches"]
    products = _make_company(tmp_path, analysis=analysis)
    checks = sorted((i["check"], i["value"]) for i in _collect(tmp_path, products))
    assert checks == [("deprecated_product_branch", "-"), ("invalid_branch_code", "21")]


@pytest.mark.parametrize(
    ("metadata", "expected_values"),
    [
        ({}, ["-"]),
        ({"quality_flags": {"untrusted": True}}, ["has_known_quality_issues"]),
        ({"quality_flags": {"untrusted": "yes", "has_known_quality_issues": False}}, ["untrusted"]),
    ],
)
def test_quality_flags_required(tmp_path, metadata, expected_values):
    products = _make_company(tmp_path, analysis={**GOOD_ANALYSIS, "metadata": metadata})
    issues = _collect(tmp_path, products)
    assert [i["check"] for i in issues] == ["missing_quality_flags"] * len(expected_values)
    assert [i["value"] for i in issues] == expected_values


def test_block_pages_detected_from_documents_jsonl(tmp_path):
    docs = [
        {"product_id": "urn:X0001-01", "filename": "a.pdf", "pdf_sha256": "p1", "markdown_sha256": MUTUA_BLOCK_HASH},
        {"product_id": "urn:X0001-01", "filename": "b.pdf", "pdf_sha256": "p2", "markdown_sha256": MUTUA_BLOCK_HASH},
        {"product_id": "urn:X0001-01", "filename": "c.pdf", "pdf_sha256": "p3", "markdown_sha256": "ok"},
    ]
    products = _make_company(tmp_path, documents=docs)
    issues = _collect(tmp_path, products, known={MUTUA_BLOCK_HASH: {"reason": "Cloudflare block page"}})
    checks = sorted((i["check"], i["item"]) for i in issues)
    assert checks == [
        ("block_page_document", "urn:X0001-01/a.pdf"),
        ("block_page_document", "urn:X0001-01/b.pdf"),
        ("duplicate_markdown_hash", "-"),
    ]


def test_duplicate_markdown_hash_without_known_hash(tmp_path):
    docs = [
        {"product_id": "u", "filename": "a.pdf", "pdf_sha256": "p1", "markdown_sha256": "same"},
        {"product_id": "u", "filename": "b.pdf", "pdf_sha256": "p2", "markdown_sha256": "same"},
    ]
    products = _make_company(tmp_path, documents=docs)
    assert [i["check"] for i in _collect(tmp_path, products)] == ["duplicate_markdown_hash"]


def test_baseline_only_new_issues_fail():
    known = cdi._issue("invalid_branch_code", "f", "p", "21", "d")
    new = cdi._issue("invalid_branch_code", "f", "p", "22", "d")
    stale = cdi._issue("missing_quality_flags", "g", "p", "-", "d")
    new_issues, stale_issues = cdi.compare_with_baseline([known, new], [known, stale])
    assert new_issues == [new]
    assert stale_issues == [stale]


def test_baseline_ignores_detail_text():
    a = cdi._issue("invalid_branch_code", "f", "p", "21", "old wording")
    b = cdi._issue("invalid_branch_code", "f", "p", "21", "new wording")
    assert cdi.compare_with_baseline([b], [a]) == ([], [])


def test_write_baseline_is_sorted_and_deduplicated(tmp_path):
    path = tmp_path / "known.jsonl"
    i1 = cdi._issue("b", "f", "p", "-", "d")
    i2 = cdi._issue("a", "f", "p", "-", "d")
    cdi.write_baseline([i1, i2, i1], path)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["check"] for line in lines] == ["a", "b"]


def test_committed_baseline_matches_repo_exactly():
    """The committed baseline must list exactly the current violations (no new, no stale)."""
    errors, warnings = cdi.run_product_quality_checks(REPO_ROOT)
    assert errors == []
    assert not [w for w in warnings if w.startswith("Resolved")]


def test_mutua_block_hash_is_known():
    assert MUTUA_BLOCK_HASH in cdi.load_known_block_page_hashes()
