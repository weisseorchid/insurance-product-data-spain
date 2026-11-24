"""Tests for PDF processing with validation."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.utils.pdf_processing import convert_pdf_to_markdown


@pytest.fixture
def mock_markitdown():
    """Mock MarkItDown converter."""
    with patch("scripts.utils.pdf_processing.MarkItDown") as mock:
        yield mock


def test_convert_pdf_to_markdown_with_validation_valid(tmp_path: Path, mock_markitdown):
    """Test PDF conversion with validation on valid PDF."""
    # Create valid PDF
    pdf_file = tmp_path / "test.pdf"
    pdf_file.write_bytes(b"%PDF-1.4\n%Test")

    # Mock converter to return valid content
    mock_result = MagicMock()
    mock_result.text_content = "x" * 150  # Valid length
    mock_markitdown.return_value.convert.return_value = mock_result

    result = convert_pdf_to_markdown(pdf_file, validate=True)

    assert result.success is True
    assert result.validation_failed is False
    assert result.markdown_sha256 is not None


def test_convert_pdf_to_markdown_with_validation_invalid_magic_bytes(tmp_path: Path):
    """Test PDF conversion with validation on invalid PDF."""
    # Create invalid PDF
    pdf_file = tmp_path / "fake.pdf"
    pdf_file.write_bytes(b"Not a PDF")

    result = convert_pdf_to_markdown(pdf_file, validate=True)

    assert result.success is False
    assert result.validation_failed is True
    assert result.error is not None
    assert "invalid magic bytes" in result.error


def test_convert_pdf_to_markdown_with_validation_block_page(tmp_path: Path, mock_markitdown):
    """Test PDF conversion with validation on block page content."""
    # Create valid PDF
    pdf_file = tmp_path / "test.pdf"
    pdf_file.write_bytes(b"%PDF-1.4\n%Test")

    # Mock converter to return block page
    mock_result = MagicMock()
    mock_result.text_content = "Pardon Our Interruption\n\n" + "x" * 150
    mock_markitdown.return_value.convert.return_value = mock_result

    result = convert_pdf_to_markdown(pdf_file, validate=True)

    assert result.success is False
    assert result.validation_failed is True
    assert result.error is not None
    assert "Bot/block page" in result.error
    assert result.markdown_sha256 is not None


def test_convert_pdf_to_markdown_with_validation_empty_content(tmp_path: Path, mock_markitdown):
    """Test PDF conversion with validation on empty content."""
    # Create valid PDF
    pdf_file = tmp_path / "test.pdf"
    pdf_file.write_bytes(b"%PDF-1.4\n%Test")

    # Mock converter to return empty content
    mock_result = MagicMock()
    mock_result.text_content = "Short"
    mock_markitdown.return_value.convert.return_value = mock_result

    result = convert_pdf_to_markdown(pdf_file, validate=True)

    assert result.success is False
    assert result.validation_failed is True
    assert result.error is not None
    assert "Empty or near-empty" in result.error


def test_convert_pdf_to_markdown_without_validation(tmp_path: Path, mock_markitdown):
    """Test PDF conversion without validation."""
    # Create invalid PDF (should still work without validation)
    pdf_file = tmp_path / "fake.pdf"
    pdf_file.write_bytes(b"Not a PDF")

    # Mock converter
    mock_result = MagicMock()
    mock_result.text_content = "Short"
    mock_markitdown.return_value.convert.return_value = mock_result

    result = convert_pdf_to_markdown(pdf_file, validate=False)

    # Should succeed without validation
    assert result.success is True
    assert result.validation_failed is False


def test_convert_pdf_to_markdown_file_not_found():
    """Test PDF conversion with nonexistent file."""
    result = convert_pdf_to_markdown(Path("/nonexistent/file.pdf"))

    assert result.success is False
    assert result.error is not None
    assert "File not found" in result.error


def test_convert_pdf_to_markdown_not_pdf_extension(tmp_path: Path):
    """Test PDF conversion with wrong extension."""
    txt_file = tmp_path / "test.txt"
    txt_file.write_text("Not a PDF")

    result = convert_pdf_to_markdown(txt_file)

    assert result.success is False
    assert result.error is not None
    assert "Not a PDF file" in result.error
