"""Storage utilities for JSON file operations."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from insurance_product_data_sp.core.logging import logger


def ensure_directory(path: Path) -> None:
    """Ensure a directory exists, creating it if necessary."""
    path.mkdir(parents=True, exist_ok=True)


def save_json(data: Any, file_path: Path | str, indent: int = 2) -> None:
    """
    Save data to a JSON file.

    Writes to a temporary file in the same directory and then replaces the
    target (the same pattern as PDF cache writes in fetch_product_documents),
    so a crash cannot leave a half-written JSON file.

    Args:
        data: Data to save (must be JSON serializable)
        file_path: Path to the JSON file
        indent: JSON indentation level
    """
    path = Path(file_path)
    ensure_directory(path.parent)

    payload = json.dumps(data, indent=indent, ensure_ascii=False)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".part")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    logger.debug(f"Saved data to {path}")


def load_json(file_path: Path | str) -> Any:
    """
    Load data from a JSON file.

    Args:
        file_path: Path to the JSON file

    Returns:
        Parsed JSON data

    Raises:
        FileNotFoundError: If the file doesn't exist
        json.JSONDecodeError: If the file contains invalid JSON
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    logger.debug(f"Loaded data from {path}")
    return data
