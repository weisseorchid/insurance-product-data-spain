"""Fetch insurer product documents listed in a source manifest, politely.

Reads ``data/sources/<company_key>.jsonl`` (see docs/SOURCE_MANIFEST.md). Each
document has a typed ``source`` handled by a pluggable adapter (``ADAPTERS``):

- ``url``: plain HTTP GET of a stable PDF URL
- ``mapfre_docprecon``: Mapfre's documentation portal API (base64 chunks, reassembled)

All adapters go through ``PoliteFetcher``, which:

- identifies itself honestly (``USER_AGENT``; never a spoofed browser UA)
- checks ``robots.txt`` and skips disallowed URLs (honours Crawl-delay)
- rate-limits per host (default 3 s between requests, configurable, never < 1 s)
- retries with exponential backoff on 5xx and timeouts/connection errors only
- never bypasses bot protection: on 401/403/429 or a challenge/block page it stops
  using that host for the rest of the run and records a gap

Fetched PDFs must start with ``%PDF-``, are cached by sha256 in ``.cache/insurance-docs``,
converted and validated (``scripts/utils/document_validation.py``) before anything is
recorded, and their provenance is upserted into the company's ``documents.jsonl``.
Already-cached documents are skipped unless ``--force``. Each run appends one ``data/runs.jsonl`` record (``script``, ``started_at``, counts and gap details).

Run with:
    uv run python -m scripts.fetch_product_documents --company-key C0058 [--product seguro_terceros] [--dry-run]
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import os
import re
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

from insurance_product_data_sp.core.logging import logger
from scripts.utils.companies import company_folder_path, find_company
from scripts.utils.document_cache import DocumentCache
from scripts.utils.document_store import convert_cached_pdf, load_documents, save_documents, upsert_document
from scripts.utils.document_validation import (
    PDF_MAGIC_BYTES,
    is_block_page,
    is_known_or_block_page_hash,
    load_known_block_page_hashes,
)
from scripts.utils.gaps import write_gaps_report
from scripts.utils.run_log import append_run_log
from scripts.utils.source_manifest import (
    ManifestDocument,
    MapfreDocpreconSource,
    SourceManifest,
    UrlSource,
    load_manifest,
    manifest_path,
)

SCRIPT_NAME = "fetch_product_documents"
USER_AGENT = "insurance-product-data-spain-bot/0.1 (+https://github.com/weisseorchid/insurance-product-data-spain)"
DEFAULT_DELAY_SECONDS = 3.0
MIN_DELAY_SECONDS = 1.0
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_SECONDS = 5.0
MAX_REDIRECTS = 5
MAX_DOCUMENT_BYTES = 50 * 1024 * 1024
RETRY_STATUSES = frozenset({500, 502, 503, 504})
BLOCKING_STATUSES = frozenset({401, 403, 429})


class HTTPResponse(Protocol):
    status_code: int
    headers: Any
    content: bytes


class HTTPSession(Protocol):
    def request(self, method: str, url: str, **kwargs: Any) -> HTTPResponse: ...


@dataclass
class Gap:
    """A document that could not be fetched (and why)."""

    company_key: str
    doc_id: str
    source: str
    reason: str
    detail: str = ""
    product_ids: list[str] = field(default_factory=list)


@dataclass
class HostState:
    last_request_at: float | None = None
    robots: RobotFileParser | None = None
    blocked_reason: str | None = None
    delay: float = DEFAULT_DELAY_SECONDS


@dataclass
class FetchStats:
    fetched: int = 0
    skipped_cached: int = 0
    gaps: list[Gap] = field(default_factory=list)


class HostBlocked(Exception):
    """The host signalled we must not continue (401/403/429/challenge). Never retried or bypassed."""


class FetchFailed(Exception):
    """A single document could not be fetched."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


