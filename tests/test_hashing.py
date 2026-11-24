"""Tests for hashing utilities."""

import hashlib
from pathlib import Path

from scripts.utils.hashing import compute_file_sha256, compute_string_sha256, get_cache_path


def test_compute_string_sha256():
    """Test string hashing."""
    text = "hello world"
    expected = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert compute_string_sha256(text) == expected


def test_compute_file_sha256(tmp_path):
    """Test file hashing."""
    test_file = tmp_path / "test.txt"
    content = b"test content"
    test_file.write_bytes(content)

    expected = hashlib.sha256(content).hexdigest()
    assert compute_file_sha256(test_file) == expected


def test_get_cache_path(tmp_path):
    """Test cache path generation."""
    sha256 = "abcd1234567890"
    cache_path = get_cache_path(sha256, "pdf", tmp_path)

    # Should use first 2 chars as subdirectory
    assert cache_path == tmp_path / "ab" / "abcd1234567890.pdf"


def test_get_cache_path_sharding():
    """Test that cache paths are properly sharded."""
    root = Path("/cache")

    # Different first 2 chars should go to different directories
    path1 = get_cache_path("aabbcc", "pdf", root)
    path2 = get_cache_path("112233", "pdf", root)

    assert path1.parent.name == "aa"
    assert path2.parent.name == "11"
    assert path1.parent != path2.parent
