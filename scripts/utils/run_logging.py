"""Run logging utilities for tracking processing runs and validation failures.

This module provides utilities for logging processing runs, validation failures,
and other events to data/runs.jsonl.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.config import PRODUCTS_STORAGE_PATH

# Path to the runs log file
RUNS_LOG_PATH = PRODUCTS_STORAGE_PATH.parent / "runs.jsonl"


def log_run_event(
    event_type: str,
    script_name: str,
    details: dict[str, Any],
    status: str = "info",
):
    """
    Log a processing run event to data/runs.jsonl.

    Args:
        event_type: Type of event (e.g., 'validation_failure', 'analysis_failure')
        script_name: Name of the script that generated the event
        details: Dictionary with event-specific details
        status: Status level ('info', 'warning', 'error')
    """
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "script": script_name,
        "status": status,
        "details": details,
    }

    # Ensure parent directory exists
    RUNS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Append to runs.jsonl (one JSON object per line)
    with open(RUNS_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def log_validation_failure(
    script_name: str,
    file_path: Path | str,
    reason: str,
    company_key: str | None = None,
    product_name: str | None = None,
    markdown_sha256: str | None = None,
):
    """
    Log a document validation failure.

    Args:
        script_name: Name of the script that detected the failure
        file_path: Path to the file that failed validation
        reason: Reason for validation failure
        company_key: Optional company key
        product_name: Optional product name
        markdown_sha256: Optional markdown content hash
    """
    details: dict[str, Any] = {
        "file_path": str(file_path),
        "reason": reason,
    }

    if company_key:
        details["company_key"] = company_key
    if product_name:
        details["product_name"] = product_name
    if markdown_sha256:
        details["markdown_sha256"] = markdown_sha256

    log_run_event(
        event_type="validation_failure",
        script_name=script_name,
        details=details,
        status="warning",
    )


def log_analysis_failure(
    script_name: str,
    product_id: str,
    product_name: str,
    reason: str,
    company_key: str | None = None,
    attempt: int | None = None,
):
    """
    Log an analysis failure.

    Args:
        script_name: Name of the script that detected the failure
        product_id: Product identifier
        product_name: Product name
        reason: Reason for failure
        company_key: Optional company key
        attempt: Optional attempt number for retries
    """
    details: dict[str, Any] = {
        "product_id": product_id,
        "product_name": product_name,
        "reason": reason,
    }

    if company_key:
        details["company_key"] = company_key
    if attempt is not None:
        details["attempt"] = attempt

    log_run_event(
        event_type="analysis_failure",
        script_name=script_name,
        details=details,
        status="error",
    )
