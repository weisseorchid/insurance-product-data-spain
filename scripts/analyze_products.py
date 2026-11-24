"""Script to analyze insurance products using Gemini AI.

This script takes an insurance company key (e.g., C0737) and:
1. Finds the company's folder in data/products_by_insurance_company/
2. Reads the index.json to get all products
3. For each product, finds the markdown files in sources/{product_name}/
4. Analyzes all markdown files using Gemini to extract structured information
5. Saves the analysis results to analysis/{product_name}.json

Run with: uv run python -m scripts.analyze_products --company-key C0737
"""

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from insurance_product_data_sp.core.logging import logger
from insurance_product_data_sp.schemas import InsuranceProduct, ProductAnalysis
from scripts.clients.gemini import GEMINI_MODEL, SCHEMA_VERSION, GeminiClient
from scripts.config import INSURANCE_COMPANIES_JSON, PRODUCTS_STORAGE_PATH
from scripts.utils.document_validation import compute_markdown_hash
from scripts.utils.run_logging import log_analysis_failure
from scripts.utils.storage import ensure_directory, load_json, save_json
from scripts.utils.text_transformations import text_to_snake_case

# Known bad markdown hashes (Mutua Madrileña Cloudflare blocks)
KNOWN_BAD_MARKDOWN_HASHES = {
    "9c2fcc5d899fb2a6196360ee14dfbff58676911c57fda1b59578702c341b0ff4",
}

# Companies with known quality issues
KNOWN_BAD_COMPANIES = {
    "mutua_madrileña_automovilista_sociedad_de_seguros_a_prima_fija",
}


@dataclass
class ProductAnalysisResult:
    """Result of analyzing a single product."""

    product_name: str
    product_id: str
    success: bool
    analysis: ProductAnalysis | None = None
    error: str | None = None
    markdown_files_processed: int = 0
    skipped: bool = False
    skip_reason: str | None = None
    has_quality_issues: bool = False


def has_known_bad_markdown(markdown_files: list[Path]) -> tuple[bool, str | None]:
    """
    Check if any markdown file has a known bad hash.

    Args:
        markdown_files: List of markdown file paths

    Returns:
        Tuple of (has_bad_hash, bad_hash_found)
    """
    for md_file in markdown_files:
        try:
            content = md_file.read_text(encoding="utf-8")
            md_hash = compute_markdown_hash(content)
            if md_hash in KNOWN_BAD_MARKDOWN_HASHES:
                return True, md_hash
        except Exception:
            pass
    return False, None


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


def load_product_index(company_folder: Path) -> list[dict] | None:
    """
    Load the product index for a company.

    Args:
        company_folder: Path to the company folder

    Returns:
        List of product entries from index.json or None if not found
    """
    index_path = company_folder / "index.json"

    if not index_path.exists():
        logger.error(f"Index file not found: {index_path}")
        return None

    try:
        index_data = load_json(index_path)
        # index.json is a list with one item containing "products"
        if isinstance(index_data, list) and len(index_data) > 0:
            return index_data[0].get("products", [])
        return []
    except Exception as e:
        logger.error(f"Failed to load index.json: {e}")
        return None


def get_product_markdown_files(company_folder: Path, product_name: str) -> list[Path]:
    """
    Get all markdown files for a product.

    Args:
        company_folder: Path to the company folder
        product_name: Name of the product (folder name in sources/)

    Returns:
        List of paths to markdown files
    """
    product_folder = company_folder / "sources" / product_name

    if not product_folder.exists():
        logger.warning(f"Product folder not found: {product_folder}")
        return []

    markdown_files = list(product_folder.glob("*.md"))
    return sorted(markdown_files)


