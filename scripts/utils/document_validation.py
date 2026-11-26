"""Document validation utilities for PDF and markdown validation.

This module provides validation functions to detect:
- Invalid PDFs (magic bytes check)
- Bot/block pages (Cloudflare, captcha pages)
- Empty or near-empty markdown
- Duplicate markdown hashes across different PDFs
"""

import hashlib
import json
import re
from pathlib import Path
from typing import NamedTuple

from insurance_product_data_sp.core.logging import logger

# Minimum number of characters for valid markdown content
MIN_MARKDOWN_LENGTH = 100

# PDF magic bytes (PDF files start with %PDF-)
PDF_MAGIC_BYTES = b"%PDF-"

# Short docs are scanned in full; longer policy markdown is only checked in the title region.
SHORT_BLOCK_PAGE_MAX_CHARS = 2_000
TITLE_REGION_MAX_CHARS = 1_500

# Bot/block page patterns (interstitials only — never bare status codes like "403"/"404")
BLOCK_PAGE_PATTERNS = [
    r"Pardon Our Interruption",
    r"Please stand by",
    r"Cloudflare",
    r"Just a moment",
    r"checking your browser",
    r"Enable JavaScript and cookies to continue",
    r"This website is using a security service to protect itself",
    r"Ray ID:",
    r"Cloudflare Ray ID",
    r"Performance & security by Cloudflare",
    r"captcha",
    r"CAPTCHA",
    r"bot detection",
    r"Access Denied",
    r"403 Forbidden",
    r"404 Not Found",
    r"Request unsuccessful",
    r"Powered by Incapsula",
    r"Incapsula incident",
    r"errors\.edgesuite\.net",
    r"Reference #[0-9]+\.[0-9a-f]+\.[0-9a-f]+",  # Akamai reference id
]

# Compile patterns for efficiency
BLOCK_PAGE_REGEX = re.compile("|".join(BLOCK_PAGE_PATTERNS), re.IGNORECASE)


class ValidationResult(NamedTuple):
    """Result of document validation."""

    is_valid: bool
    reason: str | None = None
    markdown_sha256: str | None = None


def validate_pdf_magic_bytes(pdf_path: Path) -> bool:
    """
    Check if a file is a valid PDF by verifying its magic bytes.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        True if the file has valid PDF magic bytes, False otherwise
    """
    try:
        with open(pdf_path, "rb") as f:
            header = f.read(5)
            return header == PDF_MAGIC_BYTES
    except Exception as e:
        logger.error(f"Failed to read file {pdf_path}: {e}")
        return False


def compute_markdown_hash(markdown_content: str) -> str:
    """
    Compute SHA256 hash of markdown content.

    Args:
        markdown_content: The markdown text content

    Returns:
        Hexadecimal SHA256 hash of the content
    """
    return hashlib.sha256(markdown_content.encode("utf-8")).hexdigest()


def _block_page_scan_region(markdown_content: str) -> str:
    """Region to search for interstitials: full short docs, else title/heading prefix only."""
    if len(markdown_content) <= SHORT_BLOCK_PAGE_MAX_CHARS:
        return markdown_content
    return markdown_content[:TITLE_REGION_MAX_CHARS]


def is_block_page(markdown_content: str) -> bool:
    """
    Check if markdown content appears to be a bot/block page.

    Scans the whole document when it is short (typical interstitial), otherwise only the
    title/heading region so a mention inside a long policy PDF is not treated as a block.

    Args:
        markdown_content: The markdown text content

    Returns:
        True if content appears to be a block page, False otherwise
    """
    return bool(BLOCK_PAGE_REGEX.search(_block_page_scan_region(markdown_content)))


def load_known_block_page_hashes(path: Path | None = None) -> set[str]:
    """Load known block-page markdown hashes from data/quality/known_block_page_hashes.jsonl."""
    if path is None:
        from scripts.config import PROJECT_ROOT

        path = PROJECT_ROOT / "data" / "quality" / "known_block_page_hashes.jsonl"
    if not path.exists():
        return set()
    hashes: set[str] = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            md_hash = record.get("markdown_sha256")
            if md_hash:
                hashes.add(str(md_hash))
    return hashes


def is_known_or_block_page_hash(markdown_sha256: str | None, known_hashes: set[str] | None = None) -> bool:
    """True if the hash is listed in known_block_page_hashes.jsonl."""
    if not markdown_sha256:
        return False
    known = known_hashes if known_hashes is not None else load_known_block_page_hashes()
    return markdown_sha256 in known


