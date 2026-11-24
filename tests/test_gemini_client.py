"""Tests for Gemini client with retry logic (mocked, no live calls)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from scripts.clients.gemini import GeminiClient


@pytest.fixture
def mock_genai_client():
    """Mock google.genai.Client."""
    with patch("scripts.clients.gemini.genai.Client") as mock:
        yield mock


@pytest.fixture
def test_markdown_files(tmp_path: Path):
    """Create test markdown files."""
    files = []
    for i in range(2):
        md_file = tmp_path / f"doc{i}.md"
        md_file.write_text(f"# Document {i}\n\nContent here." * 50)
        files.append(str(md_file))
    return files


def test_compute_input_hash(test_markdown_files):
    """Test input hash computation."""
    hash1 = GeminiClient.compute_input_hash(test_markdown_files)
    hash2 = GeminiClient.compute_input_hash(test_markdown_files)

    # Same files should produce same hash
    assert hash1 == hash2
    assert len(hash1) == 64  # SHA256 hex


def test_compute_input_hash_order_independent(test_markdown_files):
    """Test that input hash is order-independent (sorted)."""
    hash1 = GeminiClient.compute_input_hash(test_markdown_files)
    hash2 = GeminiClient.compute_input_hash(list(reversed(test_markdown_files)))

    # Order should not matter
    assert hash1 == hash2


def test_analyze_product_documents_success(mock_genai_client, test_markdown_files):
    """Test successful analysis on first attempt."""
    client = GeminiClient(max_retries=3)

    # Mock successful response
    mock_response = MagicMock()
    mock_response.text = """{
        "product_summary": {
            "product_type": "Seguro de Hogar",
            "description_es": "Test insurance",
            "insurance_company": "Test Company"
        },
        "obligations": {
            "duration": "Annual",
            "renewal_type": "automatic"
        },
        "contract_terms": {
            "duration": "Annual",
            "renewal_type": "automatic"
        },
        "geographic_coverage": {
            "primary_territory": "Spain"
        }
    }"""

    client.client.models.generate_content.return_value = mock_response  # type: ignore

    result = client.analyze_product_documents(test_markdown_files)

    # Should succeed
    assert result is not None
    assert result.product_summary.product_type == "Seguro de Hogar"


def test_analyze_product_documents_retry_on_validation_error(mock_genai_client, test_markdown_files):
    """Test retry logic on validation error."""
    client = GeminiClient(max_retries=3)

    # Mock responses: first fails validation, second succeeds
    mock_response_bad = MagicMock()
    mock_response_bad.text = '{"invalid": "data"}'  # Will fail validation

    mock_response_good = MagicMock()
    mock_response_good.text = """{
        "product_summary": {
            "product_type": "Seguro de Hogar",
            "description_es": "Test insurance",
            "insurance_company": "Test Company"
        },
        "obligations": {
            "duration": "Annual",
            "renewal_type": "automatic"
        },
        "contract_terms": {
            "duration": "Annual",
            "renewal_type": "automatic"
        },
        "geographic_coverage": {
            "primary_territory": "Spain"
        }
    }"""

    client.client.models.generate_content.side_effect = [mock_response_bad, mock_response_good]  # type: ignore

    # Should retry and succeed on second attempt
    with patch("scripts.clients.gemini.time.sleep"):  # Skip sleep in tests
        result = client.analyze_product_documents(test_markdown_files)

    assert result is not None
    assert client.client.models.generate_content.call_count == 2  # type: ignore


def test_analyze_product_documents_all_retries_fail(mock_genai_client, test_markdown_files):
    """Test that all retries fail and exception is raised."""
    client = GeminiClient(max_retries=3)

    # Mock always failing responses
    mock_response = MagicMock()
    mock_response.text = '{"invalid": "data"}'
    client.client.models.generate_content.return_value = mock_response  # type: ignore

    # Should fail after all retries
    with patch("scripts.clients.gemini.time.sleep"):  # Skip sleep in tests
        with pytest.raises((ValidationError, ValueError)):
            client.analyze_product_documents(test_markdown_files)

    assert client.client.models.generate_content.call_count == 3  # type: ignore


def test_analyze_product_documents_none_response(mock_genai_client, test_markdown_files):
    """Test handling of None response."""
    client = GeminiClient(max_retries=2)

    # Mock None response
    mock_response = MagicMock()
    mock_response.text = None
    client.client.models.generate_content.return_value = mock_response  # type: ignore

    # Should fail after retries
    with patch("scripts.clients.gemini.time.sleep"):
        with pytest.raises(ValueError, match="None response"):
            client.analyze_product_documents(test_markdown_files)


def test_analyze_product_documents_with_context(mock_genai_client, test_markdown_files):
    """Test analysis with product context."""
    client = GeminiClient()

    mock_response = MagicMock()
    mock_response.text = """{
        "product_summary": {
            "product_type": "Seguro de Hogar",
            "description_es": "Test insurance",
            "insurance_company": "Test Company"
        },
        "obligations": {
            "duration": "Annual",
            "renewal_type": "automatic"
        },
        "contract_terms": {
            "duration": "Annual",
            "renewal_type": "automatic"
        },
        "geographic_coverage": {
            "primary_territory": "Spain"
        }
    }"""

    client.client.models.generate_content.return_value = mock_response  # type: ignore

    context = {
        "product_name": "Test Product",
        "product_branch": "09",
        "company": "Test Company",
    }

    result = client.analyze_product_documents(test_markdown_files, product_context=context)

    assert result is not None
    # Verify context was used in the prompt
    call_args = client.client.models.generate_content.call_args  # type: ignore
    assert "Test Product" in call_args[1]["contents"][0]
