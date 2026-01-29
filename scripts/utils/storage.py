"""Storage utilities for JSON file operations."""

import json
from pathlib import Path
from typing import Any

from src.core.logging import logger


def ensure_directory(path: Path) -> None:
    """Ensure a directory exists, creating it if necessary."""
    path.mkdir(parents=True, exist_ok=True)


def save_json(data: Any, file_path: Path | str, indent: int = 2) -> None:
    """
    Save data to a JSON file.

    Args:
        data: Data to save (must be JSON serializable)
        file_path: Path to the JSON file
        indent: JSON indentation level
    """
    path = Path(file_path)
    ensure_directory(path.parent)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)

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
