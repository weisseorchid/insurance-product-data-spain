"""Offline tests for scripts/fetch_product_documents.py (all HTTP is mocked)."""

import base64
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from scripts import fetch_product_documents as fpd
from scripts.utils.document_cache import DocumentCache
from tests.test_source_manifest import MAPFRE_RECORDS, write_manifest

API = fpd.MAPFRE_DOCPRECON_API_BASE
PDF_A = b"%PDF-1.7\n" + b"A" * 3000 + b"\n%%EOF"
PDF_B = b"%PDF-1.4\n" + b"B" * 500 + b"\n%%EOF"
CLOUDFLARE = b"<html><title>Just a moment...</title>Checking your browser. Cloudflare Ray ID: 1</html>"


@dataclass
class Resp:
    status_code: int = 200
    content: bytes = b""
    headers: dict = field(default_factory=dict)


class FakeSession:
    """Routes (method, url) to queued responses; records every call."""

    def __init__(self, routes: dict[tuple[str, str], Any]):
        self.routes = {k: (v if isinstance(v, list) else [v]) for k, v in routes.items()}
        self.calls: list[tuple[str, str, dict]] = []

    def request(self, method: str, url: str, **kwargs: Any):
        self.calls.append((method, url, kwargs))
        queue = self.routes.get((method, url))
        if queue is None:
            return Resp(404)
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        return item


class FakeClock:
    def __init__(self):
        self.now = 1000.0
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def make_fetcher(routes, delay=3.0, max_retries=2):
    clock = FakeClock()
    session = FakeSession(routes)
    fetcher = fpd.PoliteFetcher(
        session=session, delay=delay, max_retries=max_retries, backoff=1.0, clock=clock.time, sleep=clock.sleep
    )
    return fetcher, session, clock


ROBOTS_OK = Resp(200, b"User-agent: *\nDisallow: /private/\n")


@pytest.fixture
def mock_markitdown():
    """Markdown derived from the PDF bytes so different PDFs give different markdown."""
    with patch("scripts.utils.pdf_processing.MarkItDown") as mock:

        def convert(path):
            data = Path(path).read_bytes()
            result = MagicMock()
            result.text_content = f"Condiciones del seguro {len(data)} bytes. " + "texto " * 40
            return result

        mock.return_value.convert.side_effect = convert
        yield mock


# -- PoliteFetcher -------------------------------------------------------------


def test_honest_user_agent_and_per_host_rate_limit():
    url1, url2 = "https://ins.example/a.pdf", "https://ins.example/b.pdf"
    fetcher, session, clock = make_fetcher(
        {
            ("GET", "https://ins.example/robots.txt"): ROBOTS_OK,
            ("GET", url1): Resp(200, PDF_A),
            ("GET", url2): Resp(200, PDF_B),
        }
    )
    assert fetcher.get_pdf(url1) == PDF_A
    assert fetcher.get_pdf(url2) == PDF_B
    assert [c[1] for c in session.calls] == ["https://ins.example/robots.txt", url1, url2]
    for _, _, kwargs in session.calls:
        assert kwargs["headers"]["User-Agent"] == fpd.USER_AGENT
        assert "Mozilla" not in kwargs["headers"]["User-Agent"]
        assert kwargs["allow_redirects"] is False
    assert clock.sleeps == [3.0, 3.0]  # one wait before each request after the first on this host


def test_minimum_delay_enforced():
    with pytest.raises(ValueError):
        fpd.PoliteFetcher(session=FakeSession({}), delay=0.2)


def test_robots_disallow_skips_url():
    url = "https://ins.example/private/doc.pdf"
    fetcher, session, _ = make_fetcher({("GET", "https://ins.example/robots.txt"): ROBOTS_OK})
    with pytest.raises(fpd.FetchFailed) as exc:
        fetcher.get_pdf(url)
    assert exc.value.reason == "robots_disallowed"
    assert [c[1] for c in session.calls] == ["https://ins.example/robots.txt"]


@pytest.mark.parametrize(("status", "allowed"), [(404, True), (403, False), (503, False)])
def test_robots_status_policy(status, allowed):
    fetcher, _, _ = make_fetcher({("GET", "https://ins.example/robots.txt"): Resp(status)}, max_retries=0)
    assert fetcher.allowed("https://ins.example/doc.pdf") is allowed


