"""Tests for document validation utilities."""

from pathlib import Path

from scripts.utils.document_validation import (
    DuplicateMarkdownDetector,
    compute_markdown_hash,
    is_block_page,
    is_empty_or_near_empty,
    validate_markdown_content,
    validate_pdf_file,
    validate_pdf_magic_bytes,
)


def test_validate_pdf_magic_bytes_valid(tmp_path: Path):
    """Test PDF magic bytes validation with valid PDF."""
    pdf_file = tmp_path / "test.pdf"
    pdf_file.write_bytes(b"%PDF-1.4\n%Test PDF content")

    assert validate_pdf_magic_bytes(pdf_file) is True


def test_validate_pdf_magic_bytes_invalid(tmp_path: Path):
    """Test PDF magic bytes validation with invalid file."""
    pdf_file = tmp_path / "test.pdf"
    pdf_file.write_bytes(b"Not a PDF file")

    assert validate_pdf_magic_bytes(pdf_file) is False


def test_compute_markdown_hash():
    """Test markdown hash computation."""
    content = "# Test Document\n\nThis is a test."
    hash1 = compute_markdown_hash(content)
    hash2 = compute_markdown_hash(content)

    # Same content should produce same hash
    assert hash1 == hash2
    assert len(hash1) == 64  # SHA256 hex digest length

    # Different content should produce different hash
    different_content = "# Different Document"
    hash3 = compute_markdown_hash(different_content)
    assert hash1 != hash3


def test_is_block_page_cloudflare():
    """Test block page detection for Cloudflare."""
    cloudflare_content = """
# Pardon Our Interruption

As you were browsing something about your browser made us think you were a bot.

Please stand by while we check your browser...
"""
    assert is_block_page(cloudflare_content) is True


def test_is_block_page_captcha():
    """Test block page detection for captcha pages."""
    captcha_content = "Please complete the CAPTCHA to continue."
    assert is_block_page(captcha_content) is True


def test_is_block_page_valid_content():
    """Test that valid insurance content is not flagged as block page."""
    valid_content = """
# Seguro de Hogar

## Coberturas Básicas

- Incendio
- Robo
- Responsabilidad civil

## Condiciones Generales

Este seguro cubre los daños causados por incendio, robo y otros eventos...
"""
    assert is_block_page(valid_content) is False


def test_is_empty_or_near_empty():
    """Test empty/near-empty markdown detection."""
    # Empty
    assert is_empty_or_near_empty("") is True
    assert is_empty_or_near_empty("   ") is True

    # Near-empty (less than default 100 chars)
    assert is_empty_or_near_empty("Short content") is True

    # Valid length
    long_content = "x" * 150
    assert is_empty_or_near_empty(long_content) is False

    # Custom threshold
    assert is_empty_or_near_empty("Test", min_length=10) is True
    assert is_empty_or_near_empty("Test content here", min_length=10) is False


def test_validate_markdown_content_valid():
    """Test markdown validation with valid content."""
    content = "x" * 150  # Long enough
    result = validate_markdown_content(content)

    assert result.is_valid is True
    assert result.reason is None
    assert result.markdown_sha256 is not None


def test_validate_markdown_content_empty():
    """Test markdown validation with empty content."""
    result = validate_markdown_content("")

    assert result.is_valid is False
    assert result.reason is not None
    assert "Empty or near-empty" in result.reason
    assert result.markdown_sha256 is not None


def test_validate_markdown_content_block_page():
    """Test markdown validation with block page."""
    content = "Pardon Our Interruption\n\n" + "x" * 150
    result = validate_markdown_content(content)

    assert result.is_valid is False
    assert result.reason is not None
    assert "Bot/block page" in result.reason
    assert result.markdown_sha256 is not None


def test_validate_pdf_file_valid(tmp_path: Path):
    """Test PDF file validation with valid PDF."""
    pdf_file = tmp_path / "test.pdf"
    pdf_file.write_bytes(b"%PDF-1.4\n%Test PDF")

    result = validate_pdf_file(pdf_file)
    assert result.is_valid is True
    assert result.reason is None


def test_validate_pdf_file_not_found(tmp_path: Path):
    """Test PDF file validation with nonexistent file."""
    pdf_file = tmp_path / "nonexistent.pdf"

    result = validate_pdf_file(pdf_file)
    assert result.is_valid is False
    assert result.reason is not None
    assert "File not found" in result.reason


def test_validate_pdf_file_invalid_magic_bytes(tmp_path: Path):
    """Test PDF file validation with invalid magic bytes."""
    pdf_file = tmp_path / "fake.pdf"
    pdf_file.write_bytes(b"Not a PDF")

    result = validate_pdf_file(pdf_file)
    assert result.is_valid is False
    assert result.reason is not None
    assert "invalid magic bytes" in result.reason


def test_duplicate_markdown_detector():
    """Test duplicate markdown hash detection."""
    detector = DuplicateMarkdownDetector()

    # Add documents
    detector.add_document(Path("doc1.pdf"), "hash1")
    detector.add_document(Path("doc2.pdf"), "hash2")
    detector.add_document(Path("doc3.pdf"), "hash1")  # Duplicate hash

    # Check duplicates
    assert detector.has_duplicates() is True

    duplicates = detector.get_duplicates()
    assert "hash1" in duplicates
    assert len(duplicates["hash1"]) == 2
    assert "hash2" not in duplicates


def test_duplicate_markdown_detector_no_duplicates():
    """Test duplicate detector with no duplicates."""
    detector = DuplicateMarkdownDetector()

    detector.add_document(Path("doc1.pdf"), "hash1")
    detector.add_document(Path("doc2.pdf"), "hash2")

    assert detector.has_duplicates() is False
    assert detector.get_duplicates() == {}


def test_known_bad_hash():
    """Test that known Mutua bad hash is detected as block page."""
    # This is the actual Cloudflare block page content
    mutua_block_page = """# Pardon Our Interruption

As you were browsing something about your browser made us think you were a bot. There are a few reasons this might happen:

* You've disabled JavaScript in your web browser.
* You're a power user moving through this website with super-human speed.
* You've disabled cookies in your web browser.
* A third-party browser plugin, such as Ghostery or NoScript, is preventing JavaScript from running. \
Additional information is available in this [support article](http://ds.tl/help-third-party-plugins \
"Third party browser plugins that block javascript").

To regain access, please make sure that cookies and JavaScript are enabled before reloading the page.

### Please stand by

We're getting everything ready for you. The page is loading, and you'll be on your way in just a few moments.

Thanks for your patience!"""

    # Verify it's detected as block page
    assert is_block_page(mutua_block_page) is True

    # Verify hash matches known bad hash
    expected_hash = "9c2fcc5d899fb2a6196360ee14dfbff58676911c57fda1b59578702c341b0ff4"
    actual_hash = compute_markdown_hash(mutua_block_page)
    assert actual_hash == expected_hash

    # Verify validation fails
    result = validate_markdown_content(mutua_block_page)
    assert result.is_valid is False
    assert result.markdown_sha256 == expected_hash
