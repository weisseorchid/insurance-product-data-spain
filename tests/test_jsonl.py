"""Tests for JSONL utilities."""

from pathlib import Path

from scripts.utils.jsonl import load_jsonl, save_jsonl


def test_save_and_load_jsonl(tmp_path: Path):
    """Test basic JSONL save and load round-trip."""
    data = [
        {"id": "1", "name": "Alice", "age": 30},
        {"id": "2", "name": "Bob", "age": 25},
        {"id": "3", "name": "Charlie", "age": 35},
    ]

    jsonl_path = tmp_path / "test.jsonl"
    save_jsonl(data, jsonl_path)

    loaded = load_jsonl(jsonl_path)
    assert loaded == data


def test_jsonl_stable_key_ordering(tmp_path: Path):
    """Test that JSONL saves keys in sorted order for diff-friendliness."""
    data = [
        {"z_field": "last", "a_field": "first", "m_field": "middle"},
    ]

    jsonl_path = tmp_path / "test.jsonl"
    save_jsonl(data, jsonl_path)

    # Read the raw file to check key ordering
    with open(jsonl_path) as f:
        line = f.read().strip()

    # Keys should appear in alphabetical order
    assert line.index("a_field") < line.index("m_field") < line.index("z_field")


def test_jsonl_stable_record_sorting(tmp_path: Path):
    """Test that JSONL sorts records by provided key for consistent diffs."""
    data = [
        {"id": "3", "name": "Charlie"},
        {"id": "1", "name": "Alice"},
        {"id": "2", "name": "Bob"},
    ]

    jsonl_path = tmp_path / "test.jsonl"
    save_jsonl(data, jsonl_path, sort_key=lambda x: x["id"])

    loaded = load_jsonl(jsonl_path)

    # Records should be sorted by id
    assert loaded[0]["id"] == "1"
    assert loaded[1]["id"] == "2"
    assert loaded[2]["id"] == "3"


def test_jsonl_one_record_per_line(tmp_path: Path):
    """Test that each record is on its own line."""
    data = [
        {"id": "1", "name": "Alice"},
        {"id": "2", "name": "Bob"},
        {"id": "3", "name": "Charlie"},
    ]

    jsonl_path = tmp_path / "test.jsonl"
    save_jsonl(data, jsonl_path)

    with open(jsonl_path) as f:
        lines = f.readlines()

    assert len(lines) == 3


def test_jsonl_deterministic_output(tmp_path: Path):
    """Test that saving the same data twice produces identical output."""
    data = [
        {"id": "2", "name": "Bob", "age": 25},
        {"id": "1", "name": "Alice", "age": 30},
    ]

    path1 = tmp_path / "output1.jsonl"
    path2 = tmp_path / "output2.jsonl"

    save_jsonl(data, path1, sort_key=lambda x: x["id"])
    save_jsonl(data, path2, sort_key=lambda x: x["id"])

    # Files should be identical
    assert path1.read_bytes() == path2.read_bytes()
