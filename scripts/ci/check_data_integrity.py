"""Data integrity checks for committed product data.

This script verifies the quality of committed product data by checking for:
- Bot/block pages in committed markdown files
- Duplicate markdown hashes across different PDFs
- Known bad documents (quarantined/allowlisted)

Exit codes:
- 0: All checks passed
- 1: Checks failed
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

from insurance_product_data_sp.core.logging import logger
from scripts.config import PRODUCTS_STORAGE_PATH
from scripts.utils.document_validation import compute_markdown_hash, is_block_page

# Known bad markdown hashes that are allowlisted (Mutua Madrileña Cloudflare blocks)
# These should not cause CI failure but should be flagged in reports
KNOWN_BAD_MARKDOWN_HASHES = {
    "9c2fcc5d899fb2a6196360ee14dfbff58676911c57fda1b59578702c341b0ff4": {
        "reason": "Cloudflare block page",
        "company": "Mutua Madrileña",
        "note": "19 Mutua Madrileña markdown files share this hash (Cloudflare 'Pardon Our Interruption' page)",
    }
}


def check_block_pages(products_dir: Path, strict: bool = False) -> bool:
    """
    Check all committed markdown files for bot/block pages.

    Args:
        products_dir: Path to products_by_insurance_company directory
        strict: If True, fail on any block page (even allowlisted ones)

    Returns:
        True if all checks passed, False otherwise
    """
    logger.info("Checking for bot/block pages in committed markdown files...")

    all_passed = True
    block_page_count = 0
    allowlisted_count = 0

    markdown_files = list(products_dir.rglob("*.md"))
    logger.info(f"Found {len(markdown_files)} markdown files to check")

    for md_file in markdown_files:
        try:
            content = md_file.read_text(encoding="utf-8")
            md_hash = compute_markdown_hash(content)

            if is_block_page(content):
                # Check if this is a known bad hash
                if md_hash in KNOWN_BAD_MARKDOWN_HASHES and not strict:
                    known_info = KNOWN_BAD_MARKDOWN_HASHES[md_hash]
                    logger.warning(
                        f"[ALLOWLISTED] Block page detected: {md_file.relative_to(products_dir)}\n"
                        f"  Hash: {md_hash}\n"
                        f"  Reason: {known_info['reason']}\n"
                        f"  Note: {known_info['note']}"
                    )
                    allowlisted_count += 1
                else:
                    logger.error(f"[FAIL] Block page detected: {md_file.relative_to(products_dir)}\n  Hash: {md_hash}")
                    block_page_count += 1
                    all_passed = False

        except Exception as e:
            logger.error(f"Failed to read {md_file}: {e}")
            all_passed = False

    if allowlisted_count > 0:
        logger.warning(f"Found {allowlisted_count} allowlisted block pages (not failing CI)")

    if block_page_count > 0:
        logger.error(f"Found {block_page_count} new block pages (failing CI)")

    return all_passed


def check_duplicate_markdown_hashes(products_dir: Path, strict: bool = False) -> bool:
    """
    Check for duplicate markdown hashes across different PDFs.

    Args:
        products_dir: Path to products_by_insurance_company directory
        strict: If True, fail on any duplicate (even allowlisted ones)

    Returns:
        True if all checks passed, False otherwise
    """
    logger.info("Checking for duplicate markdown hashes across PDFs...")

    # Build a map of markdown hash -> list of PDF paths
    hash_to_md_files: dict[str, list[Path]] = defaultdict(list)

    markdown_files = list(products_dir.rglob("*.md"))

    for md_file in markdown_files:
        try:
            content = md_file.read_text(encoding="utf-8")
            md_hash = compute_markdown_hash(content)
            hash_to_md_files[md_hash].append(md_file)
        except Exception as e:
            logger.error(f"Failed to read {md_file}: {e}")
            return False

    # Find duplicates
    duplicates = {hash_val: files for hash_val, files in hash_to_md_files.items() if len(files) > 1}

    if not duplicates:
        logger.info("No duplicate markdown hashes found")
        return True

    all_passed = True
    new_duplicate_count = 0
    allowlisted_duplicate_count = 0

    for md_hash, md_files in duplicates.items():
        # Check if this is a known bad hash
        if md_hash in KNOWN_BAD_MARKDOWN_HASHES and not strict:
            known_info = KNOWN_BAD_MARKDOWN_HASHES[md_hash]
            logger.warning(
                f"[ALLOWLISTED] Duplicate markdown hash: {md_hash}\n"
                f"  Reason: {known_info['reason']}\n"
                f"  Note: {known_info['note']}\n"
                f"  Files ({len(md_files)}):"
            )
            for f in md_files:
                logger.warning(f"    - {f.relative_to(products_dir)}")
            allowlisted_duplicate_count += 1
        else:
            logger.error(
                f"[FAIL] Duplicate markdown hash detected: {md_hash}\n"
                f"  Multiple different PDFs produced the same markdown.\n"
                f"  Files ({len(md_files)}):"
            )
            for f in md_files:
                logger.error(f"    - {f.relative_to(products_dir)}")
            new_duplicate_count += 1
            all_passed = False

    if allowlisted_duplicate_count > 0:
        logger.warning(f"Found {allowlisted_duplicate_count} allowlisted duplicate hashes (not failing CI)")

    if new_duplicate_count > 0:
        logger.error(f"Found {new_duplicate_count} new duplicate markdown hashes (failing CI)")

    return all_passed


def main():
    """Main entry point for data integrity checks."""
    parser = argparse.ArgumentParser(description="Check data integrity for committed product data")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Strict mode: fail even on allowlisted issues",
    )
    parser.add_argument(
        "--products-dir",
        type=Path,
        default=PRODUCTS_STORAGE_PATH,
        help=f"Path to products_by_insurance_company directory (default: {PRODUCTS_STORAGE_PATH})",
    )

    args = parser.parse_args()

    if not args.products_dir.exists():
        logger.error(f"Products directory not found: {args.products_dir}")
        sys.exit(1)

    logger.info(f"Running data integrity checks on {args.products_dir}")
    logger.info(f"Strict mode: {args.strict}")

    # Run checks
    block_pages_ok = check_block_pages(args.products_dir, strict=args.strict)
    duplicates_ok = check_duplicate_markdown_hashes(args.products_dir, strict=args.strict)

    # Report summary
    logger.info("\n" + "=" * 60)
    logger.info("Data Integrity Check Summary")
    logger.info("=" * 60)
    logger.info(f"Block pages check: {'PASSED' if block_pages_ok else 'FAILED'}")
    logger.info(f"Duplicate hashes check: {'PASSED' if duplicates_ok else 'FAILED'}")
    logger.info("=" * 60)

    if block_pages_ok and duplicates_ok:
        logger.info("✓ All data integrity checks passed")
        sys.exit(0)
    else:
        logger.error("✗ Data integrity checks failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
