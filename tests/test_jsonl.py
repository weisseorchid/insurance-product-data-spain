"""Tests for JSONL utilities."""

from pathlib import Path

import pytest

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
    with open(jsonl_path, "r") as f:
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

    with open(jsonl_path, "r") as f:
        lines = f.readlines()

    assert len(lines) == 3
    # Each line should be valid JSON
    import json

    for line in lines:
        json.loads(line)


def test_jsonl_unicode_handling(tmp_path: Path):
    """Test that JSONL handles unicode correctly (not escaped)."""
    data = [
        {"name": "José", "city": "Madrid"},
        {"name": "François", "city": "París"},
    ]

    jsonl_path = tmp_path / "test.jsonl"
    save_jsonl(data, jsonl_path, ensure_ascii=False)

    loaded = load_jsonl(jsonl_path)
    assert loaded[0]["name"] == "José"
    assert loaded[1]["city"] == "París"

    # Verify raw file contains actual unicode characters
    with open(jsonl_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "José" in content
    assert "París" in content


def test_jsonl_empty_list(tmp_path: Path):
    """Test saving and loading an empty list."""
    jsonl_path = tmp_path / "empty.jsonl"
    save_jsonl([], jsonl_path)

    loaded = load_jsonl(jsonl_path)
    assert loaded == []


def test_jsonl_load_nonexistent_file(tmp_path: Path):
    """Test that loading a nonexistent file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_jsonl(tmp_path / "nonexistent.jsonl")


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


def test_jsonl_no_pretty_formatting(tmp_path: Path):
    """Test that JSONL uses compact formatting (no extra whitespace)."""
    data = [{"id": "1", "nested": {"key": "value"}}]

    jsonl_path = tmp_path / "compact.jsonl"
    save_jsonl(data, jsonl_path)

    with open(jsonl_path, "r") as f:
        line = f.read().strip()

    # Compact format: no spaces after separators except after colons
    assert ',"nested":{' in line or ',"nested": {' in line
    # Should be a single line with no newlines in the JSON
    assert line.count("\n") == 0
