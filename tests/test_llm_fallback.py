"""Gemini -> Mistral fallback for analyze_products (offline: fake clients, no live calls)."""

import json
from types import SimpleNamespace
from typing import cast
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

    def __init__(self, provider: str, model: str, error: BaseException | list | None = None):
        self.provider = provider
        self.model = model
        self.error = error
        self.calls = 0

    @staticmethod
    def compute_input_hash(markdown_paths: list[str]) -> str:
        return GeminiClient.compute_input_hash(markdown_paths)

    def analyze_product_documents(self, markdown_paths, product_context=None, document_names=None):
        self.calls += 1
        error = self.error.pop(0) if isinstance(self.error, list) else self.error
        if error is not None:
            raise error
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


def mistral_error(status: int):
    from mistralai.client.errors import SDKError

    return SDKError(f"Mistral HTTP {status}", httpx_response(status))


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


def test_fallback_400_fails_only_that_product(company, monkeypatch):
    """Review #1: a request-scoped Mistral 400/422 must not disable the fallback for later products."""
    gemini = FakeProvider("gemini", "gemini-test", error=gemini_error(503, "UNAVAILABLE"))
    mistral = FakeProvider("mistral", "mistral-test", error=[mistral_error(400), None])
    use_router(monkeypatch, gemini, mistral)

    results = analyze_company_products("X0001", save_summary=False, force_reanalysis=True)
    by_name = {r.product_name: r for r in results}

    assert not by_name["hogar"].success
    assert "mistral config error" in (by_name["hogar"].error or "")
    assert by_name["auto"].success and by_name["auto"].provider == "mistral"
    assert provenance(company, "auto")["provider"] == "mistral"
    assert mistral.calls == 2 and gemini.calls == 2


@pytest.mark.parametrize("status", [401, 403, 404])
def test_fallback_auth_or_unknown_model_latches(company, monkeypatch, status):
    """A broken fallback key/model (401/403/404) disables the fallback for the rest of the run."""
    gemini = FakeProvider("gemini", "gemini-test", error=gemini_error(503, "UNAVAILABLE"))
    mistral = FakeProvider("mistral", "mistral-test", error=[mistral_error(status), None])
    use_router(monkeypatch, gemini, mistral)

    results = analyze_company_products("X0001", save_summary=False, force_reanalysis=True)

    assert all(not r.success for r in results)
    assert mistral.calls == 1  # second product fails fast without calling Mistral
    assert gemini.calls == 2  # Gemini (retryable 503) is still tried for each product


def test_unknown_gemini_error_fails_without_fallback_or_latch(company, monkeypatch):
    """UNKNOWN errors fail the product, never fall back, and do not disable Gemini."""
    gemini = FakeProvider("gemini", "gemini-test", error=RuntimeError("boom"))
    mistral = FakeProvider("mistral", "mistral-test")
    use_router(monkeypatch, gemini, mistral)

    results = analyze_company_products("X0001", save_summary=False, force_reanalysis=True)

    assert all(not r.success for r in results)
    assert all("boom" in (r.error or "") for r in results)
    assert mistral.calls == 0
    assert gemini.calls == 2


def test_fallback_failure_reports_the_last_provider_error(company, monkeypatch, tmp_path):
    """If Mistral also fails after Gemini's retries, the product fails with Mistral's error."""
    gemini = FakeProvider("gemini", "gemini-test", error=gemini_error(503, "UNAVAILABLE"))
    mistral = FakeProvider("mistral", "mistral-test", error=mistral_error(502))
    use_router(monkeypatch, gemini, mistral)

    results = analyze_company_products("X0001", product_filter="hogar", save_summary=False, force_reanalysis=True)

    assert not results[0].success
    assert "Mistral HTTP 502" in (results[0].error or "")
    assert not (company / "analysis" / "hogar.json").exists()
    assert mistral.calls == 1
    run = last_run_entry(tmp_path)
    assert run["counts"]["failed"] == 1
    assert run["counts"]["fallbacks"] == 0


def test_analyze_run_log_matches_data_integrity_schema(company, monkeypatch, tmp_path):
    """The analyze_products runs.jsonl line passes the same check CI runs on data/runs.jsonl."""
    from scripts.ci.check_data_integrity import validate_jsonl_file

    gemini = FakeProvider("gemini", "gemini-test", error=[gemini_error(503, "UNAVAILABLE"), None])
    mistral = FakeProvider("mistral", "mistral-test")
    use_router(monkeypatch, gemini, mistral)
    analyze_company_products("X0001", save_summary=False, force_reanalysis=True)
    analyze_company_products("X0001", save_summary=False)

    runs_path = tmp_path / "isolated-data" / "runs.jsonl"
    assert len(runs_path.read_text(encoding="utf-8").splitlines()) == 2
    errors, _warnings = validate_jsonl_file(runs_path, "started_at", ["script", "started_at"])
    assert errors == []


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


