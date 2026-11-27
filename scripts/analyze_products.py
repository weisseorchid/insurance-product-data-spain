"""Script to analyze insurance products using Gemini AI.

This script takes an insurance company key (e.g., C0737) and:
1. Finds the company's folder in data/products_by_insurance_company/
2. Reads the index.json to get all products
3. For each product, resolves its markdown from documents.jsonl + the document cache
   (.cache/insurance-docs), or from a legacy sources/{product_name}/ folder if present
4. Analyzes all markdown files using Gemini to extract structured information
   (Mistral as fallback when Gemini keeps failing; see scripts/clients/llm.py)
5. Saves the analysis results to analysis/{product_name}.json and sets
   analysis_path on that product in index.json
6. Writes metadata/analysis_summary.json, merging into an existing summary on
   a --product (or other partial) run so earlier products are not dropped

Run with: uv run python -m scripts.analyze_products --company-key C0737 [--provider auto|gemini|mistral]
"""

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from insurance_product_data_sp.core.logging import logger
from insurance_product_data_sp.schemas import InsuranceProduct, ProductAnalysis
from scripts.clients.gemini import GEMINI_MODEL, SCHEMA_VERSION, GeminiClient
from scripts.clients.llm import PROVIDER_CHOICES, AnalysisClient, ProviderConfigError, RoutedAnalysis, build_router
from scripts.utils.companies import company_display_name, company_folder_path, find_company
from scripts.utils.document_store import MarkdownInput, markdown_inputs_from_documents
from scripts.utils.document_validation import (
    compute_markdown_hash,
    load_known_block_page_hashes,
    markdown_is_unusable,
)
from scripts.utils.gaps import ANALYSIS_GAPS_FILENAME, write_gaps_report
from scripts.utils.run_log import append_run_log
from scripts.utils.storage import ensure_directory, load_json, save_json

# Known bad markdown hashes (e.g. Mutua Madrileña Cloudflare blocks), shared with CI
KNOWN_BAD_MARKDOWN_HASHES = load_known_block_page_hashes()

# Companies with known quality issues
KNOWN_BAD_COMPANIES = {
    "mutua_madrileña_automovilista_sociedad_de_seguros_a_prima_fija",
}


# Deprecated InsuranceProduct fields that must not be written to new analyses
DEPRECATED_ANALYSIS_FIELDS = ("product_branch", "source_urls")


def get_product_branches(product_entry: dict) -> list[str]:
    """Return the product's branch codes (schema v1 ``branches``, legacy ``product_branch`` as fallback)."""
    branches = product_entry.get("branches")
    if branches is None:
        branches = product_entry.get("product_branch")
    if branches is None:
        return []
    if isinstance(branches, str):
        return [branches]
    return [str(b) for b in branches]


def analysis_payload(insurance_product: InsuranceProduct) -> dict:
    """Serialize an analysis without deprecated fields (``branches`` replaces ``product_branch``)."""
    payload = insurance_product.model_dump(mode="json")
    for field in DEPRECATED_ANALYSIS_FIELDS:
        payload.pop(field, None)
    return payload


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
    dropped_inputs: list[MarkdownInput] | None = None
    usable_inputs: list[MarkdownInput] | None = None
    provider: str | None = None
    model: str | None = None
    fallback_from: str | None = None
    fallback_reason: str | None = None


def _analyze_with_provenance(client, markdown_paths, product_context, document_names) -> RoutedAnalysis:
    """Call the router (or a bare provider client) and report which provider/model answered."""
    if hasattr(client, "analyze_with_provenance"):
        return client.analyze_with_provenance(markdown_paths, product_context, document_names)
    analysis = client.analyze_product_documents(
        markdown_paths=markdown_paths,
        product_context=product_context,
        document_names=document_names,
    )
    return RoutedAnalysis(analysis=analysis, provider=getattr(client, "provider", "gemini"), model=client.model)


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