def should_skip_analysis(
    company_folder: Path,
    product_entry: dict,
    markdown_files: list[Path],
    client: GeminiClient,
) -> tuple[bool, str | None]:
    """
    Check if analysis should be skipped (idempotency check).

    Args:
        company_folder: Path to the company folder
        product_entry: Product entry from index.json
        markdown_files: List of markdown files for this product
        client: GeminiClient instance

    Returns:
        Tuple of (should_skip, reason)
    """
    product_name = product_entry.get("product_name", "unknown")
    analysis_folder = company_folder / "analysis"
    output_path = analysis_folder / f"{product_name}.json"

    if not output_path.exists():
        return False, None

    try:
        # Load existing analysis
        existing = load_json(output_path)
        existing_metadata = existing.get("metadata", {})

        # Check if provenance exists
        if "analysis_provenance" not in existing_metadata:
            return False, "No provenance in existing analysis"

        provenance = existing_metadata["analysis_provenance"]

        # Check if model and schema version match
        if provenance.get("model") != client.model:
            return False, f"Model changed: {provenance.get('model')} -> {client.model}"

        if provenance.get("schema_version") != SCHEMA_VERSION:
            return False, f"Schema version changed: {provenance.get('schema_version')} -> {SCHEMA_VERSION}"

        # Compute current input hash
        current_input_hash = client.compute_input_hash([str(f) for f in markdown_files])

        if provenance.get("input_hash") != current_input_hash:
            return False, "Input files changed"

        logger.info(f"Skipping analysis for {product_name}: already up-to-date")
        return True, "Already analyzed with current inputs and schema"

    except Exception as e:
        logger.warning(f"Failed to check existing analysis for {product_name}: {e}")
        return False, "Failed to load existing analysis"


def analyze_single_product(
    client: GeminiClient,
    company_folder: Path,
    product_entry: dict,
    company_name: str,
    skip_if_exists: bool = True,
) -> ProductAnalysisResult:
    """
    Analyze a single product using Gemini.

    Args:
        client: GeminiClient instance
        company_folder: Path to the company folder
        product_entry: Product entry from index.json
        company_name: Name of the insurance company
        skip_if_exists: Whether to skip if analysis already exists and is up-to-date

    Returns:
        ProductAnalysisResult with the analysis or error
    """
    product_name = product_entry.get("product_name", "unknown")
    product_id = product_entry.get("prduct_id", product_entry.get("product_id", "unknown"))
    product_branch = product_entry.get("product_branch", "unknown")

    logger.info(f"Analyzing product: {product_name} ({product_id})")

    # Get markdown files for this product
    markdown_files = get_product_markdown_files(company_folder, product_name)

    if not markdown_files:
        logger.warning(f"No markdown files found for product: {product_name}")
        return ProductAnalysisResult(
            product_name=product_name,
            product_id=product_id,
            success=False,
            error="No markdown files found",
        )

    logger.info(f"Found {len(markdown_files)} markdown files for {product_name}")

    # Check for known quality issues
    has_bad_hash, bad_hash = has_known_bad_markdown(markdown_files)
    has_quality_issues = has_bad_hash or company_folder.name in KNOWN_BAD_COMPANIES

    if has_quality_issues:
        logger.warning(
            f"Product {product_name} has known quality issues (bad_hash={bad_hash}, company={company_folder.name})"
        )

    # Check if we should skip analysis (idempotency)
    if skip_if_exists:
        should_skip, skip_reason = should_skip_analysis(company_folder, product_entry, markdown_files, client)
        if should_skip:
            return ProductAnalysisResult(
                product_name=product_name,
                product_id=product_id,
                success=True,
                skipped=True,
                skip_reason=skip_reason,
                markdown_files_processed=len(markdown_files),
                has_quality_issues=has_quality_issues,
            )

    # Build product context for Gemini
    product_context = {
        "product_name": product_name,
        "product_branch": product_branch,
        "company": company_name,
    }

    try:
        # Analyze using Gemini
        analysis = client.analyze_product_documents(
            markdown_paths=[str(f) for f in markdown_files],
            product_context=product_context,
        )

        return ProductAnalysisResult(
            product_name=product_name,
            product_id=product_id,
            success=True,
            analysis=analysis,
            markdown_files_processed=len(markdown_files),
            has_quality_issues=has_quality_issues,
        )

    except Exception as e:
        logger.error(f"Failed to analyze product {product_name}: {e}")

        # Log analysis failure
        company_key = None
        try:
            companies = load_json(INSURANCE_COMPANIES_JSON)
            for c in companies:
                if text_to_snake_case(c.get("denomination", "")) == company_folder.name:
                    company_key = c.get("company_key")
                    break
        except Exception:
            pass

        log_analysis_failure(
            script_name="analyze_products",
            product_id=product_id,
            product_name=product_name,
            reason=str(e),
            company_key=company_key,
        )

        return ProductAnalysisResult(
            product_name=product_name,
            product_id=product_id,
            success=False,
            error=str(e),
            markdown_files_processed=len(markdown_files),
            has_quality_issues=has_quality_issues,
        )