def test_mistral_analysis_is_up_to_date_for_auto_mode(company, monkeypatch, tmp_path):
    """An analysis produced by the fallback is not re-run (and re-billed) on the next auto run."""
    gemini = FakeProvider("gemini", "gemini-test", error=gemini_error(503, "UNAVAILABLE"))
    mistral = FakeProvider("mistral", "mistral-test")
    use_router(monkeypatch, gemini, mistral)
    analyze_company_products("X0001", product_filter="hogar", save_summary=False, force_reanalysis=True)

    gemini.error = None
    results = analyze_company_products("X0001", product_filter="hogar", save_summary=False)
    assert results[0].skipped
    assert gemini.calls == 1
    run = last_run_entry(tmp_path)
    assert run["counts"]["analyzed"] == 0
    assert run["counts"]["skipped"] == 1
    assert run["counts"]["failed"] == 0
    assert run["counts"]["fallbacks"] == 0
    assert run["details"]["failures"] == []
    assert run["details"]["fallbacks"] == []

    # Review #2: a Gemini-only chain does not accept the Mistral model and redoes the analysis
    use_router(monkeypatch, gemini, mode="gemini")
    results = analyze_company_products("X0001", product_filter="hogar", save_summary=False)
    assert not results[0].skipped
    assert results[0].success and results[0].provider == "gemini"
    assert gemini.calls == 2
    assert provenance(company, "hogar")["provider"] == "gemini"


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


@pytest.mark.parametrize("first", [(401, "UNAUTHENTICATED"), (400, "INVALID_ARGUMENT")])
def test_gemini_auth_or_config_error_is_not_hidden_by_a_later_503(tmp_path, first):
    """Review #5: a 401/400 on attempt 1 is raised at once, not retried until a 503 masks it."""
    md = tmp_path / "doc.md"
    md.write_text("# Doc\n\n" + "texto " * 50, encoding="utf-8")
    with patch("scripts.clients.gemini.genai.Client"):
        gemini = GeminiClient(model="gemini-test", max_retries=3)
    generate = cast(MagicMock, gemini.client.models.generate_content)
    generate.side_effect = [gemini_error(*first), gemini_error(503, "UNAVAILABLE"), gemini_error(503, "UNAVAILABLE")]
    mistral = FakeProvider("mistral", "mistral-test")
    router = AnalysisRouter([gemini, mistral])

    with patch("scripts.clients.gemini.time.sleep") as sleep, pytest.raises(ProviderConfigError):
        router.analyze_with_provenance([str(md)])

    assert generate.call_count == 1
    sleep.assert_not_called()
    assert mistral.calls == 0
    assert "gemini" in router._disabled
    with pytest.raises(ProviderConfigError):  # next product: Gemini is not called again
        router.analyze_with_provenance([str(md)])
    assert generate.call_count == 1


def test_build_router_chain_by_mode(monkeypatch):
    """Review #8: with a key, auto adds Mistral after Gemini; --provider gemini never builds Mistral."""
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key-not-real")
    gemini_factory = MagicMock(side_effect=lambda: FakeProvider("gemini", "gemini-test"))
    mistral_factory = MagicMock(side_effect=lambda: FakeProvider("mistral", "mistral-test"))

    auto = build_router("auto", gemini_factory=gemini_factory, mistral_factory=mistral_factory)
    assert [c.provider for c in auto.clients] == ["gemini", "mistral"]
    assert auto.accepted_models == {"gemini-test", "mistral-test"}
    mistral_factory.assert_called_once()

    mistral_factory.reset_mock()
    gemini_only = build_router("gemini", gemini_factory=gemini_factory, mistral_factory=mistral_factory)
    assert [c.provider for c in gemini_only.clients] == ["gemini"]
    mistral_factory.assert_not_called()

    mistral_only = build_router("mistral", gemini_factory=gemini_factory, mistral_factory=mistral_factory)
    assert [c.provider for c in mistral_only.clients] == ["mistral"]
    assert gemini_factory.call_count == 2  # auto + gemini, not mistral


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


# --- partial-run summary merge and index analysis_path --------------------------------


def _summary(company):
    return json.loads((company / "metadata" / "analysis_summary.json").read_text(encoding="utf-8"))


def _index_products(company):
    return json.loads((company / "index.json").read_text(encoding="utf-8"))[0]["products"]


def _by_name(products):
    return {p["product_name"]: p for p in products}


