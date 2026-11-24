#!/usr/bin/env python3
"""Check repository hygiene: no tracked unwanted files, no large additions."""

from __future__ import annotations

import sys
from pathlib import Path

# Files that should never be tracked
DISALLOWED_PATTERNS = [
    "*.db",
    "*.db-wal",
    "*.db-shm",
    "*.pdf",
    ".env",  # Actual .env file (not .env.example)
    ".env.local",
    ".env.development.local",
    ".env.test.local",
    ".env.production.local",
    ".coverage",
    "htmlcov/",
    "dist/",
    ".cache/",  # Cache directory
]

# Large file allowlist: files that are allowed to be large
LARGE_FILE_ALLOWLIST = {
    "data/insurance_companies.jsonl",
    "data/insurance_distributors.jsonl",
    "data/insurance_branches.jsonl",
}

# Maximum file size for new files (1 MB)
MAX_FILE_SIZE = 1 * 1024 * 1024  # 1 MB in bytes


def check_disallowed_files() -> list[str]:
    """Check for files matching disallowed patterns."""
    repo_root = Path(__file__).parent.parent.parent
    errors = []

    for pattern in DISALLOWED_PATTERNS:
        # Convert glob pattern to Path glob
        matches = list(repo_root.rglob(pattern.replace("*.", ".")))
        for match in matches:
            # Check if it's tracked by git
            import subprocess

            result = subprocess.run(
                ["git", "ls-files", "--error-unmatch", str(match.relative_to(repo_root))],
                cwd=repo_root,
                capture_output=True,
            )
            if result.returncode == 0:
                errors.append(f"Disallowed file is tracked: {match.relative_to(repo_root)}")

    return errors


def check_large_files() -> list[str]:
    """Check for newly added large files not in allowlist."""
    repo_root = Path(__file__).parent.parent.parent
    errors = []

    import subprocess

    # Get list of tracked files
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return ["Failed to get tracked files from git"]

    for file_path in result.stdout.strip().split("\n"):
        if not file_path:
            continue

        full_path = repo_root / file_path
        if not full_path.exists():
            continue

        # Skip allowlisted files
        if file_path in LARGE_FILE_ALLOWLIST:
            continue

        file_size = full_path.stat().st_size
        if file_size > MAX_FILE_SIZE:
            size_mb = file_size / (1024 * 1024)
            errors.append(
                f"Large file not in allowlist: {file_path} ({size_mb:.2f} MB > {MAX_FILE_SIZE / (1024 * 1024):.0f} MB)"
            )

    return errors


def main() -> int:
    """Run all hygiene checks."""
    print("🔍 Checking repository hygiene...")
    print()

    all_errors = []

    # Check disallowed files
    print("Checking for disallowed tracked files...")
    disallowed_errors = check_disallowed_files()
    if disallowed_errors:
        all_errors.extend(disallowed_errors)
        for error in disallowed_errors:
            print(f"  ❌ {error}")
    else:
        print("  ✅ No disallowed files found")
    print()

    # Check large files
    print("Checking for large files...")
    large_file_errors = check_large_files()
    if large_file_errors:
        all_errors.extend(large_file_errors)
        for error in large_file_errors:
            print(f"  ❌ {error}")
    else:
        print("  ✅ No unexpected large files found")
    print()

    if all_errors:
        print(f"❌ Repository hygiene check FAILED with {len(all_errors)} error(s)")
        return 1

    print("✅ Repository hygiene check PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