def partition_usable_markdown(
    markdown_inputs: list[MarkdownInput],
    known_hashes: set[str] | None = None,
) -> tuple[list[MarkdownInput], list[MarkdownInput]]:
    """Split markdown inputs into (usable, dropped block/error pages)."""
    known = known_hashes if known_hashes is not None else KNOWN_BAD_MARKDOWN_HASHES
    usable: list[MarkdownInput] = []
    dropped: list[MarkdownInput] = []
    for item in markdown_inputs:
        try:
            content = item.path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            dropped.append(item)
            continue
        md_hash = compute_markdown_hash(content)
        if markdown_is_unusable(content, md_hash, known):
            dropped.append(item)
        else:
            usable.append(item)
    return usable, dropped


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


def get_product_markdown_inputs(company_folder: Path, product_name: str) -> list[MarkdownInput]:
    """
    Resolve the markdown documents for a product.

    Source of truth is the company's documents.jsonl plus the gitignored document
    cache (see scripts/utils/document_store.py). For backward compatibility, a
    legacy ``sources/{product_name}/*.md`` folder is used if it exists.

    Args:
        company_folder: Path to the company folder
        product_name: Product name (as in index.json / documents.jsonl)

    Returns:
        List of MarkdownInput (path to read, display name), possibly empty
    """
    legacy_folder = company_folder / "sources" / product_name
    if legacy_folder.exists():
        return [MarkdownInput(p, p.name) for p in sorted(legacy_folder.glob("*.md"))]

    found, missing = markdown_inputs_from_documents(company_folder, product_name)
    if missing:
        logger.warning(
            f"{len(missing)} document(s) of {product_name} have no cached markdown "
            f"(run scripts.fetch_product_documents or scripts.process_pdfs): "
            + ", ".join(str(r.get("filename")) for r in missing)
        )
    return found


def get_product_markdown_files(company_folder: Path, product_name: str) -> list[Path]:
    """Paths of the product's markdown documents (see get_product_markdown_inputs)."""
    return [i.path for i in get_product_markdown_inputs(company_folder, product_name)]


