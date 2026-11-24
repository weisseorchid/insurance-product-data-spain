#!/usr/bin/env python3
"""Migrate product data to schema v1.

This script migrates products_by_insurance_company/*/index.json files
to the new product schema v1 format with:
- Consistent product_id (instead of prduct_id typo)
- company_key field
- branches as list
- document_references linking to documents.jsonl
- analysis_path pointing to analysis JSON
- fetched_at timestamp
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def normalize_branches(branch_value: str | list[str]) -> list[str]:
    """Normalize branch value to list of strings."""
    if isinstance(branch_value, list):
        return [str(b).strip() for b in branch_value]
    return [str(branch_value).strip()]


def load_documents_map(company_folder: Path) -> dict[str, list[dict]]:
    """Load documents.jsonl and create a map by product_id."""
    documents_file = company_folder / "documents.jsonl"
    if not documents_file.exists():
        return {}

    docs_by_product: dict[str, list[dict]] = {}
    with open(documents_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            doc = json.loads(line)
            product_id = doc.get("product_id")
            if product_id:
                docs_by_product.setdefault(product_id, []).append(
                    {
                        "filename": doc["filename"],
                        "pdf_sha256": doc["pdf_sha256"],
                        "markdown_sha256": doc.get("markdown_sha256"),
                        "doc_type": doc.get("doc_type"),
                    }
                )
    return docs_by_product


def migrate_company_index(company_folder: Path, dry_run: bool = False) -> bool:
    """Migrate a single company's index.json to schema v1.

    Returns True if changes were made, False if already migrated or no changes needed.
    """
    index_path = company_folder / "index.json"
    if not index_path.exists():
        print(f"⚠️  No index.json in {company_folder.name}")
        return False

    with open(index_path, encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list) or not data:
        print(f"⚠️  Invalid index.json format in {company_folder.name}")
        return False

    index_entry = data[0]
    company_key = index_entry.get("company_key")
    fetched_at = index_entry.get("fetched_at")
    products = index_entry.get("products", [])

    if not company_key:
        print(f"❌ Missing company_key in {company_folder.name}")
        return False

    # Load documents map
    docs_by_product = load_documents_map(company_folder)

    # Check if already migrated (has 'branches' field instead of 'product_branch')
    if products and "branches" in products[0]:
        print(f"✓  Already migrated: {company_folder.name}")
        return False

    # Migrate products
    changes_made = False
    for product in products:
        # Check if needs migration
        if "branches" not in product:
            changes_made = True

            # Normalize branches
            branch_value = product.get("product_branch", [])
            product["branches"] = normalize_branches(branch_value)

            # Remove old field
            if "product_branch" in product:
                del product["product_branch"]

            # Rename source_url to match singular (keep for backward compat)
            if "source_url" in product:
                product["source_url"] = product["source_url"]

            # Add company_key
            product["company_key"] = company_key

            # Add fetched_at
            if fetched_at:
                product["fetched_at"] = fetched_at

            # Add document_references
            product_id = product.get("product_id")
            if product_id and product_id in docs_by_product:
                product["document_references"] = docs_by_product[product_id]
            else:
                product["document_references"] = []

            # Add analysis_path if analysis file exists
            product_name = product.get("product_name")
            if product_name:
                analysis_file = company_folder / "analysis" / f"{product_name}.json"
                if analysis_file.exists():
                    product["analysis_path"] = f"analysis/{product_name}.json"
                else:
                    product["analysis_path"] = None

            # Remove legacy fields that are no longer in index
            for old_field in ["source_folder", "files"]:
                if old_field in product:
                    del product[old_field]

    if not changes_made:
        print(f"✓  No changes needed: {company_folder.name}")
        return False

    if dry_run:
        print(f"🔍 Would migrate: {company_folder.name}")
        return True

    # Write back
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
        f.write("\n")

    print(f"✅ Migrated: {company_folder.name}")
    return True


def main() -> int:
    """Run migration for all companies."""
    import argparse

    parser = argparse.ArgumentParser(description="Migrate product data to schema v1")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be changed")
    args = parser.parse_args()

    repo_root = Path(__file__).parent.parent
    products_path = repo_root / "data" / "products_by_insurance_company"

    if not products_path.exists():
        print(f"❌ Products folder not found: {products_path}")
        return 1

    print("🔄 Migrating product data to schema v1...\n")

    migrated_count = 0
    for company_folder in sorted(products_path.iterdir()):
        if not company_folder.is_dir():
            continue

        if migrate_company_index(company_folder, dry_run=args.dry_run):
            migrated_count += 1

    print(f"\n{'🔍 Would migrate' if args.dry_run else '✅ Migrated'}: {migrated_count} companies")

    if args.dry_run and migrated_count > 0:
        print("\nRun without --dry-run to apply changes.")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
