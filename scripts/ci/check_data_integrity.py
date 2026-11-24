#!/usr/bin/env python3
"""Validate JSONL data integrity: valid JSON, sorting, no duplicates."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Known duplicates in distributors (allowlist)
KNOWN_DISTRIBUTOR_DUPLICATES = {
    "AJ-0243EUS",
    "AJ-0266EUS",
    "C0161X1184962W",
    "C046807989823Z",
    "C046816075101X",
    "C046822111914J",
    "C046846034731R",
    "CS-F/0145",
    "E007",
    "F-047-CM",
    "J-0070-CAC",
    "J-0091EUS",
    "J-0093EUS",
    "J-0156-GA",
    "J-0202EUS",
    "J-068-CM",
}


def validate_jsonl_file(
    file_path: Path,
    sort_key: str,
    required_fields: list[str],
    allow_duplicates: set[str] | None = None,
) -> list[str]:
    """
    Validate a JSONL file.

    Args:
        file_path: Path to JSONL file
        sort_key: Key to check sorting by
        required_fields: List of required fields in each record
        allow_duplicates: Set of keys that are allowed to be duplicated

    Returns:
        List of error messages (empty if valid)
    """
    errors = []
    warnings = []

    if not file_path.exists():
        return [f"File not found: {file_path}"]

    try:
        records = []
        seen_keys = {}

        with open(file_path, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                # Validate JSON
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as e:
                    errors.append(f"Line {line_num}: Invalid JSON - {e}")
                    continue

                if not isinstance(record, dict):
                    errors.append(f"Line {line_num}: Expected JSON object, got {type(record).__name__}")
                    continue

                # Check required fields
                for field in required_fields:
                    if field not in record:
                        errors.append(f"Line {line_num}: Missing required field '{field}'")

                # Check for duplicates
                if sort_key in record:
                    key = record[sort_key]
                    if key in seen_keys:
                        if allow_duplicates and key in allow_duplicates:
                            warnings.append(
                                f"Line {line_num}: Duplicate key '{key}' (first seen on line {seen_keys[key]}) - allowlisted"
                            )
                        else:
                            errors.append(
                                f"Line {line_num}: Duplicate key '{key}' (first seen on line {seen_keys[key]})"
                            )
                    else:
                        seen_keys[key] = line_num

                records.append((line_num, record))

        # Check sorting (case-insensitive for strings)
        if records:
            prev_key = None
            for line_num, record in records:
                if sort_key not in record:
                    continue

                current_key = record[sort_key]
                # Use lowercase for string comparison to match common sorting
                current_key_lower = current_key.lower() if isinstance(current_key, str) else current_key
                prev_key_lower = (
                    prev_key.lower() if isinstance(prev_key, str) else prev_key if prev_key is not None else None
                )

                if prev_key_lower is not None and current_key_lower < prev_key_lower:
                    errors.append(
                        f"Line {line_num}: Records not sorted by '{sort_key}' "
                        f"('{current_key}' should come before previous key '{prev_key}')"
                    )
                prev_key = current_key

    except Exception as e:
        errors.append(f"Error reading file: {e}")

    return errors, warnings


def validate_product_index(index_path: Path) -> list[str]:
    """Validate a product index.json file against schema v1.

    Args:
        index_path: Path to index.json file

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    if not index_path.exists():
        return [f"File not found: {index_path}"]

    try:
        with open(index_path, encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list) or not data:
            errors.append("index.json must be a non-empty list")
            return errors

        index_entry = data[0]

        # Check top-level fields
        required_top_fields = ["company_key", "products"]
        for field in required_top_fields:
            if field not in index_entry:
                errors.append(f"Missing required top-level field: {field}")

        # Validate products
        products = index_entry.get("products", [])
        if not isinstance(products, list):
            errors.append("'products' must be a list")
            return errors

        for idx, product in enumerate(products):
            if not isinstance(product, dict):
                errors.append(f"Product {idx}: must be a dict")
                continue

            # Required fields in schema v1
            required_fields = ["product_id", "product_name", "company_key", "branches"]
            for field in required_fields:
                if field not in product:
                    errors.append(f"Product {idx} ({product.get('product_name', 'unknown')}): missing '{field}'")

            # Validate branches is a list
            if "branches" in product:
                branches = product["branches"]
                if not isinstance(branches, list):
                    errors.append(
                        f"Product {idx} ({product.get('product_name', 'unknown')}): 'branches' must be a list"
                    )
                elif not branches:
                    errors.append(
                        f"Product {idx} ({product.get('product_name', 'unknown')}): 'branches' cannot be empty"
                    )

            # Validate document_references if present
            if "document_references" in product:
                doc_refs = product["document_references"]
                if not isinstance(doc_refs, list):
                    errors.append(
                        f"Product {idx} ({product.get('product_name', 'unknown')}): 'document_references' must be a list"
                    )
                else:
                    for doc_idx, doc_ref in enumerate(doc_refs):
                        if not isinstance(doc_ref, dict):
                            errors.append(f"Product {idx}, doc {doc_idx}: must be a dict")
                            continue
                        if "filename" not in doc_ref or "pdf_sha256" not in doc_ref:
                            errors.append(f"Product {idx}, doc {doc_idx}: missing filename or pdf_sha256")

            # Check for old schema fields (should be removed)
            deprecated_fields = ["product_branch", "source_folder", "files"]
            for old_field in deprecated_fields:
                if old_field in product:
                    errors.append(
                        f"Product {idx} ({product.get('product_name', 'unknown')}): deprecated field '{old_field}' should be removed"
                    )

    except json.JSONDecodeError as e:
        errors.append(f"Invalid JSON: {e}")
    except Exception as e:
        errors.append(f"Error validating: {e}")

    return errors