def _default_session() -> HTTPSession:
    import requests

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def _is_timeout_or_connection_error(exc: Exception) -> bool:
    try:
        import requests
    except ImportError:  # pragma: no cover - requests is in the sync/dev extras
        return isinstance(exc, TimeoutError | ConnectionError)
    return isinstance(exc, requests.Timeout | requests.ConnectionError | TimeoutError | ConnectionError)


def _host_key(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}".lower()


class PoliteFetcher:
    """HTTP with robots.txt, per-host rate limiting, bounded retries and stop-on-block."""

    def __init__(
        self,
        session: HTTPSession | None = None,
        delay: float = DEFAULT_DELAY_SECONDS,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff: float = DEFAULT_BACKOFF_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if delay < MIN_DELAY_SECONDS:
            raise ValueError(f"delay must be >= {MIN_DELAY_SECONDS}s to respect source sites")
        self.session = session or _default_session()
        self.delay = delay
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff = backoff
        self.clock = clock
        self.sleep = sleep
        self.hosts: dict[str, HostState] = {}

    # -- per-host state -------------------------------------------------
    def host(self, url: str) -> HostState:
        key = _host_key(url)
        if key not in self.hosts:
            self.hosts[key] = HostState(delay=self.delay)
        return self.hosts[key]

    def block(self, url: str, reason: str) -> HostBlocked:
        """Mark the host as blocked for this run and return the exception to raise."""
        self.host(url).blocked_reason = reason
        logger.warning(f"Stopping requests to {_host_key(url)}: {reason}")
        return HostBlocked(reason)

    def _wait_turn(self, state: HostState) -> None:
        if state.last_request_at is not None:
            remaining = state.delay - (self.clock() - state.last_request_at)
            if remaining > 0:
                self.sleep(remaining)
        state.last_request_at = self.clock()

    def _send(self, method: str, url: str, state: HostState, **kwargs: Any) -> HTTPResponse:
        self._wait_turn(state)
        headers = {"User-Agent": USER_AGENT, **kwargs.pop("headers", {})}
        return self.session.request(method, url, headers=headers, timeout=self.timeout, allow_redirects=False, **kwargs)

    # -- robots.txt -----------------------------------------------------
    def _robots(self, url: str) -> RobotFileParser:
        state = self.host(url)
        if state.robots is not None:
            return state.robots
        robots_url = f"{_host_key(url)}/robots.txt"
        parser = RobotFileParser(robots_url)
        try:
            response = self._send("GET", robots_url, state)
            status = response.status_code
        except Exception as exc:  # network failure: be conservative
            logger.warning(f"robots.txt unreachable at {robots_url}: {exc}; treating host as disallowed")
            parser.disallow_all = True
            state.robots = parser
            return parser
        if status == 200:
            parser.parse(response.content.decode("utf-8", errors="replace").splitlines())
        elif status in BLOCKING_STATUSES or status >= 500:
            # unreachable (RFC 9309: assume disallow) or access-restricted (conservative)
            parser.disallow_all = True
        else:  # 404/410 and other 4xx: no robots.txt, everything allowed
            parser.allow_all = True
        crawl_delay = parser.crawl_delay(USER_AGENT)
        if crawl_delay:
            state.delay = max(state.delay, float(crawl_delay))
        state.robots = parser
        return parser

    def allowed(self, url: str) -> bool:
        return self._robots(url).can_fetch(USER_AGENT, url)

    # -- requests -------------------------------------------------------
    def request(self, method: str, url: str, *, robots_url: str | None = None, **kwargs: Any) -> HTTPResponse:
        """One polite request (no redirects followed).

        ``robots_url`` is the URL whose robots.txt rules govern this request; it defaults
        to ``url`` and lets API adapters be governed by the public page that uses the API.

        Raises:
            HostBlocked: the host is (or just became) blocked: 401/403/429
            FetchFailed: robots disallow or retries exhausted
        """
        state = self.host(url)
        if state.blocked_reason:
            raise HostBlocked(state.blocked_reason)
        governing = robots_url or url
        if self.host(governing).blocked_reason:
            raise HostBlocked(self.host(governing).blocked_reason or "blocked")
        if not self.allowed(governing):
            raise FetchFailed("robots_disallowed", governing)

        last_error = ""
        for attempt in range(self.max_retries + 1):
            if attempt:
                self.sleep(self.backoff * (2 ** (attempt - 1)))
            try:
                response = self._send(method, url, state, **kwargs)
            except Exception as exc:
                if not _is_timeout_or_connection_error(exc):
                    raise FetchFailed("request_error", str(exc)) from exc
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning(f"Attempt {attempt + 1} failed for {url}: {last_error}")
                continue
            if response.status_code in RETRY_STATUSES:
                last_error = f"http_{response.status_code}"
                logger.warning(f"Attempt {attempt + 1} got {response.status_code} for {url}")
                continue
            if response.status_code in BLOCKING_STATUSES:
                raise self.block(url, f"http_{response.status_code}")
            return response
        raise FetchFailed("retries_exhausted", last_error)

    def check_not_challenge(self, url: str, body: bytes) -> None:
        """Raise HostBlocked (and stop the host) if a non-PDF body is a bot/challenge page."""
        if body.startswith(PDF_MAGIC_BYTES):
            return
        if is_block_page(body[:200_000].decode("utf-8", errors="replace")):
            raise self.block(url, "challenge_page")

    def get_pdf(self, url: str) -> bytes:
        """GET a PDF, following redirects one polite hop at a time (each hop robots-checked)."""
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            response = self.request("GET", current)
            status = response.status_code
            if status in (301, 302, 303, 307, 308):
                location = response.headers.get("Location") if response.headers else None
                if not location:
                    raise FetchFailed("bad_redirect", f"{status} without Location")
                current = urljoin(current, location)
                continue
            if status != 200:
                raise FetchFailed(f"http_{status}", current)
            body = response.content or b""
            self.check_not_challenge(current, body)
            return body
        raise FetchFailed("too_many_redirects", url)


# -- source adapters ------------------------------------------------------------


class SourceAdapter(Protocol):
    source_type: str

    def fetch(self, document: ManifestDocument, fetcher: PoliteFetcher) -> bytes: ...


class UrlAdapter:
    """Stable public PDF URL."""

    source_type = "url"

    def fetch(self, document: ManifestDocument, fetcher: PoliteFetcher) -> bytes:
        assert isinstance(document.source, UrlSource)
        return fetcher.get_pdf(document.source.url)


MAPFRE_DOCPRECON_API_BASE = "https://o66inw9e2k.execute-api.eu-west-1.amazonaws.com/stage-mapfrees-docprecon/"
MAPFRE_PORTAL_URL = "https://www.mapfre.es/documentacion-precontractual/"
MAPFRE_CHUNK_SEPARATOR = "#|#"
MAPFRE_MAX_CHUNKS = 400


@dataclass
class MapfreChunk:
    current: int
    total: int
    temp_file: str
    file_name: str
    base64: str


def parse_mapfre_chunk(text: str) -> MapfreChunk:
    """Parse ``current/total#|#tempFile#|#fileName#|#base64`` (format used by Mapfre's docprecon.js)."""
    if text.strip() == "Error":
        raise FetchFailed("source_error", "docprecon returned 'Error'")
    parts = text.split(MAPFRE_CHUNK_SEPARATOR)
    if len(parts) < 4:
        raise FetchFailed("bad_response", f"unexpected docprecon chunk: {text[:120]!r}")
    match = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", parts[0])
    if not match:
        raise FetchFailed("bad_response", f"bad progress field {parts[0][:40]!r}")
    return MapfreChunk(
        current=int(match.group(1)),
        total=int(match.group(2)),
        temp_file=parts[1],
        file_name=parts[2],
        base64=MAPFRE_CHUNK_SEPARATOR.join(parts[3:]),
    )


def decode_mapfre_base64(chunks: list[str]) -> bytes:
    """Join and decode base64 chunks the way the portal's JS does (strip non-alphabet, fix padding)."""
    joined = re.sub(r"[^A-Za-z0-9+/=]", "", "".join(chunks)).rstrip("=")
    joined += "=" * (-len(joined) % 4)
    try:
        return base64.b64decode(joined, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise FetchFailed("bad_base64", str(exc)) from exc


class MapfreDocpreconAdapter:
    """Mapfre documentation portal (www.mapfre.es/documentacion-precontractual/).

    Mirrors what the portal's own download button does: POST ``{chunk: n[, tempFile]}``
    to ``docpreconcomercialesdocument?documentId=<id>`` until ``current == total``,
    reassemble the base64, then a best-effort cleanup POST so the server can delete
    its temporary file. Requests are governed by the portal page's robots.txt rules,
    use the same honest UA, rate limit and stop-on-block rules as every other source.
    The API key used by the portal is *not* committed; pass it via
    ``MAPFRE_DOCPRECON_API_KEY`` (without it every Mapfre document becomes a gap).
    """

    source_type = "mapfre_docprecon"

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str = MAPFRE_DOCPRECON_API_BASE,
        portal_url: str = MAPFRE_PORTAL_URL,
        max_chunks: int = MAPFRE_MAX_CHUNKS,
    ):
        self.api_key = api_key if api_key is not None else os.environ.get("MAPFRE_DOCPRECON_API_KEY")
        self.api_base = api_base if api_base.endswith("/") else api_base + "/"
        self.portal_url = portal_url
        self.max_chunks = max_chunks

    def _post(self, fetcher: PoliteFetcher, url: str, body: dict[str, Any]) -> str:
        response = fetcher.request(
            "POST",
            url,
            robots_url=self.portal_url,
            json=body,
            headers={"x-api-key": self.api_key or "", "Content-Type": "application/json"},
        )
        if response.status_code != 200:
            raise FetchFailed(f"http_{response.status_code}", url)
        raw = response.content or b""
        fetcher.check_not_challenge(url, raw)
        return raw.decode("utf-8", errors="replace")

    def fetch(self, document: ManifestDocument, fetcher: PoliteFetcher) -> bytes:
        source = document.source
        assert isinstance(source, MapfreDocpreconSource)
        if not self.api_key:
            raise FetchFailed("not_configured", "MAPFRE_DOCPRECON_API_KEY is not set")
        url = f"{self.api_base}docpreconcomercialesdocument?documentId={source.document_id}"

        chunks: list[str] = []
        temp_file = ""
        index = 1
        while True:
            body: dict[str, Any] = {"chunk": index}
            if temp_file:
                body["tempFile"] = temp_file
            chunk = parse_mapfre_chunk(self._post(fetcher, url, body))
            if chunk.current != index or chunk.total < 1 or chunk.total > self.max_chunks:
                raise FetchFailed("bad_response", f"chunk {chunk.current}/{chunk.total} when {index} was requested")
            temp_file = temp_file or chunk.temp_file
            chunks.append(chunk.base64)
            if chunk.current >= chunk.total:
                break
            index += 1

        if temp_file:
            try:
                self._post(fetcher, url, {"tempFile": temp_file, "cleanup": True})
            except (FetchFailed, HostBlocked) as exc:  # best effort, like the portal
                logger.warning(f"docprecon cleanup for {source.document_id} failed: {exc}")

        pdf = decode_mapfre_base64(chunks)
        if not pdf.startswith(PDF_MAGIC_BYTES):
            raise FetchFailed("not_a_pdf", f"decoded document {source.document_id} does not start with %PDF-")
        return pdf


def default_adapters() -> dict[str, SourceAdapter]:
    return {a.source_type: a for a in (UrlAdapter(), MapfreDocpreconAdapter())}


# -- manifest processing ------------------------------------------------------------


def _store_pdf_bytes(body: bytes, cache: DocumentCache) -> str:
    sha = hashlib.sha256(body).hexdigest()
    target = cache.get_pdf_path(sha)
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=target.parent, suffix=".part")
        with os.fdopen(fd, "wb") as f:
            f.write(body)
        os.replace(tmp, target)
    return sha