def test_partial_run_merges_into_existing_analysis_summary(company, monkeypatch):
    """A --product run upserts that product and keeps the other summary entries."""
    gemini = FakeProvider("gemini", "gemini-test")
    use_router(monkeypatch, gemini)
    analyze_company_products("X0001", force_reanalysis=True)

    first = _summary(company)
    assert first["summary"]["total_products"] == 2
    assert first["summary"]["successful"] == 2
    assert first["summary"]["by_provider_gemini"] == 2
    assert first["summary"]["fallbacks"] == 0
    first_auto = _by_name(first["products"])["auto"]

    mistral = FakeProvider("mistral", "mistral-test")
    use_router(monkeypatch, mistral, mode="mistral")
    analyze_company_products(
        "X0001",
        product_filter="hogar",
        force_reanalysis=True,
        provider="mistral",
    )

    merged = _summary(company)
    by_name = _by_name(merged["products"])
    assert set(by_name) == {"hogar", "auto"}
    assert by_name["hogar"]["success"] is True
    assert by_name["hogar"]["provider"] == "mistral"
    assert by_name["hogar"]["model"] == "mistral-test"
    assert by_name["auto"] == first_auto
    assert merged["summary"]["total_products"] == 2
    assert merged["summary"]["successful"] == 2
    assert merged["summary"]["failed"] == 0
    assert merged["summary"]["skipped"] == 0
    assert merged["summary"]["by_provider_gemini"] == 1
    assert merged["summary"]["by_provider_mistral"] == 1
    assert merged["summary"]["fallbacks"] == 0

    # Idempotent: a second --product run keeps both entries and the same counts.
    analyze_company_products(
        "X0001",
        product_filter="hogar",
        force_reanalysis=True,
        provider="mistral",
    )
    again = _summary(company)
    assert again["summary"] == merged["summary"]
    assert _by_name(again["products"]).keys() == by_name.keys()
    assert _by_name(again["products"])["auto"] == first_auto
    assert _by_name(again["products"])["hogar"]["provider"] == "mistral"


def test_successful_analysis_sets_analysis_path_in_index(company, monkeypatch):
    """Full and --product runs set analysis_path; the write is idempotent."""
    gemini = FakeProvider("gemini", "gemini-test")
    use_router(monkeypatch, gemini)
    analyze_company_products("X0001", product_filter="hogar", force_reanalysis=True)

    products = _by_name(_index_products(company))
    assert products["hogar"]["analysis_path"] == "analysis/hogar.json"
    assert "analysis_path" not in products["auto"]

    analyze_company_products("X0001", force_reanalysis=True)
    products = _by_name(_index_products(company))
    assert products["hogar"]["analysis_path"] == "analysis/hogar.json"
    assert products["auto"]["analysis_path"] == "analysis/auto.json"

    # Already set to the same value: a later skip still leaves it in place.
    analyze_company_products("X0001")
    products = _by_name(_index_products(company))
    assert products["hogar"]["analysis_path"] == "analysis/hogar.json"
    assert products["auto"]["analysis_path"] == "analysis/auto.json"


def test_failed_product_keeps_old_summary_entry_and_does_not_set_analysis_path(company, monkeypatch):
    """A failed --product run must not drop the old summary row or set analysis_path."""
    gemini = FakeProvider("gemini", "gemini-test")
    use_router(monkeypatch, gemini)
    analyze_company_products("X0001", force_reanalysis=True)

    # Simulate the pre-fix state: summary is complete, but analysis_path was never written.
    index = json.loads((company / "index.json").read_text(encoding="utf-8"))
    for product in index[0]["products"]:
        if product["product_name"] == "hogar":
            product["analysis_path"] = None
    (company / "index.json").write_text(json.dumps(index), encoding="utf-8")
    (company / "analysis" / "hogar.json").unlink()

    before = _summary(company)
    old_hogar = _by_name(before["products"])["hogar"]
    old_auto = _by_name(before["products"])["auto"]
    assert old_hogar["success"] is True

    failing = FakeProvider("gemini", "gemini-test", error=gemini_error(503, "UNAVAILABLE"))
    use_router(monkeypatch, failing)
    results = analyze_company_products(
        "X0001",
        product_filter="hogar",
        force_reanalysis=True,
    )
    assert results[0].success is False
    assert not (company / "analysis" / "hogar.json").exists()

    after = _summary(company)
    by_name = _by_name(after["products"])
    assert set(by_name) == {"hogar", "auto"}
    assert by_name["hogar"] == old_hogar
    assert by_name["auto"] == old_auto
    assert after["summary"]["total_products"] == 2
    assert after["summary"]["successful"] == 2
    assert after["summary"]["failed"] == 0
    assert after["summary"]["by_provider_gemini"] == 2

    products = _by_name(_index_products(company))
    assert products["hogar"]["analysis_path"] is None
    assert products["auto"]["analysis_path"] == "analysis/auto.json"