def save_product_analysis(
    company_folder: Path,
    product_entry: dict,
    analysis: ProductAnalysis,
    client: GeminiClient,
    markdown_files: list[Path],
    has_quality_issues: bool = False,
) -> Path:
    """
    Save the product analysis to a JSON file.

    Args:
        company_folder: Path to the company folder
        product_entry: Product entry from index.json
        analysis: The ProductAnalysis to save
        client: GeminiClient instance for provenance
        markdown_files: List of markdown files used
        has_quality_issues: Whether the analysis has known quality issues

    Returns:
        Path to the saved file
    """
    product_name = product_entry.get("product_name", "unknown")
    product_id = product_entry.get("prduct_id", product_entry.get("product_id", "unknown"))
    product_branch = product_entry.get("product_branch", "unknown")
    source_url = product_entry.get("source_url", "")

    # Compute input hash
    input_hash = client.compute_input_hash([str(f) for f in markdown_files])

    # Compute individual markdown hashes for provenance
    markdown_hashes = {}
    for md_file in markdown_files:
        try:
            content = md_file.read_text(encoding="utf-8")
            md_hash = compute_markdown_hash(content)
            markdown_hashes[md_file.name] = md_hash
        except Exception:
            pass

    # Create the full InsuranceProduct
    insurance_product = InsuranceProduct(
        product_name=product_name,
        product_branch=product_branch,
        product_id=product_id,
        source_urls=[source_url] if source_url else [],
        metadata={
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "analyzer_version": "1.0.0",
            "quality_flags": {
                "has_known_quality_issues": has_quality_issues,
                "untrusted": has_quality_issues,
            },
            "analysis_provenance": {
                "model": client.model,
                "schema_version": SCHEMA_VERSION,
                "input_hash": input_hash,
                "markdown_hashes": markdown_hashes,
                "markdown_files": [f.name for f in markdown_files],
            },
        },
        analysis=analysis,
    )

    # Save to analysis folder
    analysis_folder = company_folder / "analysis"
    ensure_directory(analysis_folder)

    output_path = analysis_folder / f"{product_name}.json"
    save_json(insurance_product.model_dump(mode="json"), output_path, indent=2)

    logger.info(f"Saved analysis to: {output_path}")
    if has_quality_issues:
        logger.warning("Analysis flagged as untrusted due to known quality issues")

    return output_path


def analyze_company_products(
    company_key: str,
    product_filter: str | None = None,
    save_summary: bool = True,
    dry_run: bool = False,
    force_reanalysis: bool = False,
) -> list[ProductAnalysisResult]:
    """
    Analyze all products for an insurance company.

    Args:
        company_key: The company key (e.g., C0737)
        product_filter: Optional product name to analyze only that product
        save_summary: Whether to save an analysis summary JSON
        dry_run: If True, only list products without analyzing
        force_reanalysis: If True, skip idempotency checks and re-analyze all products

    Returns:
        List of ProductAnalysisResult for each product
    """
    # Find company folder
    company_folder = find_company_folder(company_key)
    if not company_folder:
        return []

    # Load product index
    products = load_product_index(company_folder)
    if not products:
        logger.warning(f"No products found in index.json for company {company_key}")
        return []

    # Filter products if requested
    if product_filter:
        products = [p for p in products if p.get("product_name") == product_filter]
        if not products:
            logger.error(f"Product '{product_filter}' not found in index.json")
            return []

    logger.info(f"Found {len(products)} products to analyze for {company_key}")

    if dry_run:
        logger.info("Dry run - listing products without analyzing:")
        for p in products:
            product_name = p.get("product_name", "unknown")
            markdown_files = get_product_markdown_files(company_folder, product_name)
            logger.info(f"  - {product_name}: {len(markdown_files)} markdown files")
        return []

    # Get company name for context
    try:
        companies = load_json(INSURANCE_COMPANIES_JSON)
        company = next((c for c in companies if c.get("company_key") == company_key), None)
        company_name = company.get("denomination", "Unknown") if company else "Unknown"
    except Exception:
        company_name = "Unknown"

    # Initialize Gemini client
    client = GeminiClient()

    # Analyze each product
    results: list[ProductAnalysisResult] = []

    for i, product_entry in enumerate(products, 1):
        product_name = product_entry.get("product_name", "unknown")
        logger.info(f"[{i}/{len(products)}] Processing: {product_name}")

        result = analyze_single_product(
            client=client,
            company_folder=company_folder,
            product_entry=product_entry,
            company_name=company_name,
            skip_if_exists=not force_reanalysis,
        )

        results.append(result)

        # Save analysis if successful and not skipped
        if result.success and result.analysis and not result.skipped:
            # Get markdown files again for provenance
            markdown_files = get_product_markdown_files(company_folder, product_entry.get("product_name", "unknown"))
            save_product_analysis(
                company_folder,
                product_entry,
                result.analysis,
                client,
                markdown_files,
                has_quality_issues=result.has_quality_issues,
            )

    # Save summary
    if save_summary:
        summary = generate_analysis_summary(company_key, results)
        metadata_folder = company_folder / "metadata"
        ensure_directory(metadata_folder)
        summary_path = metadata_folder / "analysis_summary.json"
        save_json(summary, summary_path)
        logger.info(f"Saved analysis summary to: {summary_path}")

    return results