def _source_dict(document: ManifestDocument) -> dict[str, Any]:
    return document.source.model_dump(mode="json")


def _cached_record(records: list[dict[str, Any]], document: ManifestDocument, cache: DocumentCache) -> dict | None:
    source = _source_dict(document)
    for record in records:
        if record.get("source") != source:
            continue
        pdf, md = record.get("pdf_sha256"), record.get("markdown_sha256")
        if pdf and md and cache.get_pdf(pdf).exists and cache.get_markdown(md).exists:
            return record
    return None


def _clear_document_markdown(
    records: list[dict[str, Any]],
    document: ManifestDocument,
    product_ids: list[str],
) -> list[dict[str, Any]]:
    """Keep provenance rows but drop markdown_sha256 so block pages are not re-used."""
    filename = document.resolved_filename()
    source = _source_dict(document)
    product_id_set = set(product_ids)
    updated: list[dict[str, Any]] = []
    for record in records:
        if record.get("product_id") in product_id_set and (
            record.get("doc_id") == document.doc_id
            or record.get("filename") == filename
            or record.get("source") == source
        ):
            cleared = dict(record)
            cleared.pop("markdown_sha256", None)
            updated.append(cleared)
        else:
            updated.append(record)
    return updated


def _cached_is_block_page(
    record: dict[str, Any],
    cache: DocumentCache,
    known_hashes: set[str],
) -> bool:
    md_sha = record.get("markdown_sha256")
    if is_known_or_block_page_hash(md_sha if isinstance(md_sha, str) else None, known_hashes):
        return True
    if not md_sha:
        return False
    cached = cache.get_markdown(md_sha)
    if not cached.exists:
        return False
    try:
        content = cached.cache_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return is_block_page(content)