def test_crawl_delay_respected():
    url1, url2 = "https://ins.example/a.pdf", "https://ins.example/b.pdf"
    robots = Resp(200, b"User-agent: *\nCrawl-delay: 10\n")
    fetcher, _, clock = make_fetcher(
        {
            ("GET", "https://ins.example/robots.txt"): robots,
            ("GET", url1): Resp(200, PDF_A),
            ("GET", url2): Resp(200, PDF_A),
        }
    )
    fetcher.get_pdf(url1)
    fetcher.get_pdf(url2)
    assert clock.sleeps[-1] == 10.0


def test_retries_only_on_5xx_with_backoff():
    url = "https://ins.example/a.pdf"
    fetcher, session, clock = make_fetcher(
        {("GET", "https://ins.example/robots.txt"): ROBOTS_OK, ("GET", url): [Resp(503), Resp(502), Resp(200, PDF_A)]}
    )
    assert fetcher.get_pdf(url) == PDF_A
    assert len(session.calls) == 4
    assert 1.0 in clock.sleeps and 2.0 in clock.sleeps  # exponential backoff


def test_retries_on_timeout_then_gives_up():
    import requests

    url = "https://ins.example/a.pdf"
    fetcher, session, _ = make_fetcher(
        {("GET", "https://ins.example/robots.txt"): ROBOTS_OK, ("GET", url): requests.Timeout("slow")}, max_retries=2
    )
    with pytest.raises(fpd.FetchFailed) as exc:
        fetcher.get_pdf(url)
    assert exc.value.reason == "retries_exhausted"
    assert len(session.calls) == 1 + 3


def test_404_is_not_retried():
    url = "https://ins.example/a.pdf"
    fetcher, session, _ = make_fetcher({("GET", "https://ins.example/robots.txt"): ROBOTS_OK})
    with pytest.raises(fpd.FetchFailed) as exc:
        fetcher.get_pdf(url)
    assert exc.value.reason == "http_404"
    assert len(session.calls) == 2


@pytest.mark.parametrize("status", [401, 403, 429])
def test_blocking_status_stops_host_without_retry(status):
    url1, url2 = "https://ins.example/a.pdf", "https://ins.example/b.pdf"
    fetcher, session, _ = make_fetcher(
        {
            ("GET", "https://ins.example/robots.txt"): ROBOTS_OK,
            ("GET", url1): Resp(status),
            ("GET", url2): Resp(200, PDF_A),
        }
    )
    with pytest.raises(fpd.HostBlocked):
        fetcher.get_pdf(url1)
    with pytest.raises(fpd.HostBlocked):
        fetcher.get_pdf(url2)
    assert [c[1] for c in session.calls] == ["https://ins.example/robots.txt", url1]


def test_challenge_page_stops_host():
    url1, url2 = "https://ins.example/a.pdf", "https://ins.example/b.pdf"
    fetcher, session, _ = make_fetcher(
        {
            ("GET", "https://ins.example/robots.txt"): ROBOTS_OK,
            ("GET", url1): Resp(200, CLOUDFLARE),
            ("GET", url2): Resp(200, PDF_A),
        }
    )
    with pytest.raises(fpd.HostBlocked, match="challenge_page"):
        fetcher.get_pdf(url1)
    with pytest.raises(fpd.HostBlocked):
        fetcher.get_pdf(url2)
    assert len(session.calls) == 2


def test_redirects_followed_with_robots_check_per_host():
    url = "https://ins.example/a.pdf"
    target = "https://cdn.example/files/a.pdf"
    fetcher, session, _ = make_fetcher(
        {
            ("GET", "https://ins.example/robots.txt"): ROBOTS_OK,
            ("GET", url): Resp(302, headers={"Location": target}),
            ("GET", "https://cdn.example/robots.txt"): Resp(404),
            ("GET", target): Resp(200, PDF_A),
        }
    )
    assert fetcher.get_pdf(url) == PDF_A
    assert [c[1] for c in session.calls] == [
        "https://ins.example/robots.txt",
        url,
        "https://cdn.example/robots.txt",
        target,
    ]