def should_skip_analysis(
    company_folder: Path,
    product_entry: dict,
    markdown_files: list[Path],
    client: AnalysisClient,
) -> tuple[bool, str | None]:
    """
    Check if analysis should be skipped (idempotency check).

    Args:
        company_folder: Path to the company folder
        product_entry: Product entry from index.json
        markdown_files: List of markdown files for this product
        client: Provider client or AnalysisRouter

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

        # Check if model and schema version match (any model in the provider chain counts)
        accepted_models = getattr(client, "accepted_models", None) or {client.model}
        if provenance.get("model") not in accepted_models:
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
    client: AnalysisClient,
    company_folder: Path,
    product_entry: dict,
    company_name: str,
    skip_if_exists: bool = True,
) -> ProductAnalysisResult:
    """
    Analyze a single product using Gemini.

    Args:
        client: Provider client or AnalysisRouter
        company_folder: Path to the company folder
        product_entry: Product entry from index.json
        company_name: Name of the insurance company
        skip_if_exists: Whether to skip if analysis already exists and is up-to-date

    Returns:
        ProductAnalysisResult with the analysis or error
    """
    product_name = product_entry.get("product_name", "unknown")
    product_id = product_entry.get("product_id", "unknown")
    branches = get_product_branches(product_entry)

    logger.info(f"Analyzing product: {product_name} ({product_id})")

    # Get markdown documents for this product (documents.jsonl + cache, or legacy sources/)
    markdown_inputs = get_product_markdown_inputs(company_folder, product_name)
    usable_inputs, dropped_inputs = partition_usable_markdown(markdown_inputs)
    markdown_files = [i.path for i in usable_inputs]

    if dropped_inputs:
        logger.warning(
            f"Dropping {len(dropped_inputs)} block/error page document(s) for {product_name}: "
            + ", ".join(i.name for i in dropped_inputs)
        )

    if not markdown_files:
        logger.warning(f"No usable markdown files found for product: {product_name}")
        return ProductAnalysisResult(
            product_name=product_name,
            product_id=product_id,
            success=False,
            error="no_usable_documents",
            dropped_inputs=dropped_inputs,
            usable_inputs=[],
        )

    logger.info(f"Found {len(markdown_files)} usable markdown files for {product_name}")

    # Check for known quality issues (company-level; block pages already dropped)
    has_quality_issues = company_folder.name in KNOWN_BAD_COMPANIES
    incomplete_inputs = bool(dropped_inputs)

    if has_quality_issues:
        logger.warning(f"Product {product_name} has known quality issues (company={company_folder.name})")
    if incomplete_inputs:
        logger.warning(f"Product {product_name} has incomplete inputs ({len(dropped_inputs)} document(s) dropped)")

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
                dropped_inputs=dropped_inputs,
                usable_inputs=usable_inputs,
            )

    # Build product context for Gemini
    product_context = {
        "product_name": product_name,
        "branches": branches,
        "company": company_name,
    }

    try:
        # Analyze with Gemini, Mistral as fallback (block pages already excluded)
        routed = _analyze_with_provenance(
            client,
            [str(f) for f in markdown_files],
            product_context,
            {str(i.path): i.name for i in usable_inputs},
        )

        return ProductAnalysisResult(
            product_name=product_name,
            product_id=product_id,
            success=True,
            analysis=routed.analysis,
            markdown_files_processed=len(markdown_files),
            has_quality_issues=has_quality_issues,
            dropped_inputs=dropped_inputs,
            usable_inputs=usable_inputs,
            provider=routed.provider,
            model=routed.model,
            fallback_from=routed.fallback_from,
            fallback_reason=routed.fallback_reason,
        )

    except Exception as e:
        # Failures are recorded in the run's runs.jsonl entry (details.failures)
        logger.error(f"Failed to analyze product {product_name}: {e}")
        return ProductAnalysisResult(
            product_name=product_name,
            product_id=product_id,
            success=False,
            error=str(e),
            markdown_files_processed=len(markdown_files),
            has_quality_issues=has_quality_issues,
            dropped_inputs=dropped_inputs,
            usable_inputs=usable_inputs,
        )


def save_product_analysis(
    company_folder: Path,
    product_entry: dict,
    analysis: ProductAnalysis,
    client: AnalysisClient,
    markdown_files: list[Path],
    has_quality_issues: bool = False,
    markdown_names: list[str] | None = None,
    incomplete_inputs: bool = False,
    provider: str | None = None,
    model: str | None = None,
    fallback_reason: str | None = None,
) -> Path:
    """
    Save the product analysis to a JSON file.

    Args:
        company_folder: Path to the company folder
        product_entry: Product entry from index.json
        analysis: The ProductAnalysis to save
        client: Provider client or AnalysisRouter (provenance defaults)
        markdown_files: List of markdown files used
        markdown_names: Optional display names for markdown_files (default: file names)
        has_quality_issues: Whether the analysis has known quality issues
        incomplete_inputs: Whether some source documents were dropped (e.g. block pages)
        provider: Provider that produced the analysis (default: the client's primary provider)
        model: Model that produced the analysis (default: client.model)
        fallback_reason: Why the primary provider was skipped, when a fallback answered

    Returns:
        Path to the saved file
    """
    product_name = product_entry.get("product_name", "unknown")
    product_id = product_entry.get("product_id", "unknown")
    branches = get_product_branches(product_entry)
    source_url = product_entry.get("source_url") or None
    company_key = product_entry.get("company_key") or ""

    # Compute input hash
    input_hash = client.compute_input_hash([str(f) for f in markdown_files])

    # Compute individual markdown hashes for provenance
    names = markdown_names if markdown_names is not None else [f.name for f in markdown_files]
    markdown_hashes = {}
    for md_file, md_name in zip(markdown_files, names, strict=True):
        try:
            content = md_file.read_text(encoding="utf-8")
            md_hash = compute_markdown_hash(content)
            markdown_hashes[md_name] = md_hash
        except Exception:
            pass

    # Create the full InsuranceProduct
    insurance_product = InsuranceProduct(
        product_id=product_id,
        company_key=company_key,
        product_name=product_name,
        branches=branches,
        source_url=source_url,
        metadata={
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "analyzer_version": "1.0.0",
            "quality_flags": {
                "has_known_quality_issues": has_quality_issues,
                "untrusted": has_quality_issues,
                "incomplete_inputs": incomplete_inputs,
            },
            "analysis_provenance": {
                "provider": provider or getattr(client, "provider", "gemini"),
                "model": model or client.model,
                "schema_version": SCHEMA_VERSION,
                "input_hash": input_hash,
                "markdown_hashes": markdown_hashes,
                "markdown_files": names,
                **({"fallback_reason": fallback_reason} if fallback_reason else {}),
            },
        },
        analysis=analysis,
    )

    # Save to analysis folder
    analysis_folder = company_folder / "analysis"
    ensure_directory(analysis_folder)

    output_path = analysis_folder / f"{product_name}.json"
    save_json(analysis_payload(insurance_product), output_path, indent=2)

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
    provider: str = "auto",
) -> list[ProductAnalysisResult]:
    """
    Analyze all products for an insurance company.

    Args:
        company_key: The company key (e.g., C0737)
        product_filter: Optional product name to analyze only that product
        save_summary: Whether to save an analysis summary JSON
        dry_run: If True, only list products without analyzing
        force_reanalysis: If True, skip idempotency checks and re-analyze all products
        provider: "auto" (Gemini, Mistral fallback), "gemini" or "mistral"

    Returns:
        List of ProductAnalysisResult for each product

    Raises:
        ProviderConfigError: If the requested provider cannot be configured (e.g. missing key)
    """
    started_at = datetime.now(timezone.utc)
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
        company = find_company(company_key)
        company_name = (company_display_name(company) if company else "") or "Unknown"
    except Exception:
        company_name = "Unknown"

    # Provider chain: Gemini primary, Mistral fallback (if MISTRAL_API_KEY is set)
    client = build_router(provider, gemini_factory=GeminiClient)

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

        # Save analysis if successful and not skipped (only usable, non-block-page inputs)
        if result.success and result.analysis and not result.skipped:
            usable = result.usable_inputs or []
            save_product_analysis(
                company_folder,
                product_entry,
                result.analysis,
                client,
                [i.path for i in usable],
                has_quality_issues=result.has_quality_issues,
                markdown_names=[i.name for i in usable],
                incomplete_inputs=bool(result.dropped_inputs),
                provider=result.provider,
                model=result.model,
                fallback_reason=result.fallback_reason,
            )

        # Successful analyses (including already-up-to-date skips) get analysis_path
        # in index.json. A failure never sets or clears it.
        if result.success:
            set_index_analysis_path(company_folder, result.product_id, result.product_name)

    gap_rows: list[dict] = []
    for result in results:
        for dropped in result.dropped_inputs or []:
            gap_rows.append(
                {
                    "product_id": result.product_id,
                    "product_name": result.product_name,
                    "doc_id": None,
                    "filename": dropped.name,
                    "source": None,
                    "reason": "block_page",
                    "detail": "dropped before analysis",
                }
            )
        if not result.success and result.error == "no_usable_documents":
            gap_rows.append(
                {
                    "product_id": result.product_id,
                    "product_name": result.product_name,
                    "doc_id": None,
                    "filename": None,
                    "source": None,
                    "reason": "no_usable_documents",
                    "detail": "all documents missing or are block/error pages",
                }
            )
    write_gaps_report(
        company_folder,
        company_key,
        "analyze_products",
        gap_rows,
        filename=ANALYSIS_GAPS_FILENAME,
        replace_product_ids={r.product_id for r in results} if product_filter else None,
    )

    _append_analysis_run_log(company_key, provider, client, results, started_at)

    # Save summary (merge into an existing file on partial/--product runs)
    if save_summary:
        metadata_folder = company_folder / "metadata"
        ensure_directory(metadata_folder)
        summary_path = metadata_folder / "analysis_summary.json"
        existing = _load_existing_summary(summary_path)
        summary = generate_analysis_summary(
            company_key,
            results,
            primary_model=client.model,
            existing=existing,
            keep_products_not_in_run=product_filter is not None,
        )
        save_json(summary, summary_path)
        logger.info(f"Saved analysis summary to: {summary_path}")

    return results


def provider_counts(results: list[ProductAnalysisResult]) -> dict[str, int]:
    """Analyses produced in this run per provider, plus how many came from a fallback."""
    counts: dict[str, int] = {}
    for r in results:
        if r.success and not r.skipped and r.provider:
            counts[f"by_provider_{r.provider}"] = counts.get(f"by_provider_{r.provider}", 0) + 1
    counts["fallbacks"] = sum(1 for r in results if r.fallback_from and r.success and not r.skipped)
    return counts


def _append_analysis_run_log(
    company_key: str,
    provider_mode: str,
    client,
    results: list[ProductAnalysisResult],
    started_at: datetime,
) -> None:
    """Append one runs.jsonl entry (started_at/script format checked by CI) for this analysis run."""
    successful = sum(1 for r in results if r.success and not r.skipped)
    skipped = sum(1 for r in results if r.skipped)
    failures = [
        {"product_id": r.product_id, "product_name": r.product_name, "error": (r.error or "")[:500]}
        for r in results
        if not r.success and not r.skipped
    ]
    fallbacks = [
        {"product_id": r.product_id, "from": r.fallback_from, "to": r.provider, "reason": r.fallback_reason}
        for r in results
        if r.fallback_from and r.success and not r.skipped
    ]
    try:
        append_run_log(
            script="analyze_products",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            counts={
                "analyzed": successful,
                "skipped": skipped,
                "failed": len(failures),
                **provider_counts(results),
            },
            model=client.model,
            details={
                "company_key": company_key,
                "provider_mode": provider_mode,
                "providers": [
                    {"provider": getattr(c, "provider", "gemini"), "model": c.model}
                    for c in getattr(client, "clients", [client])
                ],
                "failures": failures,
                "fallbacks": fallbacks,
            },
        )
    except Exception as e:  # the run log must never break an analysis run
        logger.warning(f"Could not append analyze_products run log: {e}")


def _product_key(product_name: str, product_id: str | None) -> str:
    """Stable identity for a product in the summary or index (prefer product_id)."""
    if product_id and product_id != "unknown":
        return f"id:{product_id}"
    return f"name:{product_name}"


def _product_summary_entry(result: ProductAnalysisResult) -> dict:
    """One product row in analysis_summary.json."""
    entry = {
        "product_name": result.product_name,
        "product_id": result.product_id,
        "success": result.success,
        "skipped": result.skipped,
        "skip_reason": result.skip_reason,
        "has_quality_issues": result.has_quality_issues,
        "markdown_files_processed": result.markdown_files_processed,
        "error": result.error,
        "provider": result.provider,
        "model": result.model,
    }
    if result.fallback_from:
        entry["fallback_from"] = result.fallback_from
    return entry


def _entry_key(entry: dict) -> str:
    return _product_key(str(entry.get("product_name") or "unknown"), entry.get("product_id"))


def _result_key(result: ProductAnalysisResult) -> str:
    return _product_key(result.product_name, result.product_id)


def _choose_summary_entry(existing_entry: dict | None, result: ProductAnalysisResult) -> dict:
    """Upsert a run result into a summary row without dropping a prior success on failure."""
    if result.success and not result.skipped:
        return _product_summary_entry(result)
    if existing_entry is not None:
        # Skip (already up-to-date) and failure keep the previous row, including a
        # successful analysis that this run did not replace.
        return existing_entry
    return _product_summary_entry(result)


def merge_summary_products(
    results: list[ProductAnalysisResult],
    existing_products: list[dict] | None,
    *,
    keep_products_not_in_run: bool,
) -> list[dict]:
    """Merge this run's results into existing summary product rows.

    Successful new analyses are upserted. A skipped or failed product keeps its
    previous row when one exists (a failure does not drop a prior success).
    Products not in this run are kept when ``keep_products_not_in_run`` is true
    (a ``--product`` / partial run); a full company run drops rows no longer in
    the index.
    """
    results_by_key = {_result_key(result): result for result in results}
    seen: set[str] = set()
    merged: list[dict] = []

    for entry in existing_products or []:
        if not isinstance(entry, dict):
            continue
        key = _entry_key(entry)
        result = results_by_key.get(key)
        if result is None:
            if keep_products_not_in_run:
                merged.append(entry)
            seen.add(key)
            continue
        merged.append(_choose_summary_entry(entry, result))
        seen.add(key)

    for result in results:
        key = _result_key(result)
        if key not in seen:
            merged.append(_choose_summary_entry(None, result))
            seen.add(key)

    return merged


def summary_counts(products: list[dict]) -> dict:
    """Totals and per-provider counts from the merged product set."""
    total_products = len(products)
    successful = sum(1 for p in products if p.get("success") and not p.get("skipped"))
    skipped = sum(1 for p in products if p.get("skipped"))
    failed = total_products - successful - skipped
    quality_issues = sum(1 for p in products if p.get("has_quality_issues"))
    total_files = sum(int(p.get("markdown_files_processed") or 0) for p in products)
    counts: dict[str, int] = {}
    for product in products:
        if product.get("success") and not product.get("skipped") and product.get("provider"):
            key = f"by_provider_{product['provider']}"
            counts[key] = counts.get(key, 0) + 1
    counts["fallbacks"] = sum(
        1 for p in products if p.get("success") and not p.get("skipped") and p.get("fallback_from")
    )
    return {
        "total_products": total_products,
        "successful": successful,
        "skipped": skipped,
        "failed": failed,
        "quality_issues": quality_issues,
        "total_markdown_files": total_files,
        **counts,
    }


def _load_existing_summary(summary_path: Path) -> dict | None:
    """Load an on-disk analysis summary, or None if missing or unreadable."""
    if not summary_path.exists():
        return None
    try:
        existing = load_json(summary_path)
    except Exception as exc:
        logger.warning(f"Could not load existing analysis summary {summary_path}: {exc}")
        return None
    return existing if isinstance(existing, dict) else None


def analysis_relative_path(product_name: str) -> str:
    """Index ``analysis_path`` value for a saved analysis file."""
    return f"analysis/{product_name}.json"


def set_index_analysis_path(company_folder: Path, product_id: str, product_name: str) -> bool:
    """Set ``analysis_path`` on the matching product in index.json if the analysis file exists.

    Idempotent: no write when the path is already set to the same relative value.
    Does nothing when the analysis file or the index is missing. Never clears a
    path (callers must not invoke this for a failed analysis).

    Returns:
        True when index.json was written.
    """
    relative_path = analysis_relative_path(product_name)
    if not (company_folder / relative_path).exists():
        return False

    index_path = company_folder / "index.json"
    if not index_path.exists():
        logger.warning(f"Index file not found, cannot set analysis_path: {index_path}")
        return False

    try:
        index_data = load_json(index_path)
    except Exception as exc:
        logger.warning(f"Failed to load index.json to set analysis_path: {exc}")
        return False

    if not isinstance(index_data, list):
        logger.warning(f"Unexpected index.json format, cannot set analysis_path: {index_path}")
        return False

    target = _product_key(product_name, product_id)
    changed = False
    for company_entry in index_data:
        if not isinstance(company_entry, dict):
            continue
        for product in company_entry.get("products") or []:
            if not isinstance(product, dict):
                continue
            if _entry_key(product) != target:
                continue
            if product.get("analysis_path") != relative_path:
                product["analysis_path"] = relative_path
                changed = True

    if changed:
        save_json(index_data, index_path)
        logger.info(f"Set analysis_path={relative_path} for {product_name} in {index_path}")
    return changed


def _existing_analyzer_model(existing: dict | None) -> str | None:
    """Return analyzer.model from a previous summary, if it is a string."""
    if not existing:
        return None
    analyzer = existing.get("analyzer")
    if not isinstance(analyzer, dict):
        return None
    model = analyzer.get("model")
    return model if isinstance(model, str) and model else None


def generate_analysis_summary(
    company_key: str,
    results: list[ProductAnalysisResult],
    primary_model: str | None = None,
    existing: dict | None = None,
    keep_products_not_in_run: bool = False,
) -> dict:
    """
    Generate a summary of the product analysis results.

    When ``existing`` is a previous analysis_summary.json, this run's products
    are upserted into it and totals / per-provider counts are recomputed from
    the merged set. A ``--product`` run should pass ``keep_products_not_in_run``
    so other products are not dropped.

    Args:
        company_key: The company key
        results: List of analysis results for this run
        primary_model: Model name recorded under analyzer.model
        existing: Previously written summary, if any
        keep_products_not_in_run: Keep existing rows for products not in results

    Returns:
        Summary dictionary
    """
    existing_products = None
    if existing and isinstance(existing.get("products"), list):
        existing_products = existing["products"]

    products_summary = merge_summary_products(
        results,
        existing_products,
        keep_products_not_in_run=keep_products_not_in_run,
    )

    summary = {
        "schema_version": "1.0",
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "analyzer": {
            "name": "analyze_products",
            "version": "1.0.0",
            "model": primary_model or _existing_analyzer_model(existing) or GEMINI_MODEL,
            "schema_version": SCHEMA_VERSION,
        },
        "company_key": company_key,
        "summary": summary_counts(products_summary),
        "products": products_summary,
    }
    if existing:
        for key, value in existing.items():
            if key not in summary:
                summary[key] = value
    return summary


def main() -> int:
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
    parser.add_argument(
        "--provider",
        choices=PROVIDER_CHOICES,
        default="auto",
        help="LLM provider: auto = Gemini, then Mistral if Gemini keeps failing (needs MISTRAL_API_KEY)",
    )

    args = parser.parse_args()

    logger.info(f"Starting product analysis for company: {args.company_key}")

    try:
        results = analyze_company_products(
            company_key=args.company_key,
            product_filter=args.product,
            save_summary=not args.no_summary,
            dry_run=args.dry_run,
            force_reanalysis=args.force,
            provider=getattr(args, "provider", "auto"),
        )
    except ProviderConfigError as e:
        logger.error(str(e))
        return 2

    if args.dry_run:
        return 0

    # Print summary
    exit_code = 0
    if results:
        successful = sum(1 for r in results if r.success and not r.skipped)
        skipped = sum(1 for r in results if r.skipped)
        failed = len(results) - successful - skipped
        quality_issues = sum(1 for r in results if r.has_quality_issues)
        dropped = sum(len(r.dropped_inputs or []) for r in results)

        logger.info("Analysis complete!")
        logger.info(f"Total products: {len(results)}")
        logger.info(f"Successful: {successful}")
        logger.info(f"Skipped (up-to-date): {skipped}")
        logger.info(f"Failed: {failed}")
        if dropped > 0:
            logger.warning(f"Dropped block/error page documents: {dropped}")
        if quality_issues > 0:
            logger.warning(f"Products with quality issues (flagged as untrusted): {quality_issues}")

        if failed > 0:
            exit_code = 1
            logger.warning("Failed products:")
            for r in results:
                if not r.success and not r.skipped:
                    logger.warning(f"  - {r.product_name}: {r.error}")
        # Dropped files on otherwise successful (mixed) products are warnings only;
        # exit 1 is reserved for no_usable_documents / analysis failures (failed > 0).

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
