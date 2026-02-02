"""Script to process PDFs for insurance companies and convert them to markdown.

This script takes an insurance company key (e.g., C0737) and:
1. Finds the company's folder in data/products_by_insurance_company/
2. Locates the sources/ subdirectory
3. Converts all PDFs in each product folder to markdown
4. Saves the markdown files alongside the original PDFs

Run with: uv run python -m scripts.process_pdfs --company-key C0737
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path

from insurance_product_data_sp.core.logging import logger
from scripts.config import INSURANCE_COMPANIES_JSON, PRODUCTS_STORAGE_PATH
from scripts.utils.pdf_processing import PDFConversionResult, convert_pdf_to_markdown
from scripts.utils.storage import ensure_directory, load_json, save_json
from scripts.utils.text_transformations import text_to_snake_case


def find_company_folder(company_key: str) -> Path | None:
    """
    Find the folder for an insurance company by its key.

    Args:
        company_key: The company key (e.g., C0737)

    Returns:
        Path to the company folder or None if not found
    """
    # Load companies data to get the company name
    try:
        companies = load_json(INSURANCE_COMPANIES_JSON)
    except FileNotFoundError:
        logger.error(f"Companies JSON file not found: {INSURANCE_COMPANIES_JSON}")
        return None

    # Find the company by key
    company = None
    for c in companies:
        if c.get("company_key") == company_key:
            company = c
            break

    if not company:
        logger.error(f"Company with key {company_key} not found in companies data")
        return None

    # Get the company name and convert to folder name
    company_name = company.get("denomination", "")
    if not company_name:
        logger.error(f"Company {company_key} has no denomination")
        return None

    folder_name = text_to_snake_case(company_name)
    company_folder = PRODUCTS_STORAGE_PATH / folder_name

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
    product_folder: Path, output_dir: Path | None = None
) -> dict[str, list[PDFConversionResult]]:
    """
    Process all PDFs in a product folder.

    Args:
        product_folder: Path to the product folder containing PDFs
        output_dir: Optional output directory for markdown files.
                   If None, saves alongside the original PDFs.

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
        result = convert_pdf_to_markdown(pdf_file)
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

    return {product_name: results}


def process_company_pdfs(
    company_key: str,
    output_dir: Path | str | None = None,
    save_summary: bool = True,
) -> dict[str, list[PDFConversionResult]]:
    """
    Process all PDFs for an insurance company.

    Args:
        company_key: The company key (e.g., C0737)
        output_dir: Optional output directory for markdown files.
                   If None, saves alongside the original PDFs.
        save_summary: Whether to save a processing summary JSON file

    Returns:
        Dictionary with product names as keys and lists of conversion results as values
    """
    # Find company folder
    company_folder = find_company_folder(company_key)
    if not company_folder:
        return {}

    # Get sources directory
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
        results = process_product_folder(product_folder, out_path)
        all_results.update(results)

    # Generate and save summary
    if save_summary:
        summary = generate_processing_summary(company_key, all_results)
        metadata_folder = company_folder / "metadata"
        ensure_directory(metadata_folder)
        summary_path = metadata_folder / "processing_summary.json"
        save_json(summary, summary_path)
        logger.info(f"Saved processing summary to: {summary_path}")

    return all_results


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

    args = parser.parse_args()

    logger.info(f"Starting PDF processing for company: {args.company_key}")

    results = process_company_pdfs(
        company_key=args.company_key,
        output_dir=args.output_dir,
        save_summary=not args.no_summary,
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
