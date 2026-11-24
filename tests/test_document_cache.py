"""Tests for document cache."""

from pathlib import Path

from scripts.utils.document_cache import DocumentCache


def test_cache_initialization_default():
    """Test cache initialization with default path."""
    cache = DocumentCache()
    # Should use env var or default
    assert cache.cache_root is not None


def test_cache_initialization_custom():
    """Test cache initialization with custom path."""
    cache = DocumentCache("/custom/path")
    assert cache.cache_root == Path("/custom/path")


def test_cache_initialization_from_env(monkeypatch):
    """Test cache initialization from environment variable."""
    monkeypatch.setenv("INSURANCE_DOCS_CACHE", "/env/cache")
    cache = DocumentCache()
    assert cache.cache_root == Path("/env/cache")


def test_get_pdf_path(tmp_path):
    """Test PDF cache path generation."""
    cache = DocumentCache(tmp_path)
    path = cache.get_pdf_path("abcd1234")
    assert path == tmp_path / "ab" / "abcd1234.pdf"


def test_get_markdown_path(tmp_path):
    """Test markdown cache path generation."""
    cache = DocumentCache(tmp_path)
    path = cache.get_markdown_path("1234abcd")
    assert path == tmp_path / "12" / "1234abcd.md"


def test_store_pdf(tmp_path):
    """Test storing a PDF in the cache."""
    # Create a test PDF
    source = tmp_path / "source.pdf"
    content = b"PDF content here"
    source.write_bytes(content)

    # Store in cache
    cache_root = tmp_path / "cache"
    cache = DocumentCache(cache_root)
    cached = cache.store_pdf(source)

    # Verify
    assert cached.exists
    assert cached.size == len(content)
    assert cached.cache_path.exists()
    assert cached.cache_path.read_bytes() == content


def test_store_pdf_idempotent(tmp_path):
    """Test that storing the same PDF twice doesn't duplicate."""
    source = tmp_path / "source.pdf"
    source.write_bytes(b"content")

    cache_root = tmp_path / "cache"
    cache = DocumentCache(cache_root)

    # Store twice
    cached1 = cache.store_pdf(source)
    cached2 = cache.store_pdf(source)

    # Should have same hash and path
    assert cached1.sha256 == cached2.sha256
    assert cached1.cache_path == cached2.cache_path


def test_store_markdown(tmp_path):
    """Test storing markdown content."""
    cache = DocumentCache(tmp_path)
    content = "# Markdown content\n\nTest"

    cached = cache.store_markdown(content)

    assert cached.exists
    assert cached.cache_path.exists()
    assert cached.cache_path.read_text(encoding="utf-8") == content


def test_get_markdown_missing(tmp_path):
    """Test getting markdown that doesn't exist."""
    cache = DocumentCache(tmp_path)
    cached = cache.get_markdown("nonexistent_hash")

    assert not cached.exists
    assert cached.size == 0


def test_read_markdown(tmp_path):
    """Test reading markdown from cache."""
    cache = DocumentCache(tmp_path)
    content = "Test markdown"

    # Store first
    cached = cache.store_markdown(content)

    # Read back
    read_content = cache.read_markdown(cached.sha256)
    assert read_content == content


def test_read_markdown_missing(tmp_path):
    """Test reading nonexistent markdown."""
    cache = DocumentCache(tmp_path)
    result = cache.read_markdown("nonexistent")
    assert result is None
