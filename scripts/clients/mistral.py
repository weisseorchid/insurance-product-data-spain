"""Mistral AI client used as a fallback analyzer for insurance policy documents.

It mirrors ``GeminiClient``: same prompt, same retry spacing and backoff, and the same
``ProductAnalysis`` pydantic validation of the output. Mistral's JSON mode
(``response_format={"type": "json_object"}``) guarantees valid JSON but not the schema,
so the ``ProductAnalysis`` JSON Schema is appended to the system prompt.
"""

import json
import os
import time

from dotenv import load_dotenv
from mistralai.client import Mistral
from pydantic import ValidationError

from insurance_product_data_sp.core.logging import logger
from insurance_product_data_sp.schemas.insurance_product import ProductAnalysis
from scripts.clients.gemini import (
    INITIAL_RETRY_DELAY,
    MAX_RETRY_ATTEMPTS,
    MAX_RETRY_DELAY,
    SYSTEM_PROMPT,
    GeminiClient,
    build_user_prompt,
)

load_dotenv()

DEFAULT_MISTRAL_MODEL = "mistral-large-latest"
MISTRAL_TIMEOUT_MS = 300_000


def mistral_model_from_env() -> str:
    """Model from ``MISTRAL_MODEL`` (default ``mistral-large-latest``)."""
    return os.getenv("MISTRAL_MODEL") or DEFAULT_MISTRAL_MODEL


def mistral_system_prompt() -> str:
    """System prompt plus the ProductAnalysis JSON Schema (JSON mode does not enforce a schema)."""
    schema = json.dumps(ProductAnalysis.model_json_schema(), ensure_ascii=False)
    return (
        f"{SYSTEM_PROMPT}\n"
        "Respond with a single JSON object only, no prose and no markdown fences. "
        "It must validate against this JSON Schema:\n"
        f"{schema}\n"
    )


def _message_text(response) -> str | None:
    """Extract the text content of the first choice (str or list of text chunks)."""
    choices = getattr(response, "choices", None) or []
    if not choices:
        return None
    content = choices[0].message.content
    if content is None or isinstance(content, str):
        return content
    parts = [getattr(chunk, "text", None) for chunk in content]
    return "".join(p for p in parts if p) or None


class MistralClient:
    """Client for analyzing insurance documents with Mistral (JSON mode)."""

    provider = "mistral"
    compute_input_hash = staticmethod(GeminiClient.compute_input_hash)

    def __init__(
        self,
        model: str | None = None,
        max_retries: int = MAX_RETRY_ATTEMPTS,
        api_key: str | None = None,
    ):
        """Initialize the Mistral client.

        Args:
            model: Model name; defaults to ``MISTRAL_MODEL`` or ``mistral-large-latest``.
            max_retries: Attempts for API errors and validation failures (same as Gemini).
            api_key: Defaults to ``MISTRAL_API_KEY``.

        Raises:
            ValueError: If no API key is available.
        """
        api_key = api_key or os.getenv("MISTRAL_API_KEY")
        if not api_key:
            raise ValueError("MISTRAL_API_KEY is not set")
        self.client = Mistral(api_key=api_key)
        self.model = model or mistral_model_from_env()
        self.max_retries = max_retries

    def analyze_product_documents(
        self,
        markdown_paths: list[str],
        product_context: dict | None = None,
        document_names: dict[str, str] | None = None,
    ) -> ProductAnalysis:
        """Analyze a product's documents; same contract as ``GeminiClient.analyze_product_documents``.

        Retries with the Gemini backoff (2s, 4s, ... up to 16s) on retryable API errors and on
        invalid output. Auth/config errors (401, 403, 400, 404, ...) are raised immediately.
        """
        from scripts.clients.llm import ErrorKind, classify_error  # avoid an import cycle

        user_prompt = build_user_prompt(markdown_paths, product_context, document_names)
        system_prompt = mistral_system_prompt()

        last_exception: Exception | None = None
        retry_delay = INITIAL_RETRY_DELAY

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"Mistral attempt {attempt}/{self.max_retries} ({self.model})")
                response = self.client.chat.complete(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.0,
                    timeout_ms=MISTRAL_TIMEOUT_MS,
                )
                text = _message_text(response)
                if text is None:
                    raise ValueError("Mistral API returned an empty response")
                analysis = ProductAnalysis.model_validate_json(text)
                logger.info(f"Mistral analyzed product on attempt {attempt}")
                return analysis
            except (ValueError, ValidationError) as e:
                last_exception = e
                logger.warning(f"Mistral attempt {attempt} returned invalid output: {e}")
            except Exception as e:
                last_exception = e
                if classify_error(e) in (ErrorKind.AUTH, ErrorKind.CONFIG):
                    logger.error(f"Mistral auth/config error, not retrying: {e}")
                    raise
                logger.warning(f"Mistral attempt {attempt} failed with error: {e}")

            if attempt < self.max_retries:
                logger.info(f"Retrying Mistral in {retry_delay:.1f} seconds...")
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)
            else:
                logger.error(f"All {self.max_retries} Mistral attempts failed")

        raise last_exception if last_exception else ValueError("Mistral analysis failed after all retries")
