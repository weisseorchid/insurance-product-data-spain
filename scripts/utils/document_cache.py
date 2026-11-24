"""Document cache management for PDFs and markdown files."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from scripts.utils.hashing import compute_file_sha256, get_cache_path


@dataclass
class CachedDocument:
    """Information about a cached document."""

    sha256: str
    size: int
    cache_path: Path
    exists: bool


class DocumentCache:
    """
    Content-addressed cache for insurance product documents.

    Documents are stored in a two-level directory structure:
    <cache_root>/<sha256[:2]>/<sha256>.<extension>
    """

    def __init__(self, cache_root: Path | str | None = None):
        """
        Initialize the document cache.

        Args:
            cache_root: Root directory for the cache.
                       If None, uses environment variable INSURANCE_DOCS_CACHE
                       or defaults to '.cache/insurance-docs'
        """
        if cache_root is None:
            cache_root = os.environ.get(
                "INSURANCE_DOCS_CACHE",
                ".cache/insurance-docs",
            )
        self.cache_root = Path(cache_root)

    def get_pdf_path(self, sha256: str) -> Path:
        """Get the cache path for a PDF."""
        return get_cache_path(sha256, "pdf", self.cache_root)

    def get_markdown_path(self, sha256: str) -> Path:
        """Get the cache path for a markdown file."""
        return get_cache_path(sha256, "md", self.cache_root)

    def store_pdf(self, source_path: Path) -> CachedDocument:
        """
        Store a PDF file in the cache.

        Args:
            source_path: Path to the PDF file

        Returns:
            CachedDocument with metadata
        """
        # Compute hash
        sha256 = compute_file_sha256(source_path)
        cache_path = self.get_pdf_path(sha256)

        # Create directory if needed
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        # Copy file if not already cached
        if not cache_path.exists():
            shutil.copy2(source_path, cache_path)

        return CachedDocument(
            sha256=sha256,
            size=source_path.stat().st_size,
            cache_path=cache_path,
            exists=True,
        )

    def store_markdown(self, content: str, sha256: str | None = None) -> CachedDocument:
        """
        Store markdown content in the cache.

        Args:
            content: Markdown content
            sha256: Optional pre-computed hash. If None, will be computed.

        Returns:
            CachedDocument with metadata
        """
        from scripts.utils.hashing import compute_string_sha256

        # Compute hash if not provided
        if sha256 is None:
            sha256 = compute_string_sha256(content)

        cache_path = self.get_markdown_path(sha256)

        # Create directory if needed
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        # Write content if not already cached
        if not cache_path.exists():
            cache_path.write_text(content, encoding="utf-8")

        return CachedDocument(
            sha256=sha256,
            size=len(content.encode("utf-8")),
            cache_path=cache_path,
            exists=True,
        )

    def get_pdf(self, sha256: str) -> CachedDocument:
        """
        Get information about a cached PDF.

        Args:
            sha256: SHA256 hash of the PDF

        Returns:
            CachedDocument (exists=False if not in cache)
        """
        cache_path = self.get_pdf_path(sha256)
        exists = cache_path.exists()

        return CachedDocument(
            sha256=sha256,
            size=cache_path.stat().st_size if exists else 0,
            cache_path=cache_path,
            exists=exists,
        )

    def get_markdown(self, sha256: str) -> CachedDocument:
        """
        Get information about a cached markdown file.

        Args:
            sha256: SHA256 hash of the markdown content

        Returns:
            CachedDocument (exists=False if not in cache)
        """
        cache_path = self.get_markdown_path(sha256)
        exists = cache_path.exists()

        return CachedDocument(
            sha256=sha256,
            size=cache_path.stat().st_size if exists else 0,
            cache_path=cache_path,
            exists=exists,
        )

    def read_markdown(self, sha256: str) -> str | None:
        """
        Read markdown content from cache.

        Args:
            sha256: SHA256 hash of the markdown content

        Returns:
            Markdown content or None if not in cache
        """
        cached = self.get_markdown(sha256)
        if not cached.exists:
            return None
        return cached.cache_path.read_text(encoding="utf-8")