def generate_analysis_summary(
    company_key: str,
    results: list[ProductAnalysisResult],
) -> dict:
    """
    Generate a summary of the product analysis results.

    Args:
        company_key: The company key
        results: List of analysis results

    Returns:
        Summary dictionary
    """
    total_products = len(results)
    successful = sum(1 for r in results if r.success and not r.skipped)
    skipped = sum(1 for r in results if r.skipped)
    failed = total_products - successful - skipped
    quality_issues = sum(1 for r in results if r.has_quality_issues)
    total_files = sum(r.markdown_files_processed for r in results)

    products_summary = [
        {
            "product_name": r.product_name,
            "product_id": r.product_id,
            "success": r.success,
            "skipped": r.skipped,
            "skip_reason": r.skip_reason,
            "has_quality_issues": r.has_quality_issues,
            "markdown_files_processed": r.markdown_files_processed,
            "error": r.error,
        }
        for r in results
    ]

    return {
        "schema_version": "1.0",
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "analyzer": {
            "name": "analyze_products",
            "version": "1.0.0",
            "model": GEMINI_MODEL,
            "schema_version": SCHEMA_VERSION,
        },
        "company_key": company_key,
        "summary": {
            "total_products": total_products,
            "successful": successful,
            "skipped": skipped,
            "failed": failed,
            "quality_issues": quality_issues,
            "total_markdown_files": total_files,
        },
        "products": products_summary,
    }


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description="Analyze insurance products using Gemini AI")
    parser.add_argument(
        "--company-key",
        "-k",
        required=True,
        help="Insurance company key (e.g., C0737)",
    )
    parser.add_argument(
        "--product",
        "-p",
        help="Analyze only a specific product by name (e.g., seguro_hogar)",
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="Don't save analysis summary JSON",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List products without analyzing (useful for checking setup)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-analysis even if already analyzed",
    )

    args = parser.parse_args()

    logger.info(f"Starting product analysis for company: {args.company_key}")

    results = analyze_company_products(
        company_key=args.company_key,
        product_filter=args.product,
        save_summary=not args.no_summary,
        dry_run=args.dry_run,
        force_reanalysis=args.force,
    )

    if args.dry_run:
        return

    # Print summary
    if results:
        successful = sum(1 for r in results if r.success and not r.skipped)
        skipped = sum(1 for r in results if r.skipped)
        failed = len(results) - successful - skipped
        quality_issues = sum(1 for r in results if r.has_quality_issues)

        logger.info("Analysis complete!")
        logger.info(f"Total products: {len(results)}")
        logger.info(f"Successful: {successful}")
        logger.info(f"Skipped (up-to-date): {skipped}")
        logger.info(f"Failed: {failed}")
        if quality_issues > 0:
            logger.warning(f"Products with quality issues (flagged as untrusted): {quality_issues}")

        if failed > 0:
            logger.warning("Failed products:")
            for r in results:
                if not r.success and not r.skipped:
                    logger.warning(f"  - {r.product_name}: {r.error}")


if __name__ == "__main__":
    main()
