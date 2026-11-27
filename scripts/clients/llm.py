"""LLM provider abstraction for product analysis: Gemini primary, Mistral fallback.

Every provider client implements :class:`AnalysisClient` (``provider``, ``model``,
``compute_input_hash``, ``analyze_product_documents``). Each client owns its own retries, backoff and
``ProductAnalysis`` validation. :class:`AnalysisRouter` chains them:

* ``auto`` (default): Gemini first; if Gemini still fails after its retries with a
  *retryable* error (429, 5xx, 408, timeouts, connection errors) or *invalid output*
  (``ProductAnalysis`` validation / empty response), the same prompt goes to Mistral.
* Auth or config errors (401/403, 400, 404 unknown model, missing key) and unknown
  exceptions never fall back silently: they are logged and the product fails. After the
  first auth/config error the primary is disabled for the rest of the run, so the run
  does not hammer a broken key once per product. A fallback provider is disabled only on
  401/403/404; its 400/422 fails that product only.
* No ``MISTRAL_API_KEY`` means no fallback at all (logged once when the router is built).
* ``gemini`` / ``mistral`` force a single provider.
"""

from __future__ import annotations

import enum
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from pydantic import ValidationError

from insurance_product_data_sp.core.logging import logger
from insurance_product_data_sp.schemas.insurance_product import ProductAnalysis

PROVIDER_CHOICES = ("auto", "gemini", "mistral")

RETRYABLE_STATUS_CODES = frozenset({408, 429})
AUTH_STATUS_CODES = frozenset({401, 403})
# Statuses that disable a non-primary (fallback) provider for the rest of the run
LATCHING_FALLBACK_STATUS_CODES = frozenset({401, 403, 404})
_TRANSPORT_ERROR_NAMES = frozenset({"TransportError", "TimeoutException", "NetworkError", "NoResponseError"})


class AnalysisClient(Protocol):
    """What analyze_products needs from a provider client."""

    provider: str
    model: str

    @staticmethod
    def compute_input_hash(markdown_paths: list[str]) -> str: ...

    def analyze_product_documents(
        self,
        markdown_paths: list[str],
        product_context: dict | None = None,
        document_names: dict[str, str] | None = None,
    ) -> ProductAnalysis: ...


class ErrorKind(enum.Enum):
    """How a provider failure is treated by the router."""

    RETRYABLE = "retryable"  # quota/overload/timeout/connection: fall back
    INVALID_OUTPUT = "invalid_output"  # validation failed after retries: fall back
    AUTH = "auth"  # bad/missing key or permission: never fall back silently
    CONFIG = "config"  # bad request, unknown model: never fall back silently
    UNKNOWN = "unknown"  # anything else: never fall back silently


FALLBACK_KINDS = frozenset({ErrorKind.RETRYABLE, ErrorKind.INVALID_OUTPUT})


def _status_code(exc: BaseException) -> int | None:
    """HTTP status of a google-genai ``APIError`` (``code``) or a Mistral ``MistralError`` (``status_code``)."""
    for attr in ("status_code", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int) and 100 <= value <= 599:
            return value
    return None


def classify_error(exc: BaseException) -> ErrorKind:
    """Classify a provider exception (raised after the provider's own retries)."""
    if isinstance(exc, ValidationError | ValueError):
        return ErrorKind.INVALID_OUTPUT
    if isinstance(exc, TimeoutError | ConnectionError):
        return ErrorKind.RETRYABLE
    if any(cls.__name__ in _TRANSPORT_ERROR_NAMES for cls in type(exc).__mro__):
        return ErrorKind.RETRYABLE
    status = _status_code(exc)
    if status is None:
        return ErrorKind.UNKNOWN
    if status in AUTH_STATUS_CODES:
        return ErrorKind.AUTH
    if status in RETRYABLE_STATUS_CODES or status >= 500:
        return ErrorKind.RETRYABLE
    return ErrorKind.CONFIG


class ProviderConfigError(RuntimeError):
    """A provider cannot be used (missing key, auth or config error); never triggers fallback."""


@dataclass
class RoutedAnalysis:
    """Analysis plus which provider/model actually produced it."""

    analysis: ProductAnalysis
    provider: str
    model: str
    fallback_from: str | None = None
    fallback_reason: str | None = None


def _describe(exc: BaseException) -> str:
    text = str(exc).splitlines()[0] if str(exc) else ""
    return f"{type(exc).__name__}: {text[:300]}"


