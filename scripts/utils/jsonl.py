"""JSONL utilities for deterministic, diff-friendly data storage.

JSONL (JSON Lines) stores one JSON object per line, enabling:
- Git diffs that show only changed records (not entire file reformatting)
- Stable sorting by primary key for consistent output
- Stable key ordering within each record for minimal diffs
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable


def save_jsonl(
    items: list[dict[str, Any]],
    path: Path,
    sort_key: Callable[[dict[str, Any]], Any] | None = None,
    ensure_ascii: bool = False,
) -> None:
    """Save a list of dictionaries to a JSONL file with stable ordering.

    Args:
        items: List of dictionaries to save
        path: Path to the output JSONL file
        sort_key: Optional function to extract sort key from each item (e.g., lambda x: x['id'])
        ensure_ascii: If True, escape non-ASCII characters (default False for readability)
    """
    if sort_key:
        items = sorted(items, key=sort_key)

    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            # sort_keys=True ensures stable key ordering within each record
            line = json.dumps(item, ensure_ascii=ensure_ascii, sort_keys=True, separators=(",", ":"))
            f.write(line)
            f.write("\n")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load a JSONL file into a list of dictionaries.

    Args:
        path: Path to the JSONL file

    Returns:
        List of dictionaries, one per line

    Raises:
        FileNotFoundError: If the file does not exist
        json.JSONDecodeError: If a line contains invalid JSON
    """
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise json.JSONDecodeError(
                    f"Invalid JSON at line {line_num}: {e.msg}",
                    e.doc,
                    e.pos,
                ) from e
    return items
