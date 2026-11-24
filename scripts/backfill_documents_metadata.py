"""Backfill documents.jsonl metadata from existing PDF and markdown files.

This script scans all companies' source directories, computes hashes,
and creates documents.jsonl files with metadata for each document.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from insurance_product_data_sp.core.logging import logger
from scripts.config import PRODUCTS_STORAGE_PATH
from scripts.utils.document_cache import DocumentCache
from scripts.utils.hashing import compute_file_sha256, compute_string_sha256
from scripts.utils.jsonl import save_jsonl
from scripts.utils.storage import load_json


def classify_document_type(filename: str) -> str:
    """
    Classify document type based on filename.

    Args:
        filename: Document filename (without extension)

    Returns:
        Document type classification
    """
    filename_lower = filename.lower()

    if "ipid" in filename_lower or "pid" in filename_lower:
        return "ipid"
    elif "condiciones_generales" in filename_lower or "ccgg" in filename_lower or "_cg_" in filename_lower:
        return "condiciones_generales"
    elif "condiciones" in filename_lower or "ccll" in filename_lower or "_cl_" in filename_lower:
        return "condiciones_particulares"
    elif "folleto" in filename_lower:
        return "folleto"
    elif "nota_informativa" in filename_lower or "guia" in filename_lower:
        return "nota_informativa"
    else:
        return "other"


def backfill_company_documents(
    company_folder: Path,
    cache: DocumentCache,
    dry_run: bool = False,
) -> dict:
    """
    Backfill documents metadata for a single company.

    Args:
        company_folder: Path to company folder
        cache: DocumentCache instance
        dry_run: If True, don't write files

    Returns:
        Summary dictionary
    """
    company_name = company_folder.name
    sources_dir = company_folder / "sources"

    if not sources_dir.exists():
        logger.warning(f"No sources directory for {company_name}")
        return {"company": company_name, "products": 0, "documents": 0}

    # Load index.json to get product metadata if available
    index_path = company_folder / "index.json"
    index_data = {}
    if index_path.exists():
        try:
            index_list = load_json(index_path)
            if isinstance(index_list, list) and len(index_list) > 0:
                products = index_list[0].get("products", [])
                index_data = {p.get("product_name"): p for p in products}
        except Exception as e:
            logger.warning(f"Failed to load index.json for {company_name}: {e}")

    # Process each product folder
    all_documents = []
    product_count = 0

    for product_dir in sorted(sources_dir.iterdir()):
        if not product_dir.is_dir():
            continue

        product_name = product_dir.name
        product_info = index_data.get(product_name, {})
        product_id = product_info.get("prduct_id", product_info.get("product_id"))
        source_url = product_info.get("source_url")

        # Find all PDF files
        pdf_files = sorted(product_dir.glob("*.pdf"))
        if not pdf_files:
            continue

        product_count += 1

        for pdf_file in pdf_files:
            md_file = pdf_file.with_suffix(".md")

            # Compute PDF hash
            pdf_sha256 = compute_file_sha256(pdf_file)
            pdf_size = pdf_file.stat().st_size

            # Store in cache
            if not dry_run:
                cache.store_pdf(pdf_file)

            # Compute markdown hash if exists
            md_sha256 = None
            if md_file.exists():
                md_content = md_file.read_text(encoding="utf-8")
                md_sha256 = compute_string_sha256(md_content)
                if not dry_run:
                    cache.store_markdown(md_content, md_sha256)

            # Classify document type
            doc_type = classify_document_type(pdf_file.stem)

            # Try to extract retrieval date from somewhere
            # For now, use file modification time as fallback
            retrieved_at = datetime.fromtimestamp(pdf_file.stat().st_mtime, tz=timezone.utc).isoformat()

            document_entry = {
                "product_id": product_id or f"urn:{company_name}/{product_name}",
                "product_name": product_name,
                "doc_type": doc_type,
                "filename": pdf_file.name,
                "source_url": source_url,  # May be None
                "retrieved_at": retrieved_at,
                "pdf_sha256": pdf_sha256,
                "pdf_size": pdf_size,
                "markdown_sha256": md_sha256,  # May be None if not yet converted
            }

            all_documents.append(document_entry)

    # Sort by product_name, then doc_type, then filename
    all_documents.sort(key=lambda d: (d["product_name"], d["doc_type"], d["filename"]))

    # Save to documents.jsonl
    if all_documents and not dry_run:
        documents_path = company_folder / "documents.jsonl"
        save_jsonl(all_documents, documents_path)
        logger.info(f"Saved {len(all_documents)} document entries to {documents_path}")

    return {
        "company": company_name,
        "products": product_count,
        "documents": len(all_documents),
    }


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Backfill documents.jsonl metadata from existing files"
    )
    parser.add_argument(
        "--company",
        "-c",
        help="Process only a specific company (by folder name)",
    )
    parser.add_argument(
        "--cache-root",
        help="Cache root directory (default: from env or .cache/insurance-docs)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't write files or populate cache",
    )

    args = parser.parse_args()

    cache = DocumentCache(args.cache_root)
    logger.info(f"Using cache root: {cache.cache_root}")

    if not PRODUCTS_STORAGE_PATH.exists():
        logger.error(f"Products storage path not found: {PRODUCTS_STORAGE_PATH}")
        return

    # Find all company folders
    company_folders = [d for d in PRODUCTS_STORAGE_PATH.iterdir() if d.is_dir()]

    if args.company:
        company_folders = [d for d in company_folders if d.name == args.company]
        if not company_folders:
            logger.error(f"Company folder '{args.company}' not found")
            return

    logger.info(f"Processing {len(company_folders)} companies")

    summaries = []
    for company_folder in sorted(company_folders):
        logger.info(f"Processing {company_folder.name}")
        summary = backfill_company_documents(company_folder, cache, args.dry_run)
        summaries.append(summary)

    # Print final summary
    total_products = sum(s["products"] for s in summaries)
    total_documents = sum(s["documents"] for s in summaries)

    logger.info("\n" + "=" * 60)
    logger.info("BACKFILL SUMMARY")
    logger.info("=" * 60)
    for summary in summaries:
        logger.info(
            f"  {summary['company']}: "
            f"{summary['products']} products, {summary['documents']} documents"
        )
    logger.info(f"\nTotal: {total_products} products, {total_documents} documents")

    if args.dry_run:
        logger.info("\nDRY RUN - no files were written")


if __name__ == "__main__":
    main()
