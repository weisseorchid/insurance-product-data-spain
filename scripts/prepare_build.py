"""Prepare the package for building by generating the database.

This script must be run before `uv build` or `pip install -e .` to ensure
the SQLite database is built from JSONL sources.

Run with: uv run python -m scripts.prepare_build
"""

from scripts.build_db import build_database

if __name__ == "__main__":
    db_path = build_database()
    print(f"✓ Database ready for packaging: {db_path}")
    print("You can now run: uv build")
