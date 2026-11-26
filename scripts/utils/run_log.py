"""Utilities for logging pipeline runs to runs.jsonl."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from scripts.config import BASE_STORAGE_PATH
from scripts.utils.jsonl import load_jsonl, save_jsonl


def get_runs_log_path() -> Path:
    """Get the path to runs.jsonl."""
    return BASE_STORAGE_PATH / "runs.jsonl"


def append_run_log(
    script: str,
    started_at: datetime,
    finished_at: datetime | None = None,
    counts: dict | None = None,
    model: str | None = None,
    prompt_hash: str | None = None,
    error: str | None = None,
    details: dict | None = None,
) -> None:
    """
    Append a run log entry to runs.jsonl.

    Args:
        script: Name of the script (e.g., 'process_pdfs', 'analyze_products')
        started_at: When the run started
        finished_at: When the run finished (defaults to now if None)
        counts: Dictionary with processed/skipped/failed counts
        model: Model name (for AI-based scripts)
        prompt_hash: Hash of the prompt template (for AI-based scripts)
        error: Error message if the run failed
        details: Optional free-form metadata (gaps, company_key, etc.)
    """
    if finished_at is None:
        finished_at = datetime.now(timezone.utc)

    # Get git commit if available
    git_commit = None
    try:
        import subprocess

        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            git_commit = result.stdout.strip()
    except Exception:
        pass

    entry = {
        "script": script,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "git_commit": git_commit,
        "counts": counts or {},
        "model": model,
        "prompt_hash": prompt_hash,
        "error": error,
        "details": details or {},
    }

    # Load existing runs
    runs_path = get_runs_log_path()
    existing_runs = []
    if runs_path.exists():
        try:
            existing_runs = load_jsonl(runs_path)
        except Exception:
            pass

    # Append new entry
    existing_runs.append(entry)

    # Save back
    save_jsonl(existing_runs, runs_path)
