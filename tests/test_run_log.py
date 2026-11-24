"""Tests for run logging."""

from datetime import datetime, timezone

from scripts.utils.run_log import append_run_log


def test_append_run_log(tmp_path, monkeypatch):
    """Test appending to run log."""
    # Mock the config to use temp directory
    import scripts.utils.run_log

    monkeypatch.setattr(scripts.utils.run_log, "BASE_STORAGE_PATH", tmp_path)

    started = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    finished = datetime(2026, 1, 1, 12, 5, 0, tzinfo=timezone.utc)

    append_run_log(
        script="test_script",
        started_at=started,
        finished_at=finished,
        counts={"processed": 10, "skipped": 2, "failed": 1},
        model="test-model",
        prompt_hash="abc123",
    )

    runs_path = tmp_path / "runs.jsonl"
    assert runs_path.exists()

    # Read back
    from scripts.utils.jsonl import load_jsonl

    runs = load_jsonl(runs_path)
    assert len(runs) == 1
    assert runs[0]["script"] == "test_script"
    assert runs[0]["counts"]["processed"] == 10


def test_append_run_log_multiple(tmp_path, monkeypatch):
    """Test appending multiple run logs."""
    import scripts.utils.run_log

    monkeypatch.setattr(scripts.utils.run_log, "BASE_STORAGE_PATH", tmp_path)

    now = datetime.now(timezone.utc)

    # Append two runs
    append_run_log(script="run1", started_at=now, finished_at=now)
    append_run_log(script="run2", started_at=now, finished_at=now)

    from scripts.utils.jsonl import load_jsonl

    runs = load_jsonl(tmp_path / "runs.jsonl")
    assert len(runs) == 2
    assert runs[0]["script"] == "run1"
    assert runs[1]["script"] == "run2"


def test_append_run_log_with_error(tmp_path, monkeypatch):
    """Test logging a failed run."""
    import scripts.utils.run_log

    monkeypatch.setattr(scripts.utils.run_log, "BASE_STORAGE_PATH", tmp_path)

    now = datetime.now(timezone.utc)
    append_run_log(
        script="failing_script",
        started_at=now,
        finished_at=now,
        error="Something went wrong",
    )

    from scripts.utils.jsonl import load_jsonl

    runs = load_jsonl(tmp_path / "runs.jsonl")
    assert runs[0]["error"] == "Something went wrong"
