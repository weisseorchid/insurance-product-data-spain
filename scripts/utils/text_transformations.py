"""Text transformation utilities."""

import re


def text_to_snake_case(text: str) -> str:
    """
    Convert a string to snake_case.

    Args:
        text: The string to convert

    Returns:
        The string in snake_case format
    """

    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s-]+", "_", text)
    text = re.sub(r"_+", "_", text)
    text = text.strip("_")

    return text


_LEADING_JUNK = re.compile(r"^[\s:;,./]+")
# DGSFP renders "www." in front of the stored value, producing "www.HTTPS//..." or "www.WWW.X".
_SPURIOUS_WWW_PREFIX = re.compile(r"^www\.(?=(?:https?\b|www\.))", re.IGNORECASE)
# Scheme with missing/mangled separator, e.g. "HTTPS//host", "http:/host", "https:host", "http:\\\\host".
_BROKEN_SCHEME = re.compile(r"^(https?)(?::[/\\]{0,2}|[/\\]{1,2})(?=[^/\\])", re.IGNORECASE)
_SCHEME_OK = re.compile(r"^https?://", re.IGNORECASE)
# "ww.host" (missing a "w") right after the scheme or at the start.
_TRUNCATED_WWW = re.compile(r"^((?:https?://)?)ww\.(?!w)", re.IGNORECASE)


def normalize_website(value: str | None) -> str | None:
    """Repair malformed website values scraped from the DGSFP registry.

    Only clearly broken values are rewritten; well-formed values are returned
    unchanged (apart from surrounding whitespace), so the function is idempotent
    and does not churn otherwise-valid data. Repairs:

    - spurious leading ``www.`` before a scheme or another ``www.``
      (``www.HTTPS//WWW.X.ES/`` -> ``https://WWW.X.ES/``, ``www.www.x.es`` -> ``www.x.es``)
    - mangled scheme separators (``HTTPS//x``, ``http:x``, backslashes -> ``https://x``)
    - leading punctuation (``:www.x.es`` -> ``www.x.es``)
    - truncated ``ww.`` host prefix (``https://WW.MAPFRE.COM`` -> ``https://www.MAPFRE.COM``)

    Args:
        value: Raw website string (may be None or blank)

    Returns:
        The repaired website, or None for empty input
    """
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None

    original = text
    text = _LEADING_JUNK.sub("", text)
    while _SPURIOUS_WWW_PREFIX.match(text):
        text = _SPURIOUS_WWW_PREFIX.sub("", text, count=1)

    if not _SCHEME_OK.match(text):
        text = _BROKEN_SCHEME.sub(lambda m: f"{m.group(1).lower()}://", text, count=1)

    text = _TRUNCATED_WWW.sub(lambda m: f"{m.group(1)}www.", text, count=1)

    if text == original:
        return original
    return text or None
