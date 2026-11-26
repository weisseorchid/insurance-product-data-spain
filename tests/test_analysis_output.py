"""analyze_products must write schema v1 analyses (branches, quality_flags), never product_branch."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from insurance_product_data_sp.schemas import ProductAnalysis
from scripts.analyze_products import (
    analyze_single_product,
    get_product_branches,
    partition_usable_markdown,
    save_product_analysis,
)
from scripts.utils.document_store import MarkdownInput
from scripts.utils.document_validation import SHORT_BLOCK_PAGE_MAX_CHARS, is_block_page

ANALYSIS = ProductAnalysis.model_validate(
    {
        "product_summary": {"product_type": "Hogar", "description_es": "x", "insurance_company": "Foo"},
        "obligations": {},
        "contract_terms": {"duration": "Anual", "renewal_type": "automatic"},
        "geographic_coverage": {"primary_territory": "Spain"},
    }
)


class FakeClient(SimpleNamespace):
    model = "fake-model"

    def compute_input_hash(self, paths):
        return "hash"

    def analyze_product_documents(self, markdown_paths, product_context=None, document_names=None):
        self.last_paths = list(markdown_paths)
        return ANALYSIS


def test_get_product_branches_prefers_branches():
    assert get_product_branches({"branches": ["09"], "product_branch": "01"}) == ["09"]
    assert get_product_branches({"product_branch": "01"}) == ["01"]
    assert get_product_branches({"product_branch": ["05", "06"]}) == ["05", "06"]
    assert get_product_branches({}) == []


def test_saved_analysis_uses_branches_and_quality_flags(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text("content", encoding="utf-8")
    entry = {
        "product_id": "urn:X0001-01",
        "company_key": "X0001",
        "product_name": "hogar",
        "branches": ["09"],
        "source_url": "https://example.com/hogar",
    }
    out = save_product_analysis(tmp_path, entry, ANALYSIS, FakeClient(), [md], has_quality_issues=True)  # type: ignore[arg-type]
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["branches"] == ["09"]
    assert saved["company_key"] == "X0001"
    assert saved["source_url"] == "https://example.com/hogar"
    assert "product_branch" not in saved
    assert "source_urls" not in saved
    assert saved["metadata"]["quality_flags"] == {"has_known_quality_issues": True, "untrusted": True}


def test_partition_usable_markdown_drops_block_pages(tmp_path):
    good = tmp_path / "good.md"
    bad = tmp_path / "bad.md"
    good.write_text("# Seguro de Hogar\n\n" + "cobertura " * 40, encoding="utf-8")
    bad.write_text("# Pardon Our Interruption\n\nPlease stand by...\n", encoding="utf-8")
    usable, dropped = partition_usable_markdown(
        [MarkdownInput(good, "good.md"), MarkdownInput(bad, "bad.md")]
    )
    assert [i.name for i in usable] == ["good.md"]
    assert [i.name for i in dropped] == ["bad.md"]


def test_analyze_skips_client_when_only_block_pages(tmp_path, monkeypatch):
    company = tmp_path / "company"
    sources = company / "sources" / "hogar"
    sources.mkdir(parents=True)
    (sources / "block.md").write_text(
        "# Pardon Our Interruption\n\nCloudflare Ray ID: abc\nPlease stand by\n",
        encoding="utf-8",
    )
    client = FakeClient()
    client.analyze_product_documents = MagicMock(side_effect=AssertionError("must not call Gemini"))
    result = analyze_single_product(
        client=client,  # type: ignore[arg-type]
        company_folder=company,
        product_entry={"product_name": "hogar", "product_id": "urn:X0001-01", "branches": ["09"]},
        company_name="Foo",
        skip_if_exists=False,
    )
    assert result.success is False
    assert result.error == "no_usable_documents"
    assert result.dropped_inputs and len(result.dropped_inputs) == 1


def test_analyze_omits_block_pages_when_mixed(tmp_path):
    company = tmp_path / "company"
    sources = company / "sources" / "hogar"
    sources.mkdir(parents=True)
    (sources / "real.md").write_text("# Condiciones\n\n" + "cobertura " * 50, encoding="utf-8")
    (sources / "block.md").write_text(
        "# Pardon Our Interruption\n\nPlease stand by while we check your browser\n",
        encoding="utf-8",
    )
    client = FakeClient()
    result = analyze_single_product(
        client=client,  # type: ignore[arg-type]
        company_folder=company,
        product_entry={"product_name": "hogar", "product_id": "urn:X0001-01", "branches": ["09"]},
        company_name="Foo",
        skip_if_exists=False,
    )
    assert result.success is True
    assert [i.name for i in (result.usable_inputs or [])] == ["real.md"]
    assert [i.name for i in (result.dropped_inputs or [])] == ["block.md"]
    assert client.last_paths == [str(sources / "real.md")]


def test_long_policy_mentioning_cloudflare_in_body_is_not_block_page():
    body = "# Condiciones Generales\n\n" + ("cobertura " * 400) + "\n\nCloudflare is a CDN used by some sites.\n"
    assert len(body) > SHORT_BLOCK_PAGE_MAX_CHARS
    assert is_block_page(body) is False
    # Same phrase in a short interstitial still counts
    assert is_block_page("# Just a moment\n\nCloudflare Ray ID: 1\n") is True