def markdown_is_unusable(
    markdown_content: str | None = None,
    markdown_sha256: str | None = None,
    known_hashes: set[str] | None = None,
) -> bool:
    """True if content or hash is a known block/error page that must not enter the knowledge base."""
    if markdown_sha256 and is_known_or_block_page_hash(markdown_sha256, known_hashes):
        return True
    if markdown_content is not None and is_block_page(markdown_content):
        return True
    return False


def is_empty_or_near_empty(markdown_content: str, min_length: int = MIN_MARKDOWN_LENGTH) -> bool:
    """
    Check if markdown content is empty or near-empty.

    Args:
        markdown_content: The markdown text content
        min_length: Minimum number of characters required

    Returns:
        True if content is too short, False otherwise
    """
    return len(markdown_content.strip()) < min_length


def validate_markdown_content(
    markdown_content: str,
    source_pdf_path: Path | None = None,
    min_length: int = MIN_MARKDOWN_LENGTH,
) -> ValidationResult:
    """
    Validate markdown content for quality issues.

    Args:
        markdown_content: The markdown text content
        source_pdf_path: Optional path to source PDF for logging
        min_length: Minimum number of characters required

    Returns:
        ValidationResult with validation status and reason
    """
    # Compute hash
    md_hash = compute_markdown_hash(markdown_content)

    # Check if empty or near-empty
    if is_empty_or_near_empty(markdown_content, min_length):
        reason = f"Empty or near-empty markdown ({len(markdown_content)} chars < {min_length} required)"
        logger.warning(f"Validation failed for {source_pdf_path or 'unknown'}: {reason}")
        return ValidationResult(is_valid=False, reason=reason, markdown_sha256=md_hash)

    # Check if block page
    if is_block_page(markdown_content):
        reason = "Bot/block page detected (Cloudflare, captcha, or similar)"
        logger.warning(f"Validation failed for {source_pdf_path or 'unknown'}: {reason}")
        return ValidationResult(is_valid=False, reason=reason, markdown_sha256=md_hash)

    return ValidationResult(is_valid=True, reason=None, markdown_sha256=md_hash)


def validate_pdf_file(pdf_path: Path) -> ValidationResult:
    """
    Validate a PDF file for quality issues.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        ValidationResult with validation status and reason
    """
    # Check if file exists
    if not pdf_path.exists():
        reason = f"File not found: {pdf_path}"
        logger.error(reason)
        return ValidationResult(is_valid=False, reason=reason)

    # Check PDF magic bytes
    if not validate_pdf_magic_bytes(pdf_path):
        reason = f"Not a valid PDF (invalid magic bytes): {pdf_path}"
        logger.warning(reason)
        return ValidationResult(is_valid=False, reason=reason)

    return ValidationResult(is_valid=True, reason=None)


class DuplicateMarkdownDetector:
    """
    Detector for duplicate markdown hashes across different PDFs.

    Tracks markdown hashes and their source PDFs to detect when multiple
    different PDFs produce the same markdown (usually indicating block pages).
    """

    def __init__(self):
        """Initialize the detector with empty tracking."""
        self.hash_to_pdfs: dict[str, list[Path]] = {}

    def add_document(self, pdf_path: Path, markdown_hash: str):
        """
        Register a PDF and its markdown hash.

        Args:
            pdf_path: Path to the PDF file
            markdown_hash: SHA256 hash of the markdown content
        """
        if markdown_hash not in self.hash_to_pdfs:
            self.hash_to_pdfs[markdown_hash] = []
        self.hash_to_pdfs[markdown_hash].append(pdf_path)

    def get_duplicates(self) -> dict[str, list[Path]]:
        """
        Get all markdown hashes that are shared by multiple PDFs.

        Returns:
            Dictionary mapping markdown hash to list of PDF paths (only entries with 2+ PDFs)
        """
        return {hash_val: pdfs for hash_val, pdfs in self.hash_to_pdfs.items() if len(pdfs) > 1}

    def has_duplicates(self) -> bool:
        """
        Check if any duplicate markdown hashes have been detected.

        Returns:
            True if duplicates exist, False otherwise
        """
        return any(len(pdfs) > 1 for pdfs in self.hash_to_pdfs.values())
