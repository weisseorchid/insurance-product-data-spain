"""Script to process PDFs for insurance companies and convert them to markdown.

This script takes an insurance company key (e.g., C0737) and converts its PDFs to
validated markdown. Two sources are supported:

- cache (default when there is no sources/ folder): documents listed in the company's
  documents.jsonl whose PDF is in the document cache (.cache/insurance-docs) are
  converted; the markdown is stored in the cache and markdown_sha256 is updated in
  documents.jsonl. This is the normal path after scripts.fetch_product_documents
  (which already converts, so this mostly re-converts with --force or fills gaps).
- sources (legacy): PDFs in sources/{product}/ are converted and the markdown is saved
  next to them.

Run with: uv run python -m scripts.process_pdfs --company-key C0737 [--source auto|cache|sources] [--force]
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path

from insurance_product_data_sp.core.logging import logger
from scripts.utils.companies import company_display_name, company_folder_path, find_company
from scripts.utils.document_cache import DocumentCache
from scripts.utils.document_store import convert_cached_pdf, load_documents, save_documents
from scripts.utils.document_validation import is_known_or_block_page_hash
from scripts.utils.pdf_processing import PDFConversionResult, convert_pdf_to_markdown
from scripts.utils.run_logging import log_validation_failure
from scripts.utils.storage import ensure_directory, save_json


def find_company_folder(company_key: str) -> Path | None:
    """
    Find the folder for an insurance company by its key.

    Args:
        company_key: The company key (e.g., C0737)

    Returns:
        Path to the company folder or None if not found
    """
    try:
        company = find_company(company_key)
    except FileNotFoundError as e:
        logger.error(str(e))
        return None

    if not company:
        logger.error(f"Company with key {company_key} not found in companies data")
        return None

    if not company_display_name(company):
        logger.error(f"Company {company_key} has no denomination")
        return None

    company_folder = company_folder_path(company)

    if not company_folder.exists():
        logger.error(f"Company folder not found: {company_folder}")
        return None

    logger.info(f"Found company folder: {company_folder}")
    return company_folder


def get_sources_directory(company_folder: Path) -> Path | None:
    """
    Get the sources directory for a company folder.

    Args:
        company_folder: Path to the company folder

    Returns:
        Path to the sources directory or None if not found
    """
    sources_dir = company_folder / "sources"

    if not sources_dir.exists():
        logger.warning(f"Sources directory not found: {sources_dir}")
        return None

    return sources_dir


def process_product_folder(
    product_folder: Path, output_dir: Path | None = None, company_key: str | None = None
) -> dict[str, list[PDFConversionResult]]:
    """
    Process all PDFs in a product folder.

    Args:
        product_folder: Path to the product folder containing PDFs
        output_dir: Optional output directory for markdown files.
                   If None, saves alongside the original PDFs.
        company_key: Optional company key for logging

    Returns:
        Dictionary with product name as key and list of conversion results as value
    """
    product_name = product_folder.name
    pdf_files = list(product_folder.glob("*.pdf"))

    if not pdf_files:
        logger.info(f"No PDF files found in {product_folder}")
        return {product_name: []}

    logger.info(f"Processing {len(pdf_files)} PDF files for product: {product_name}")

    results = []
    for pdf_file in pdf_files:
        result = convert_pdf_to_markdown(pdf_file, validate=True)
        results.append(result)

        if result.success:
            # Determine output path
            if output_dir:
                md_output_dir = output_dir / product_name
                ensure_directory(md_output_dir)
                md_path = md_output_dir / f"{pdf_file.stem}.md"
            else:
                md_path = pdf_file.with_suffix(".md")

            # Save markdown content
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(result.markdown_content)

            logger.info(f"Saved markdown to: {md_path}")
        elif result.validation_failed:
            # Log validation failures
            log_validation_failure(
                script_name="process_pdfs",
                file_path=result.source_path,
                reason=result.error or "Unknown validation error",
                company_key=company_key,
                product_name=product_name,
                markdown_sha256=result.markdown_sha256,
            )
            logger.warning(f"Skipped saving markdown for {pdf_file.name} due to validation failure")

    return {product_name: results}


def process_company_pdfs(
    company_key: str,
    output_dir: Path | str | None = None,
    save_summary: bool = True,
    source: str = "auto",
    force: bool = False,
) -> dict[str, list[PDFConversionResult]]:
    """
    Process all PDFs for an insurance company.

    Args:
        company_key: The company key (e.g., C0737)
        output_dir: Optional output directory for markdown files.
                   If None, saves alongside the original PDFs.
        save_summary: Whether to save a processing summary JSON file
        source: "cache" (documents.jsonl + cache), "sources" (legacy folder) or "auto"
        force: Re-convert cached PDFs even if their markdown is already cached

    Returns:
        Dictionary with product names as keys and lists of conversion results as values
    """
    # Find company folder
    company_folder = find_company_folder(company_key)
    if not company_folder:
        return {}

    use_sources = source == "sources" or (source == "auto" and (company_folder / "sources").exists())
    if not use_sources:
        all_cached = process_cached_documents(company_folder, company_key=company_key, force=force)
        if save_summary:
            _save_summary(company_folder, generate_processing_summary(company_key, all_cached))
        return all_cached

    # Legacy: sources/{product}/*.pdf
    sources_dir = get_sources_directory(company_folder)
    if not sources_dir:
        logger.warning(f"No sources directory found for company {company_key}")
        return {}

    # Get all product folders
    product_folders = [d for d in sources_dir.iterdir() if d.is_dir()]
    if not product_folders:
        logger.warning(f"No product folders found in {sources_dir}")
        return {}

    logger.info(f"Found {len(product_folders)} product folders for {company_key}")

    # Process each product folder
    all_results: dict[str, list[PDFConversionResult]] = {}
    out_path = Path(output_dir) if output_dir else None

    for product_folder in product_folders:
        results = process_product_folder(product_folder, out_path, company_key=company_key)
        all_results.update(results)

    # Generate and save summary
    if save_summary:
        _save_summary(company_folder, generate_processing_summary(company_key, all_results))

    return all_results


def _save_summary(company_folder: Path, summary: dict) -> None:
    metadata_folder = company_folder / "metadata"
    ensure_directory(metadata_folder)
    summary_path = metadata_folder / "processing_summary.json"
    save_json(summary, summary_path)
    logger.info(f"Saved processing summary to: {summary_path}")


def process_cached_documents(
    company_folder: Path,
    company_key: str | None = None,
    force: bool = False,
    cache: DocumentCache | None = None,
) -> dict[str, list[PDFConversionResult]]:
    """
    Convert cached PDFs referenced by documents.jsonl to markdown (stored in the cache).

    Args:
        company_folder: Path to the company folder
        company_key: Optional company key for logging
        force: Re-convert even if the markdown is already cached
        cache: Document cache (default: .cache/insurance-docs)

    Returns:
        Dictionary with product name as key and list of conversion results as value
    """
    cache = cache or DocumentCache()
    records = load_documents(company_folder)
    results: dict[str, list[PDFConversionResult]] = {}
    converted: dict[str, str | None] = {}  # pdf_sha256 -> markdown_sha256 (convert each PDF once)
    changed = False

    for record in records:
        product_name = str(record.get("product_name", "unknown"))
        pdf_sha = record.get("pdf_sha256")
        md_sha = record.get("markdown_sha256")
        if not pdf_sha:
            continue
        pdf = cache.get_pdf(pdf_sha)
        if not pdf.exists:
            logger.warning(f"PDF not in cache for {product_name}/{record.get('filename')}; fetch it first")
            continue
        if (
            not force
            and md_sha
            and cache.get_markdown(md_sha).exists
            and not is_known_or_block_page_hash(str(md_sha))
        ):
            continue
        if pdf_sha not in converted:
            outcome = convert_cached_pdf(pdf_sha, cache)
            converted[pdf_sha] = outcome.markdown_sha256 if outcome.success else None
            results.setdefault(product_name, []).append(
                PDFConversionResult(
                    source_path=pdf.cache_path,
                    markdown_content="",
                    success=outcome.success,
                    error=outcome.error,
                    markdown_sha256=outcome.markdown_sha256,
                    validation_failed=outcome.validation_failed,
                )
            )
            if not outcome.success and outcome.validation_failed:
                log_validation_failure(
                    script_name="process_pdfs",
                    file_path=str(record.get("filename")),
                    reason=outcome.error or "Unknown validation error",
                    company_key=company_key,
                    product_name=product_name,
                    markdown_sha256=outcome.markdown_sha256,
                )
        new_md = converted[pdf_sha]
        if new_md is None and md_sha:
            # Validation failed (block page / empty): do not keep a stale markdown hash
            record.pop("markdown_sha256", None)
            changed = True
        elif new_md and new_md != md_sha:
            record["markdown_sha256"] = new_md
            changed = True

    if changed:
        save_documents(company_folder, records)
        logger.info(f"Updated markdown_sha256 in {company_folder / 'documents.jsonl'}")
    return results


def generate_processing_summary(company_key: str, results: dict[str, list[PDFConversionResult]]) -> dict:
    """
    Generate a summary of the PDF processing results.

    Args:
        company_key: The company key
        results: Dictionary of processing results by product

    Returns:
        Summary dictionary
    """
    total_files = 0
    successful = 0
    failed = 0
    products_summary = []

    for product_name, product_results in results.items():
        product_total = len(product_results)
        product_success = sum(1 for r in product_results if r.success)
        product_failed = product_total - product_success

        total_files += product_total
        successful += product_success
        failed += product_failed

        products_summary.append(
            {
                "product_name": product_name,
                "total_files": product_total,
                "successful": product_success,
                "failed": product_failed,
                "files": [
                    {
                        "file_name": r.source_path.name,
                        "success": r.success,
                        "error": r.error,
                    }
                    for r in product_results
                ],
            }
        )

    return {
        "schema_version": "1.0",
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "processor": {
            "name": "process_pdfs",
            "version": "1.0.0",
            "converter": "markitdown[pdf]",
        },
        "company_key": company_key,
        "summary": {
            "total_files": total_files,
            "successful": successful,
            "failed": failed,
        },
        "products": products_summary,
    }


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description="Process PDFs for an insurance company and convert to markdown")
    parser.add_argument(
        "--company-key",
        "-k",
        required=True,
        help="Insurance company key (e.g., C0737)",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        help="Output directory for markdown files (default: save alongside PDFs)",
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="Don't save processing summary JSON",
    )

    parser.add_argument(
        "--source",
        choices=["auto", "cache", "sources"],
        default="auto",
        help="cache = documents.jsonl + .cache/insurance-docs; sources = legacy sources/ folder; "
        "auto = sources/ if it exists, else cache (default)",
    )
    parser.add_argument("--force", action="store_true", help="Re-convert even if markdown is already cached")

    args = parser.parse_args()

    logger.info(f"Starting PDF processing for company: {args.company_key}")

    results = process_company_pdfs(
        company_key=args.company_key,
        output_dir=args.output_dir,
        save_summary=not args.no_summary,
        source=args.source,
        force=args.force,
    )

    # Print summary
    total = sum(len(r) for r in results.values())
    successful = sum(1 for r_list in results.values() for r in r_list if r.success)
    failed = total - successful

    logger.info("Processing complete!")
    logger.info(f"Total files: {total}")
    logger.info(f"Successful: {successful}")
    logger.info(f"Failed: {failed}")


if __name__ == "__main__":
    main()
