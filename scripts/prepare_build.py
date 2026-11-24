"""Prepare for package build by ensuring database exists.

This script checks if the database exists and is valid, and provides
instructions if it doesn't. Run this before `uv build`.
"""

from __future__ import annotations

import sys

from scripts.build_db import build_database
from scripts.config import PACKAGE_DATA_PATH


def main() -> int:
    """Check database exists, build if missing."""
    db_path = PACKAGE_DATA_PATH / "insurance.db"

    if not db_path.exists():
        print("Database not found. Building from JSONL sources...")
        try:
            built_path = build_database()
            print(f"✓ Database built successfully: {built_path}")
            print(f"  Size: {built_path.stat().st_size / 1024 / 1024:.1f}MB")
        except Exception as e:
            print(f"✗ Failed to build database: {e}", file=sys.stderr)
            return 1
    else:
        print(f"✓ Database exists: {db_path}")
        print(f"  Size: {db_path.stat().st_size / 1024 / 1024:.1f}MB")

    print("\nReady to build package. Run:")
    print("  uv build")
    return 0


if __name__ == "__main__":
    sys.exit(main())
