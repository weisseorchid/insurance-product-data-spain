"""Gemini -> Mistral fallback for analyze_products (offline: fake clients, no live calls)."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
from google.genai import errors as genai_errors
from pydantic import ValidationError

from insurance_product_data_sp.schemas import ProductAnalysis
from scripts.analyze_products import analyze_company_products
from scripts.analyze_products import main as analyze_main
from scripts.clients.gemini import GeminiClient
from scripts.clients.llm import (
    AnalysisRouter,
    ErrorKind,
    ProviderConfigError,
    build_router,
    classify_error,
)
from scripts.clients.mistral import DEFAULT_MISTRAL_MODEL, MistralClient

ANALYSIS_JSON = {
    "product_summary": {"product_type": "Hogar", "description_es": "x", "insurance_company": "Foo"},
    "obligations": {},
    "contract_terms": {"duration": "Anual", "renewal_type": "automatic"},
    "geographic_coverage": {"primary_territory": "Spain"},
}
ANALYSIS = ProductAnalysis.model_validate(ANALYSIS_JSON)


def gemini_error(code: int, status: str) -> genai_errors.APIError:
    cls = genai_errors.ServerError if code >= 500 else genai_errors.ClientError
    return cls(code, {"error": {"code": code, "message": status.lower(), "status": status}})


def validation_error() -> ValidationError:
    try:
        ProductAnalysis.model_validate({"invalid": "data"})
    except ValidationError as e:
        return e
    raise AssertionError("expected a ValidationError")


class FakeProvider:
    """Provider client double: returns ANALYSIS or raises the configured error."""

    def __init__(self, provider: str, model: str, error: BaseException | None = None):
        self.provider = provider
        self.model = model
        self.error = error
        self.calls = 0

    @staticmethod
    def compute_input_hash(markdown_paths: list[str]) -> str:
        return GeminiClient.compute_input_hash(markdown_paths)

    def analyze_product_documents(self, markdown_paths, product_context=None, document_names=None):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return ANALYSIS


@pytest.fixture(autouse=True)
def _no_real_keys(monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.delenv("MISTRAL_MODEL", raising=False)


@pytest.fixture
def company(tmp_path, monkeypatch):
    """A company folder with two products that each have one real markdown file."""
    folder = tmp_path / "company"
    for name in ("hogar", "auto"):
        (folder / "sources" / name).mkdir(parents=True)
        (folder / "sources" / name / "cg.md").write_text("# Condiciones\n\n" + "cobertura " * 50, encoding="utf-8")
    (folder / "index.json").write_text(
        json.dumps(
            [
                {
                    "products": [
                        {"product_name": "hogar", "product_id": "urn:X0001-01", "branches": ["09"]},
                        {"product_name": "auto", "product_id": "urn:X0001-02", "branches": ["03"]},
                    ]
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("scripts.analyze_products.find_company_folder", lambda key: folder)
    monkeypatch.setattr("scripts.analyze_products.find_company", lambda key: {"denomination": "Foo"})
    monkeypatch.setattr("scripts.analyze_products.company_display_name", lambda c: "Foo")
    return folder


def use_router(monkeypatch, *clients: FakeProvider, mode: str = "auto") -> None:
    monkeypatch.setattr(
        "scripts.analyze_products.build_router",
        lambda provider, gemini_factory=None: AnalysisRouter(list(clients), mode=mode),
    )


def provenance(company, product: str) -> dict:
    saved = json.loads((company / "analysis" / f"{product}.json").read_text(encoding="utf-8"))
    return saved["metadata"]["analysis_provenance"]


def last_run_entry(tmp_path) -> dict:
    lines = (tmp_path / "isolated-data" / "runs.jsonl").read_text(encoding="utf-8").splitlines()
    return json.loads(lines[-1])


# --- error classification -------------------------------------------------------------


@pytest.mark.parametrize(
    ("exc", "kind"),
    [
        (gemini_error(429, "RESOURCE_EXHAUSTED"), ErrorKind.RETRYABLE),
        (gemini_error(503, "UNAVAILABLE"), ErrorKind.RETRYABLE),
        (gemini_error(500, "INTERNAL"), ErrorKind.RETRYABLE),
        (gemini_error(504, "DEADLINE_EXCEEDED"), ErrorKind.RETRYABLE),
        (httpx.ReadTimeout("timed out"), ErrorKind.RETRYABLE),
        (httpx.ConnectError("refused"), ErrorKind.RETRYABLE),
        (TimeoutError(), ErrorKind.RETRYABLE),
        (validation_error(), ErrorKind.INVALID_OUTPUT),
        (ValueError("Gemini API returned None response text"), ErrorKind.INVALID_OUTPUT),
        (gemini_error(401, "UNAUTHENTICATED"), ErrorKind.AUTH),
        (gemini_error(403, "PERMISSION_DENIED"), ErrorKind.AUTH),
        (gemini_error(400, "INVALID_ARGUMENT"), ErrorKind.CONFIG),  # includes API_KEY_INVALID
        (gemini_error(404, "NOT_FOUND"), ErrorKind.CONFIG),  # unknown model
        (RuntimeError("boom"), ErrorKind.UNKNOWN),
    ],
)
def test_classify_error(exc, kind):
    assert classify_error(exc) is kind


def test_classify_mistral_status_codes():
    from mistralai.client.errors import SDKError

    def sdk_error(status: int) -> SDKError:
        return SDKError("err", httpx_response(status))

    assert classify_error(sdk_error(429)) is ErrorKind.RETRYABLE
    assert classify_error(sdk_error(502)) is ErrorKind.RETRYABLE
    assert classify_error(sdk_error(401)) is ErrorKind.AUTH


def httpx_response(status: int):
    import httpx2

    return httpx2.Response(status, text="{}", request=httpx2.Request("POST", "https://api.mistral.ai/v1/chat"))


# --- routing through analyze_company_products -----------------------------------------


def test_gemini_success_does_not_call_mistral(company, monkeypatch, tmp_path):
    gemini = FakeProvider("gemini", "gemini-test")
    mistral = FakeProvider("mistral", "mistral-test")
    use_router(monkeypatch, gemini, mistral)

    results = analyze_company_products("X0001", save_summary=False, force_reanalysis=True)

    assert all(r.success and r.provider == "gemini" for r in results)
    assert mistral.calls == 0
    prov = provenance(company, "hogar")
    assert prov["provider"] == "gemini"
    assert prov["model"] == "gemini-test"
    assert "fallback_reason" not in prov
    run = last_run_entry(tmp_path)
    assert run["script"] == "analyze_products"
    assert run["counts"]["by_provider_gemini"] == 2
    assert run["counts"]["fallbacks"] == 0


def test_retryable_gemini_error_falls_back_to_mistral(company, monkeypatch, tmp_path):
    gemini = FakeProvider("gemini", "gemini-test", error=gemini_error(503, "UNAVAILABLE"))
    mistral = FakeProvider("mistral", "mistral-test")
    use_router(monkeypatch, gemini, mistral)

    results = analyze_company_products("X0001", save_summary=False, force_reanalysis=True)

    assert all(r.success and r.provider == "mistral" for r in results)
    assert gemini.calls == 2 and mistral.calls == 2
    prov = provenance(company, "hogar")
    assert prov["provider"] == "mistral"
    assert prov["model"] == "mistral-test"
    assert prov["fallback_reason"].startswith("retryable: ServerError")
    run = last_run_entry(tmp_path)
    assert run["counts"]["by_provider_mistral"] == 2
    assert run["counts"]["fallbacks"] == 2
    assert run["details"]["fallbacks"][0]["from"] == "gemini"


def test_invalid_gemini_output_falls_back_to_mistral(company, monkeypatch):
    gemini = FakeProvider("gemini", "gemini-test", error=validation_error())
    mistral = FakeProvider("mistral", "mistral-test")
    use_router(monkeypatch, gemini, mistral)

    results = analyze_company_products("X0001", product_filter="hogar", save_summary=False, force_reanalysis=True)

    assert results[0].success and results[0].provider == "mistral"
    assert provenance(company, "hogar")["fallback_reason"].startswith("invalid_output")


def test_without_mistral_key_there_is_no_fallback(company, monkeypatch, tmp_path):
    mistral_factory = MagicMock(side_effect=AssertionError("Mistral must not be built without a key"))
    gemini = FakeProvider("gemini", "gemini-test", error=gemini_error(429, "RESOURCE_EXHAUSTED"))
    router = build_router("auto", gemini_factory=lambda: gemini, mistral_factory=mistral_factory)
    assert [c.provider for c in router.clients] == ["gemini"]
    monkeypatch.setattr("scripts.analyze_products.build_router", lambda provider, gemini_factory=None: router)

    results = analyze_company_products("X0001", save_summary=False, force_reanalysis=True)

    assert all(not r.success for r in results)
    assert "RESOURCE_EXHAUSTED" in (results[0].error or "")
    assert not (company / "analysis" / "hogar.json").exists()
    mistral_factory.assert_not_called()
    run = last_run_entry(tmp_path)
    assert run["counts"]["failed"] == 2
    assert run["details"]["failures"][0]["product_name"] == "hogar"


def test_auth_error_does_not_fall_back_and_stops_calling_gemini(company, monkeypatch):
    """Decision: a 401/403 (or 400/404 config error) is a setup problem, not an outage.

    Falling back would hide a broken GEMINI_API_KEY and silently switch every analysis to
    Mistral, so the product fails with a clear error and Gemini is not called again this run.
    """
    gemini = FakeProvider("gemini", "gemini-test", error=gemini_error(403, "PERMISSION_DENIED"))
    mistral = FakeProvider("mistral", "mistral-test")
    use_router(monkeypatch, gemini, mistral)

    results = analyze_company_products("X0001", save_summary=False, force_reanalysis=True)

    assert all(not r.success for r in results)
    assert "auth error" in (results[0].error or "")
    assert "--provider" in (results[0].error or "")
    assert gemini.calls == 1  # second product fails fast
    assert mistral.calls == 0


def test_provider_mistral_forces_mistral(company, monkeypatch, tmp_path):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key-not-real")
    gemini_factory = MagicMock(side_effect=AssertionError("Gemini must not be built"))
    mistral = FakeProvider("mistral", "mistral-test")
    monkeypatch.setattr("scripts.analyze_products.GeminiClient", gemini_factory)
    monkeypatch.setattr("scripts.clients.mistral.MistralClient", lambda: mistral)

    with patch("sys.argv", ["analyze_products", "-k", "X0001", "--provider", "mistral", "--force", "--no-summary"]):
        assert analyze_main() == 0

    assert mistral.calls == 2
    gemini_factory.assert_not_called()
    assert provenance(company, "hogar")["provider"] == "mistral"
    assert last_run_entry(tmp_path)["details"]["provider_mode"] == "mistral"


def test_provider_mistral_without_key_exits_2(company, monkeypatch):
    with patch("sys.argv", ["analyze_products", "-k", "X0001", "--provider", "mistral"]):
        assert analyze_main() == 2


def test_mistral_analysis_is_up_to_date_for_auto_mode(company, monkeypatch):
    """An analysis produced by the fallback is not re-run (and re-billed) on the next auto run."""
    gemini = FakeProvider("gemini", "gemini-test", error=gemini_error(503, "UNAVAILABLE"))
    mistral = FakeProvider("mistral", "mistral-test")
    use_router(monkeypatch, gemini, mistral)
    analyze_company_products("X0001", product_filter="hogar", save_summary=False, force_reanalysis=True)

    gemini.error = None
    results = analyze_company_products("X0001", product_filter="hogar", save_summary=False)
    assert results[0].skipped
    assert gemini.calls == 1


# --- real GeminiClient retries feed the router ------------------------------------------


def test_real_gemini_retries_are_exhausted_before_fallback(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text("# Doc\n\n" + "texto " * 50, encoding="utf-8")
    with patch("scripts.clients.gemini.genai.Client"):
        gemini = GeminiClient(model="gemini-test", max_retries=3)
    gemini.client.models.generate_content.side_effect = gemini_error(503, "UNAVAILABLE")  # type: ignore[attr-defined]
    mistral = FakeProvider("mistral", "mistral-test")

    with patch("scripts.clients.gemini.time.sleep") as sleep:
        routed = AnalysisRouter([gemini, mistral]).analyze_with_provenance([str(md)])

    assert gemini.client.models.generate_content.call_count == 3  # type: ignore[attr-defined]
    assert [c.args[0] for c in sleep.call_args_list] == [2.0, 4.0]  # existing backoff kept
    assert routed.provider == "mistral"
    assert routed.fallback_from == "gemini"


def test_build_router_missing_gemini_key_is_a_config_error(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key-not-real")

    def no_key():
        raise ValueError("Missing key inputs argument!")

    with pytest.raises(ProviderConfigError, match="Cannot configure gemini"):
        build_router("auto", gemini_factory=no_key, mistral_factory=lambda: FakeProvider("mistral", "m"))


# --- MistralClient ---------------------------------------------------------------------


def mistral_response(text: str | None):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def test_mistral_client_json_mode_and_validation(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text("# Doc\n\n" + "texto " * 50, encoding="utf-8")
    client = MistralClient(api_key="test-key-not-real")
    assert client.model == DEFAULT_MISTRAL_MODEL
    responses = [mistral_response('{"invalid": "data"}'), mistral_response(json.dumps(ANALYSIS_JSON))]
    complete = MagicMock(side_effect=responses)
    client.client = SimpleNamespace(chat=SimpleNamespace(complete=complete))

    with patch("scripts.clients.mistral.time.sleep") as sleep:
        analysis = client.analyze_product_documents([str(md)], {"product_name": "hogar", "company": "Foo"})

    assert analysis.product_summary.product_type == "Hogar"
    assert complete.call_count == 2
    sleep.assert_called_once_with(2.0)
    kwargs = complete.call_args.kwargs
    assert kwargs["response_format"] == {"type": "json_object"}
    assert kwargs["model"] == DEFAULT_MISTRAL_MODEL
    assert "JSON Schema" in kwargs["messages"][0]["content"]
    assert "Product name: hogar" in kwargs["messages"][1]["content"]


def test_mistral_model_from_env(monkeypatch):
    monkeypatch.setenv("MISTRAL_MODEL", "mistral-medium-latest")
    assert MistralClient(api_key="test-key-not-real").model == "mistral-medium-latest"


def test_mistral_client_does_not_retry_auth_errors(tmp_path):
    from mistralai.client.errors import SDKError

    md = tmp_path / "doc.md"
    md.write_text("# Doc\n\n" + "texto " * 50, encoding="utf-8")
    client = MistralClient(api_key="test-key-not-real")
    complete = MagicMock(side_effect=SDKError("Unauthorized", httpx_response(401)))
    client.client = SimpleNamespace(chat=SimpleNamespace(complete=complete))

    with patch("scripts.clients.mistral.time.sleep"), pytest.raises(SDKError):
        client.analyze_product_documents([str(md)])
    assert complete.call_count == 1


def test_mistral_client_requires_key():
    with pytest.raises(ValueError, match="MISTRAL_API_KEY"):
        MistralClient()
