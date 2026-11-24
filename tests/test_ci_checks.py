"""Tests for CI check scripts."""

from pathlib import Path

import pytest

from scripts.ci.check_data_integrity import (
    KNOWN_BAD_MARKDOWN_HASHES,
    check_block_pages,
    check_duplicate_markdown_hashes,
)
from scripts.utils.document_validation import compute_markdown_hash

# Known Mutua block page content (hash: 9c2fcc5d899fb2a6196360ee14dfbff58676911c57fda1b59578702c341b0ff4)
MUTUA_BLOCK_PAGE = """# Pardon Our Interruption

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


@pytest.fixture
def mock_products_dir(tmp_path: Path):
    """Create mock products directory structure."""
    products_dir = tmp_path / "products_by_insurance_company"
    products_dir.mkdir()

    # Create company folder
    company_dir = products_dir / "test_company"
    company_dir.mkdir()

    sources_dir = company_dir / "sources"
    sources_dir.mkdir()

    # Create product folder
    product_dir = sources_dir / "test_product"
    product_dir.mkdir()

    return products_dir, company_dir, product_dir


def test_check_block_pages_no_issues(mock_products_dir):
    """Test block page check with valid markdown."""
    products_dir, _, product_dir = mock_products_dir

    # Create valid markdown
    md_file = product_dir / "valid.md"
    md_file.write_text("# Valid Document\n\n" + "x" * 200)

    result = check_block_pages(products_dir)
    assert result is True


def test_check_block_pages_with_block_page(mock_products_dir):
    """Test block page check with Cloudflare block page."""
    products_dir, _, product_dir = mock_products_dir

    # Create block page
    md_file = product_dir / "block.md"
    md_file.write_text("Pardon Our Interruption\n\nPlease stand by")

    result = check_block_pages(products_dir, strict=False)
    # Should fail because this is not in allowlist
    assert result is False


def test_check_block_pages_allowlisted(mock_products_dir):
    """Test block page check with allowlisted hash."""
    products_dir, _, product_dir = mock_products_dir

    # Create the known Mutua block page
    md_file = product_dir / "mutua_block.md"
    md_file.write_text(MUTUA_BLOCK_PAGE)

    # Verify hash matches known bad hash
    assert compute_markdown_hash(MUTUA_BLOCK_PAGE) in KNOWN_BAD_MARKDOWN_HASHES

    # Should pass in non-strict mode (allowlisted)
    result = check_block_pages(products_dir, strict=False)
    assert result is True

    # Should fail in strict mode
    result = check_block_pages(products_dir, strict=True)
    assert result is False


def test_check_duplicate_markdown_hashes_no_duplicates(mock_products_dir):
    """Test duplicate hash check with no duplicates."""
    products_dir, _, product_dir = mock_products_dir

    # Create unique markdown files
    for i in range(3):
        md_file = product_dir / f"doc{i}.md"
        md_file.write_text(f"# Document {i}\n\n" + "x" * 200)

    result = check_duplicate_markdown_hashes(products_dir)
    assert result is True


def test_check_duplicate_markdown_hashes_with_duplicates(mock_products_dir):
    """Test duplicate hash check with duplicate content."""
    products_dir, _, product_dir = mock_products_dir

    # Create duplicate markdown files
    duplicate_content = "# Same Content\n\n" + "x" * 200
    md_file1 = product_dir / "doc1.md"
    md_file1.write_text(duplicate_content)

    md_file2 = product_dir / "doc2.md"
    md_file2.write_text(duplicate_content)

    result = check_duplicate_markdown_hashes(products_dir, strict=False)
    # Should fail because duplicates are not allowlisted
    assert result is False


def test_check_duplicate_markdown_hashes_allowlisted(mock_products_dir):
    """Test duplicate hash check with allowlisted duplicates."""
    products_dir, _, product_dir = mock_products_dir

    # Create the known Mutua block page (allowlisted)
    md_file1 = product_dir / "mutua1.md"
    md_file1.write_text(MUTUA_BLOCK_PAGE)

    md_file2 = product_dir / "mutua2.md"
    md_file2.write_text(MUTUA_BLOCK_PAGE)

    # Should pass in non-strict mode (allowlisted)
    result = check_duplicate_markdown_hashes(products_dir, strict=False)
    assert result is True

    # Should fail in strict mode
    result = check_duplicate_markdown_hashes(products_dir, strict=True)
    assert result is False


def test_check_duplicate_markdown_hashes_mixed(mock_products_dir):
    """Test duplicate hash check with both allowlisted and new duplicates."""
    products_dir, _, product_dir = mock_products_dir

    # Create allowlisted duplicate
    md_file1 = product_dir / "mutua1.md"
    md_file1.write_text(MUTUA_BLOCK_PAGE)

    md_file2 = product_dir / "mutua2.md"
    md_file2.write_text(MUTUA_BLOCK_PAGE)

    # Create new duplicate (not allowlisted)
    new_duplicate = "# New Duplicate\n\n" + "x" * 200
    md_file3 = product_dir / "new1.md"
    md_file3.write_text(new_duplicate)

    md_file4 = product_dir / "new2.md"
    md_file4.write_text(new_duplicate)

    # Should fail because new duplicates exist
    result = check_duplicate_markdown_hashes(products_dir, strict=False)
    assert result is False