class AnalysisRouter:
    """Runs the provider chain and records which provider answered."""

    def __init__(self, clients: list[AnalysisClient], mode: str = "auto"):
        if not clients:
            raise ValueError("AnalysisRouter needs at least one client")
        self.clients = clients
        self.mode = mode
        self._disabled: dict[str, str] = {}

    # GeminiClient-compatible surface used by analyze_products
    @property
    def provider(self) -> str:
        return getattr(self.clients[0], "provider", "gemini")

    @property
    def model(self) -> str:
        return self.clients[0].model

    @property
    def accepted_models(self) -> set[str]:
        """Models whose existing analyses count as up to date (idempotency check)."""
        return {c.model for c in self.clients}

    @staticmethod
    def compute_input_hash(markdown_paths: list[str]) -> str:
        from scripts.clients.gemini import GeminiClient

        return GeminiClient.compute_input_hash(markdown_paths)

    def analyze_product_documents(
        self,
        markdown_paths: list[str],
        product_context: dict | None = None,
        document_names: dict[str, str] | None = None,
    ) -> ProductAnalysis:
        return self.analyze_with_provenance(markdown_paths, product_context, document_names).analysis

    def analyze_with_provenance(
        self,
        markdown_paths: list[str],
        product_context: dict | None = None,
        document_names: dict[str, str] | None = None,
    ) -> RoutedAnalysis:
        """Try each provider in order; fall back only on retryable errors or invalid output."""
        fallback_from: str | None = None
        fallback_reason: str | None = None
        last_exc: BaseException | None = None

        for index, client in enumerate(self.clients):
            provider = getattr(client, "provider", "gemini")
            if provider in self._disabled:
                raise ProviderConfigError(self._disabled[provider])
            try:
                analysis = client.analyze_product_documents(
                    markdown_paths=markdown_paths,
                    product_context=product_context,
                    document_names=document_names,
                )
                return RoutedAnalysis(
                    analysis=analysis,
                    provider=provider,
                    model=client.model,
                    fallback_from=fallback_from,
                    fallback_reason=fallback_reason,
                )
            except Exception as exc:
                last_exc = exc
                kind = classify_error(exc)
                has_next = index + 1 < len(self.clients)
                if kind in (ErrorKind.AUTH, ErrorKind.CONFIG):
                    message = (
                        f"{provider} {kind.value} error ({_describe(exc)}). Not falling back automatically: "
                        f"fix the {provider} key/model, or rerun with --provider explicitly."
                    )
                    logger.error(message)
                    # The primary is latched on any auth/config error. A fallback provider is latched
                    # only when the key or model is broken (401/403/404); a request-scoped 400/422
                    # (e.g. a prompt too long for its context) fails this product only.
                    if index == 0 or _status_code(exc) in LATCHING_FALLBACK_STATUS_CODES:
                        self._disabled[provider] = message
                    raise ProviderConfigError(message) from exc
                if kind not in FALLBACK_KINDS or not has_next:
                    raise
                fallback_from = provider
                fallback_reason = f"{kind.value}: {_describe(exc)}"
                next_provider = getattr(self.clients[index + 1], "provider", "?")
                logger.warning(f"{provider} failed after retries ({fallback_reason}); falling back to {next_provider}")

        raise last_exc if last_exc else RuntimeError("No provider produced an analysis")


def build_router(
    mode: str = "auto",
    gemini_factory: Callable[[], AnalysisClient] | None = None,
    mistral_factory: Callable[[], AnalysisClient] | None = None,
) -> AnalysisRouter:
    """Build the provider chain for ``--provider auto|gemini|mistral``.

    Raises:
        ProviderConfigError: if a required provider cannot be configured (e.g. missing key).
    """
    if mode not in PROVIDER_CHOICES:
        raise ValueError(f"Unknown provider {mode!r}; expected one of {PROVIDER_CHOICES}")

    if gemini_factory is None:
        from scripts.clients.gemini import GeminiClient

        gemini_factory = GeminiClient
    if mistral_factory is None:
        from scripts.clients.mistral import MistralClient

        mistral_factory = MistralClient

    def make(name: str, factory: Callable[[], AnalysisClient]) -> AnalysisClient:
        try:
            return factory()
        except Exception as exc:
            raise ProviderConfigError(f"Cannot configure {name}: {_describe(exc)}") from exc

    has_mistral_key = bool(os.getenv("MISTRAL_API_KEY"))

    if mode == "mistral":
        if not has_mistral_key:
            raise ProviderConfigError("--provider mistral needs MISTRAL_API_KEY in .env")
        return AnalysisRouter([make("mistral", mistral_factory)], mode=mode)

    clients = [make("gemini", gemini_factory)]
    if mode == "auto":
        if has_mistral_key:
            clients.append(make("mistral", mistral_factory))
            logger.info(f"Mistral fallback enabled ({clients[-1].model})")
        else:
            logger.info("MISTRAL_API_KEY not set: Mistral fallback disabled for this run")
    return AnalysisRouter(clients, mode=mode)
