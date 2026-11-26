"""Pytest configuration for tests."""

import sys
from pathlib import Path

import pytest

# Add the project root to sys.path so that the package can be imported
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture(autouse=True)
def _isolate_runs_log(tmp_path, monkeypatch):
    """Never let a test append to the real data/runs.jsonl."""
    import scripts.utils.run_log
    import scripts.utils.run_logging

    isolated = tmp_path / "isolated-data"
    monkeypatch.setattr(scripts.utils.run_log, "BASE_STORAGE_PATH", isolated)
    monkeypatch.setattr(scripts.utils.run_logging, "RUNS_LOG_PATH", isolated / "runs.jsonl")