def main() -> int:
    """Run all data integrity checks."""
    print("🔍 Checking data integrity...")
    print()

    repo_root = Path(__file__).parent.parent.parent
    all_errors = []
    all_warnings = []

    # Check main data files
    data_files = [
        ("data/insurance_companies.jsonl", "company_key", ["company_key", "denomination"]),
        ("data/insurance_distributors.jsonl", "distributor_key", ["distributor_key", "name"]),
        ("data/insurance_branches.jsonl", "code", ["code"]),  # branches only require 'code'
    ]

    for file_path, sort_key, required_fields in data_files:
        full_path = repo_root / file_path
        print(f"Validating {file_path}...")

        # Allow duplicates for distributors
        allow_dups = KNOWN_DISTRIBUTOR_DUPLICATES if "distributors" in file_path else None

        errors, warnings = validate_jsonl_file(full_path, sort_key, required_fields, allow_dups)

        if errors:
            all_errors.extend([f"{file_path}: {e}" for e in errors])
            for error in errors:
                print(f"  ❌ {error}")
        else:
            print("  ✅ Valid")

        if warnings:
            all_warnings.extend([f"{file_path}: {w}" for w in warnings])
            for warning in warnings:
                print(f"  ⚠️  {warning}")

        print()

    # Check product index.json files (schema v1 validation)
    index_files = list(repo_root.glob("data/products_by_insurance_company/*/index.json"))
    for index_file in index_files:
        print(f"Validating {index_file.relative_to(repo_root)}...")
        errors = validate_product_index(index_file)

        if errors:
            all_errors.extend([f"{index_file.relative_to(repo_root)}: {e}" for e in errors])
            for error in errors:
                print(f"  ❌ {error}")
        else:
            print("  ✅ Valid")
        print()

    # Check documents.jsonl files (skip sorting check - complex multi-key sort)
    documents_files = list(repo_root.glob("data/products_by_insurance_company/*/documents.jsonl"))
    bad_pdfs_warnings = []
    for doc_file in documents_files:
        print(f"Validating {doc_file.relative_to(repo_root)}...")
        # Only check JSON validity and required fields, not sorting
        errors_found = []
        with open(doc_file) as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    for field in ["product_id", "product_name", "filename", "pdf_sha256"]:
                        if field not in record:
                            errors_found.append(f"Line {line_num}: Missing required field '{field}'")

                    # Check if cache files exist and validate them
                    if "pdf_sha256" in record:
                        pdf_hash = record["pdf_sha256"]
                        pdf_cache_path = repo_root / ".cache" / "insurance-docs" / pdf_hash[:2] / f"{pdf_hash}.pdf"
                        if pdf_cache_path.exists():
                            # Check PDF magic bytes
                            with open(pdf_cache_path, "rb") as pf:
                                magic = pf.read(4)
                                if magic != b"%PDF":
                                    bad_pdfs_warnings.append(
                                        f"Line {line_num} ({record['filename']}): Cache file is not a real PDF (magic: {magic[:20]})"
                                    )

                    if "markdown_sha256" in record:
                        md_hash = record["markdown_sha256"]
                        md_cache_path = repo_root / ".cache" / "insurance-docs" / md_hash[:2] / f"{md_hash}.md"
                        if md_cache_path.exists():
                            # Check for block/cookie page indicators
                            with open(md_cache_path, encoding="utf-8", errors="ignore") as mf:
                                content = mf.read(5000).lower()  # First 5KB
                                block_indicators = [
                                    "cloudflare",
                                    "please stand by",
                                    "checking your browser",
                                    "enable cookies",
                                ]
                                if any(indicator in content for indicator in block_indicators):
                                    bad_pdfs_warnings.append(
                                        f"Line {line_num} ({record['filename']}): Markdown appears to be a block/cookie page"
                                    )

                except json.JSONDecodeError as e:
                    errors_found.append(f"Line {line_num}: Invalid JSON - {e}")

        if errors_found:
            all_errors.extend([f"{doc_file.relative_to(repo_root)}: {e}" for e in errors_found])
            for error in errors_found:
                print(f"  ❌ {error}")
        else:
            print("  ✅ Valid")
        print()

    # Report bad PDF warnings at the end
    if bad_pdfs_warnings:
        print("\n⚠️  Data quality issues (warnings):")
        all_warnings.extend(bad_pdfs_warnings)
        for warning in bad_pdfs_warnings:
            print(f"  ⚠️  {warning}")

    # Check runs.jsonl if it exists
    runs_file = repo_root / "data" / "runs.jsonl"
    if runs_file.exists():
        print(f"Validating {runs_file.relative_to(repo_root)}...")
        errors, warnings = validate_jsonl_file(
            runs_file,
            "started_at",
            ["script", "started_at"],
        )

        if errors:
            all_errors.extend([f"{runs_file.relative_to(repo_root)}: {e}" for e in errors])
            for error in errors:
                print(f"  ❌ {error}")
        else:
            print("  ✅ Valid")
        print()

    # Print summary
    if all_warnings:
        print(f"⚠️  {len(all_warnings)} warning(s):")
        for warning in all_warnings:
            print(f"  {warning}")
        print()

    if all_errors:
        print(f"❌ Data integrity check FAILED with {len(all_errors)} error(s)")
        return 1

    print("✅ Data integrity check PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
