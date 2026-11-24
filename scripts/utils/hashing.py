"""Utilities for content hashing and cache management."""

from __future__ import annotations

import hashlib
from pathlib import Path


def compute_file_sha256(file_path: Path) -> str:
    """
    Compute SHA256 hash of a file.

    Args:
        file_path: Path to the file

    Returns:
        Hex-encoded SHA256 hash
    """
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def compute_string_sha256(text: str) -> str:
    """
    Compute SHA256 hash of a string.

    Args:
        text: String to hash

    Returns:
        Hex-encoded SHA256 hash
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get_cache_path(sha256_hash: str, extension: str, cache_root: Path) -> Path:
    """
    Get the content-addressed cache path for a file.

    Uses a 2-level directory structure: <cache_root>/<first_2_chars>/<hash>.<ext>

    Args:
        sha256_hash: SHA256 hash of the content
        extension: File extension (e.g., 'pdf', 'md')
        cache_root: Root directory for the cache

    Returns:
        Path to the cached file
    """
    # Use first 2 characters for directory sharding
    subdir = sha256_hash[:2]
    return cache_root / subdir / f"{sha256_hash}.{extension}"