def _gaps_for_report(
    gaps: list[Gap],
    products_by_id: dict[str, Any],
) -> list[dict[str, Any]]:
    """Expand document gaps into one report row per product that uses the document."""
    rows: list[dict[str, Any]] = []
    for g in gaps:
        ids = g.product_ids or [None]
        for product_id in ids:
            product = products_by_id.get(product_id) if product_id else None
            rows.append(
                {
                    "product_id": product_id,
                    "product_name": getattr(product, "product_name", None),
                    "doc_id": g.doc_id,
                    "filename": None,
                    "source": g.source,
                    "reason": g.reason,
                    "detail": g.detail,
                }
            )
    return rows


def run(
    company_key: str,
    product: str | None = None,
    manifest_dir: Path | None = None,
    cache: DocumentCache | None = None,
    fetcher: PoliteFetcher | None = None,
    adapters: dict[str, SourceAdapter] | None = None,
    company_folder: Path | None = None,
    force: bool = False,
    dry_run: bool = False,
    log_gaps: bool = True,
) -> FetchStats:
    manifest: SourceManifest = load_manifest(manifest_path(company_key, manifest_dir))
    products = manifest.products
    if product:
        products = [p for p in products if p.product_name == product]
        if not products:
            raise SystemExit(f"Product {product!r} not in manifest for {company_key}")

    # doc_id -> products that use it (fetch each document once, record it per product)
    users: dict[str, list] = {}
    for p in products:
        for doc_id in p.documents:
            users.setdefault(doc_id, []).append(p)
    products_by_id = {p.product_id: p for p in products}
    known_block_hashes = load_known_block_page_hashes()

    stats = FetchStats()
    if dry_run:
        for doc_id in sorted(users):
            doc = manifest.documents[doc_id]
            names = ",".join(p.product_name for p in users[doc_id])
            print(f"{doc_id}\t{doc.doc_type}\t{doc.source.type}\t{doc.source.key()}\t{names}")
        return stats

    if company_folder is None:
        company = find_company(company_key)
        if not company:
            raise SystemExit(f"Company {company_key} not found in data/insurance_companies.jsonl")
        company_folder = company_folder_path(company)
    company_folder.mkdir(parents=True, exist_ok=True)
    cache = cache or DocumentCache()
    fetcher = fetcher or PoliteFetcher()
    adapters = adapters or default_adapters()
    records = load_documents(company_folder)
    started_at = datetime.now(timezone.utc)
    usable_docs_by_product: dict[str, int] = {p.product_id: 0 for p in products}

    for doc_id in sorted(users):
        doc = manifest.documents[doc_id]
        product_ids = [p.product_id for p in users[doc_id]]

        def gap(reason: str, detail: str = "", doc: ManifestDocument = doc, product_ids: list = product_ids) -> None:
            stats.gaps.append(Gap(company_key, doc.doc_id, doc.source.key(), reason, detail, product_ids))
            logger.warning(f"Gap for {doc.doc_id} ({doc.source.key()}): {reason} {detail}")

        cached = None if force else _cached_record(records, doc, cache)
        if cached and _cached_is_block_page(cached, cache, known_block_hashes):
            gap("block_page", str(cached.get("markdown_sha256") or ""))
            records = _clear_document_markdown(records, doc, product_ids)
            save_documents(company_folder, records)
            continue
        if cached:
            stats.skipped_cached += 1
            pdf_sha, md_sha, size = cached["pdf_sha256"], cached["markdown_sha256"], cached.get("pdf_size")
            retrieved_at = cached.get("retrieved_at")
        else:
            adapter = adapters.get(doc.source.type)
            if adapter is None:
                gap("no_adapter", doc.source.type)
                continue
            try:
                body = adapter.fetch(doc, fetcher)
            except HostBlocked as exc:
                gap("host_blocked", str(exc))
                continue
            except FetchFailed as exc:
                gap(exc.reason, exc.detail)
                continue
            if len(body) > MAX_DOCUMENT_BYTES:
                gap("too_large", f"{len(body)} bytes")
                continue
            if not body.startswith(PDF_MAGIC_BYTES):
                gap("not_a_pdf", "missing %PDF- magic bytes")
                continue
            pdf_sha = _store_pdf_bytes(body, cache)
            outcome = convert_cached_pdf(pdf_sha, cache)
            known_bad = is_known_or_block_page_hash(outcome.markdown_sha256, known_block_hashes)
            error_text = (outcome.error or "").lower()
            is_block = known_bad or "block page" in error_text
            if not outcome.success or not outcome.markdown_sha256 or known_bad:
                reason = "block_page" if is_block else "validation_failed"
                gap(reason, outcome.error or (outcome.markdown_sha256 or ""))
                records = _clear_document_markdown(records, doc, product_ids)
                for p in users[doc_id]:
                    records = upsert_document(
                        records,
                        {
                            "doc_id": doc.doc_id,
                            "doc_type": doc.doc_type,
                            "filename": doc.resolved_filename(),
                            "pdf_sha256": pdf_sha,
                            "pdf_size": len(body),
                            "product_id": p.product_id,
                            "product_name": p.product_name,
                            "retrieved_at": datetime.now(timezone.utc).isoformat(),
                            "source": _source_dict(doc),
                            "source_url": doc.source_url,
                        },
                    )
                save_documents(company_folder, records)
                continue
            md_sha, size = outcome.markdown_sha256, len(body)
            retrieved_at = datetime.now(timezone.utc).isoformat()
            stats.fetched += 1
            logger.info(f"Fetched {doc.doc_id} -> {pdf_sha[:12]} ({size} bytes)")

        for p in users[doc_id]:
            usable_docs_by_product[p.product_id] = usable_docs_by_product.get(p.product_id, 0) + 1
            records = upsert_document(
                records,
                {
                    "doc_id": doc.doc_id,
                    "doc_type": doc.doc_type,
                    "filename": doc.resolved_filename(),
                    "markdown_sha256": md_sha,
                    "pdf_sha256": pdf_sha,
                    "pdf_size": size,
                    "product_id": p.product_id,
                    "product_name": p.product_name,
                    "retrieved_at": retrieved_at,
                    "source": _source_dict(doc),
                    "source_url": doc.source_url,
                },
            )
        save_documents(company_folder, records)

    for product_id, usable in usable_docs_by_product.items():
        if usable == 0:
            product_obj = products_by_id[product_id]
            stats.gaps.append(
                Gap(
                    company_key,
                    doc_id="-",
                    source="-",
                    reason="no_usable_documents",
                    detail="all documents for this product failed or are block pages",
                    product_ids=[product_id],
                )
            )
            logger.warning(f"Gap for product {product_obj.product_name}: no_usable_documents")

    gap_rows = _gaps_for_report(stats.gaps, products_by_id)
    for row in gap_rows:
        doc_id = row.get("doc_id")
        if doc_id and doc_id != "-" and doc_id in manifest.documents:
            row["filename"] = manifest.documents[doc_id].resolved_filename()
    write_gaps_report(company_folder, company_key, SCRIPT_NAME, gap_rows)

    if log_gaps:
        reason_counts: dict[str, int] = {}
        for g in stats.gaps:
            reason_counts[g.reason] = reason_counts.get(g.reason, 0) + 1
        append_run_log(
            script=SCRIPT_NAME,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            counts={
                **reason_counts,
                "fetched": stats.fetched,
                "skipped_cached": stats.skipped_cached,
                "gaps": len(stats.gaps),
            },
            details={
                "company_key": company_key,
                "user_agent": USER_AGENT,
                "gaps": [g.__dict__ for g in stats.gaps],
            },
        )
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch product documents listed in data/sources/<company_key>.jsonl")
    parser.add_argument("--company-key", "-k", required=True, help="DGSFP company key (e.g. C0058)")
    parser.add_argument("--product", "-p", help="Only this product_name")
    parser.add_argument("--manifest-dir", type=Path, help="Directory with <company_key>.jsonl (default data/sources)")
    parser.add_argument("--cache-dir", type=Path, help="Document cache root (default .cache/insurance-docs)")
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY_SECONDS,
        help=f"Seconds between requests to the same host (default {DEFAULT_DELAY_SECONDS}, min {MIN_DELAY_SECONDS})",
    )
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES, help="Retries on 5xx/timeouts only")
    parser.add_argument("--force", action="store_true", help="Re-download even if already cached")
    parser.add_argument("--dry-run", action="store_true", help="Validate the manifest and list documents; no network")
    args = parser.parse_args(argv)

    try:  # optional: pick up MAPFRE_DOCPRECON_API_KEY etc. from a local, gitignored .env
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    fetcher = (
        None if args.dry_run else PoliteFetcher(delay=args.delay, timeout=args.timeout, max_retries=args.max_retries)
    )
    stats = run(
        company_key=args.company_key,
        product=args.product,
        manifest_dir=args.manifest_dir,
        cache=DocumentCache(args.cache_dir) if args.cache_dir else None,
        fetcher=fetcher,
        force=args.force,
        dry_run=args.dry_run,
    )
    if args.dry_run:
        return 0
    logger.info(f"Fetched: {stats.fetched}, cached/skipped: {stats.skipped_cached}, gaps: {len(stats.gaps)}")
    for g in stats.gaps:
        logger.warning(f"GAP {g.doc_id} {g.reason} {g.detail} ({g.source}) used by {g.product_ids}")
    return 1 if stats.gaps else 0


if __name__ == "__main__":
    sys.exit(main())