# -- Mapfre docprecon adapter --------------------------------------------------


def _mapfre_routes(document_id: str, pdf: bytes, parts: int = 3, temp: str = "tmp123.pdf"):
    b64 = base64.b64encode(pdf).decode()
    size = -(-len(b64) // parts)
    pieces = [b64[i * size : (i + 1) * size] for i in range(parts)]
    url = f"{API}docpreconcomercialesdocument?documentId={document_id}"
    responses = [Resp(200, f"{i + 1}/{parts}#|#{temp}#|#doc.pdf#|#{piece}".encode()) for i, piece in enumerate(pieces)]
    return url, responses + [Resp(200, b"OK")]  # last one answers the cleanup call


def _mapfre_doc(document_id="0900ab44c391e066"):
    from scripts.utils.source_manifest import ManifestDocument

    return ManifestDocument.model_validate(
        {
            "doc_id": "coche_cg",
            "doc_type": "condiciones_generales",
            "source": {"type": "mapfre_docprecon", "document_id": document_id, "entidad": "001"},
            "source_url": "https://www.mapfre.es/documentacion-precontractual/",
        }
    )


def test_mapfre_adapter_reassembles_chunks_and_cleans_up():
    url, responses = _mapfre_routes("0900ab44c391e066", PDF_A, parts=3)
    fetcher, session, clock = make_fetcher(
        {("GET", "https://www.mapfre.es/robots.txt"): ROBOTS_OK, ("POST", url): responses}
    )
    adapter = fpd.MapfreDocpreconAdapter(api_key="test-key")
    assert adapter.fetch(_mapfre_doc(), fetcher) == PDF_A

    posts = [c for c in session.calls if c[0] == "POST"]
    bodies = [c[2]["json"] for c in posts]
    assert bodies == [
        {"chunk": 1},
        {"chunk": 2, "tempFile": "tmp123.pdf"},
        {"chunk": 3, "tempFile": "tmp123.pdf"},
        {"tempFile": "tmp123.pdf", "cleanup": True},
    ]
    for _, _, kwargs in posts:
        assert kwargs["headers"]["User-Agent"] == fpd.USER_AGENT
        assert kwargs["headers"]["x-api-key"] == "test-key"
    # robots.txt of the portal host governs the API calls; API host is rate limited
    assert session.calls[0][1] == "https://www.mapfre.es/robots.txt"
    assert clock.sleeps == [3.0, 3.0, 3.0]


def test_mapfre_adapter_rejects_non_pdf():
    url, responses = _mapfre_routes("0900ab44c391e066", b"<html>not a pdf</html>" * 10, parts=2)
    fetcher, _, _ = make_fetcher({("GET", "https://www.mapfre.es/robots.txt"): ROBOTS_OK, ("POST", url): responses})
    with pytest.raises(fpd.FetchFailed) as exc:
        fpd.MapfreDocpreconAdapter(api_key="k").fetch(_mapfre_doc(), fetcher)
    assert exc.value.reason == "not_a_pdf"


def test_mapfre_adapter_error_and_block_handling():
    url = f"{API}docpreconcomercialesdocument?documentId=0900ab44c391e066"
    fetcher, _, _ = make_fetcher(
        {("GET", "https://www.mapfre.es/robots.txt"): ROBOTS_OK, ("POST", url): Resp(200, b"Error")}
    )
    with pytest.raises(fpd.FetchFailed, match="source_error"):
        fpd.MapfreDocpreconAdapter(api_key="k").fetch(_mapfre_doc(), fetcher)

    fetcher, session, _ = make_fetcher(
        {("GET", "https://www.mapfre.es/robots.txt"): ROBOTS_OK, ("POST", url): Resp(403)}
    )
    adapter = fpd.MapfreDocpreconAdapter(api_key="k")
    with pytest.raises(fpd.HostBlocked):
        adapter.fetch(_mapfre_doc(), fetcher)
    with pytest.raises(fpd.HostBlocked):
        adapter.fetch(_mapfre_doc(), fetcher)
    assert len([c for c in session.calls if c[0] == "POST"]) == 1  # no retry, no second attempt


def test_mapfre_adapter_requires_api_key(monkeypatch):
    monkeypatch.delenv("MAPFRE_DOCPRECON_API_KEY", raising=False)
    fetcher, session, _ = make_fetcher({})
    with pytest.raises(fpd.FetchFailed, match="not_configured"):
        fpd.MapfreDocpreconAdapter().fetch(_mapfre_doc(), fetcher)
    assert session.calls == []


def test_mapfre_chunk_out_of_order_rejected():
    url = f"{API}docpreconcomercialesdocument?documentId=0900ab44c391e066"
    fetcher, _, _ = make_fetcher(
        {("GET", "https://www.mapfre.es/robots.txt"): ROBOTS_OK, ("POST", url): Resp(200, b"2/3#|#t#|#f#|#AAAA")}
    )
    with pytest.raises(fpd.FetchFailed, match="bad_response"):
        fpd.MapfreDocpreconAdapter(api_key="k").fetch(_mapfre_doc(), fetcher)


def test_decode_mapfre_base64_tolerates_whitespace_and_padding():
    b64 = base64.b64encode(PDF_B).decode()
    assert fpd.decode_mapfre_base64([b64[:10] + "\n", " " + b64[10:].rstrip("=")]) == PDF_B


# -- end to end over a manifest -------------------------------------------------


def test_run_fetches_shared_document_once_and_records_provenance(tmp_path, mock_markitdown):
    manifest_dir = tmp_path / "sources"
    manifest_dir.mkdir()
    write_manifest(manifest_dir, MAPFRE_RECORDS)
    routes: dict = {("GET", "https://www.mapfre.es/robots.txt"): ROBOTS_OK}
    pdfs = {"0900ab44c391e066": PDF_A, "0900ab44c48adb6a": PDF_B, "0900ab44c48b450d": PDF_B + b"nota"}
    for doc_id, pdf in pdfs.items():
        url, responses = _mapfre_routes(doc_id, pdf, parts=2, temp=f"t-{doc_id}")
        routes[("POST", url)] = responses
    fetcher, session, _ = make_fetcher(routes)
    adapters = {"mapfre_docprecon": fpd.MapfreDocpreconAdapter(api_key="k"), "url": fpd.UrlAdapter()}
    company = tmp_path / "company"
    cache = DocumentCache(tmp_path / "cache")

    stats = fpd.run(
        "C0058",
        manifest_dir=manifest_dir,
        cache=cache,
        fetcher=fetcher,
        adapters=adapters,
        company_folder=company,
        log_gaps=False,
    )
    assert stats.fetched == 3 and stats.gaps == []
    records = [json.loads(line) for line in (company / "documents.jsonl").read_text(encoding="utf-8").splitlines()]
    # shared CG recorded once per product, same hashes
    cg = [r for r in records if r["doc_id"] == "coche_cg_0900ab44c391e066"]
    assert sorted(r["product_id"] for r in cg) == ["urn:C0058-01", "urn:C0058-02"]
    assert len({r["pdf_sha256"] for r in cg}) == 1
    assert cache.get_pdf(cg[0]["pdf_sha256"]).exists
    assert cache.get_markdown(cg[0]["markdown_sha256"]).exists
    assert cg[0]["source"] == {"type": "mapfre_docprecon", "document_id": "0900ab44c391e066", "entidad": "001"}
    assert cg[0]["source_url"].startswith("https://www.mapfre.es/documentacion-precontractual/")
    assert {"retrieved_at", "pdf_size", "filename", "doc_type", "product_name"} <= set(cg[0])
    assert len(records) == 4

    # Idempotent: a second run makes no network calls
    calls_before = len(session.calls)
    stats2 = fpd.run(
        "C0058",
        manifest_dir=manifest_dir,
        cache=cache,
        fetcher=fetcher,
        adapters=adapters,
        company_folder=company,
        log_gaps=False,
    )
    assert stats2.fetched == 0 and stats2.skipped_cached == 3
    assert len(session.calls) == calls_before
    assert (company / "documents.jsonl").read_text(encoding="utf-8").count("\n") == 4


def test_run_records_gaps_on_block(tmp_path, mock_markitdown):
    manifest_dir = tmp_path / "sources"
    manifest_dir.mkdir()
    write_manifest(manifest_dir, MAPFRE_RECORDS)
    routes: dict = {("GET", "https://www.mapfre.es/robots.txt"): ROBOTS_OK}
    for doc_id in ("0900ab44c391e066", "0900ab44c48adb6a", "0900ab44c48b450d"):
        routes[("POST", f"{API}docpreconcomercialesdocument?documentId={doc_id}")] = Resp(429)
    fetcher, session, _ = make_fetcher(routes)
    stats = fpd.run(
        "C0058",
        manifest_dir=manifest_dir,
        cache=DocumentCache(tmp_path / "cache"),
        fetcher=fetcher,
        adapters={"mapfre_docprecon": fpd.MapfreDocpreconAdapter(api_key="k")},
        company_folder=tmp_path / "company",
        log_gaps=False,
    )
    assert stats.fetched == 0
    assert [g.reason for g in stats.gaps] == ["host_blocked"] * 3
    assert len([c for c in session.calls if c[0] == "POST"]) == 1  # stopped after the first 429
    shared = next(g for g in stats.gaps if g.doc_id == "coche_cg_0900ab44c391e066")
    assert shared.product_ids == ["urn:C0058-01", "urn:C0058-02"]


def test_dry_run_makes_no_requests(tmp_path, capsys):
    manifest_dir = tmp_path / "sources"
    manifest_dir.mkdir()
    write_manifest(manifest_dir, MAPFRE_RECORDS)
    session = FakeSession({})
    fetcher = fpd.PoliteFetcher(session=session)
    fpd.run("C0058", manifest_dir=manifest_dir, fetcher=fetcher, dry_run=True)
    assert session.calls == []
    assert "coche_cg_0900ab44c391e066" in capsys.readouterr().out


def test_run_log_matches_data_integrity_schema(tmp_path, mock_markitdown, monkeypatch):
    """Fetcher run records must satisfy CI's runs.jsonl schema (script + started_at)."""
    import scripts.utils.run_log
    from scripts.ci.check_data_integrity import validate_jsonl_file
    from scripts.utils.jsonl import load_jsonl

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(scripts.utils.run_log, "BASE_STORAGE_PATH", data_dir)

    manifest_dir = tmp_path / "sources"
    manifest_dir.mkdir()
    write_manifest(manifest_dir, MAPFRE_RECORDS)
    routes: dict = {("GET", "https://www.mapfre.es/robots.txt"): ROBOTS_OK}
    for doc_id in ("0900ab44c391e066", "0900ab44c48adb6a", "0900ab44c48b450d"):
        routes[("POST", f"{API}docpreconcomercialesdocument?documentId={doc_id}")] = Resp(429)
    fetcher, _, _ = make_fetcher(routes)
    stats = fpd.run(
        "C0058",
        manifest_dir=manifest_dir,
        cache=DocumentCache(tmp_path / "cache"),
        fetcher=fetcher,
        adapters={"mapfre_docprecon": fpd.MapfreDocpreconAdapter(api_key="k")},
        company_folder=tmp_path / "company",
    )
    assert stats.fetched == 0
    assert [g.reason for g in stats.gaps] == ["host_blocked"] * 3

    runs_path = data_dir / "runs.jsonl"
    errors, _warnings = validate_jsonl_file(runs_path, "started_at", ["script", "started_at"])
    assert errors == []

    runs = load_jsonl(runs_path)
    assert len(runs) == 1
    record = runs[0]
    assert record["script"] == fpd.SCRIPT_NAME
    assert "started_at" in record and "finished_at" in record
    assert "event_type" not in record
    assert record["counts"]["fetched"] == 0
    assert record["counts"]["skipped_cached"] == 0
    assert record["counts"]["gaps"] == 3
    assert record["counts"]["host_blocked"] == 3
    assert record["details"]["company_key"] == "C0058"
    assert record["details"]["user_agent"] == fpd.USER_AGENT
    assert len(record["details"]["gaps"]) == 3
    assert all(gap["reason"] == "host_blocked" for gap in record["details"]["gaps"])
