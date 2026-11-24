"""analyze_products must write schema v1 analyses (branches, quality_flags), never product_branch."""

import json
from types import SimpleNamespace

from insurance_product_data_sp.schemas import ProductAnalysis
from scripts.analyze_products import get_product_branches, save_product_analysis

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
