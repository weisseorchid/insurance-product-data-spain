#!/usr/bin/env python3
"""Check repository hygiene: no tracked unwanted files, no large additions.

Also scans all blobs in PR commit range for size/extension violations.
"""

from __future__ import annotations

import argparse
import subprocess
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


def check_pr_blob_additions(base_ref: str, head_ref: str = "HEAD") -> list[str]:
    """
    Check all blobs added in PR commit range for size/extension violations.

    Scans base..head to catch blobs added then removed within the PR.

    Args:
        base_ref: Base ref (e.g., 'origin/main' or commit SHA)
        head_ref: Head ref (default: 'HEAD')

    Returns:
        List of error messages
    """
    errors = []
    repo_root = Path(__file__).parent.parent.parent

    try:
        # Get all commits in the range
        result = subprocess.run(
            ["git", "rev-list", f"{base_ref}..{head_ref}"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        commits = result.stdout.strip().split("\n")

        if not commits or commits == [""]:
            return []

        # Track seen blobs to avoid duplicates
        seen_blobs = set()

        for commit in commits:
            # Get all blobs in this commit
            tree_result = subprocess.run(
                ["git", "ls-tree", "-r", "-l", commit],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=True,
            )

            for line in tree_result.stdout.strip().split("\n"):
                if not line:
                    continue

                parts = line.split(None, 4)
                if len(parts) < 5:
                    continue

                mode, obj_type, blob_hash, size_str, file_path = parts

                if obj_type != "blob" or blob_hash in seen_blobs:
                    continue

                seen_blobs.add(blob_hash)

                try:
                    size = int(size_str)
                except ValueError:
                    continue

                # Check size
                if size > MAX_FILE_SIZE:
                    # Skip allowlisted files
                    if file_path not in LARGE_FILE_ALLOWLIST:
                        size_mb = size / (1024 * 1024)
                        max_mb = MAX_FILE_SIZE / (1024 * 1024)
                        errors.append(
                            f"Blob exceeds size limit: {file_path} "
                            f"(blob: {blob_hash[:8]}, {size_mb:.2f} MB > {max_mb:.0f} MB limit)"
                        )

                # Check extension
                file_path_obj = Path(file_path)
                if file_path_obj.suffix and f"*{file_path_obj.suffix}" in DISALLOWED_PATTERNS:
                    errors.append(
                        f"Disallowed file extension in blob: {file_path} "
                        f"(blob: {blob_hash[:8]}, extension: {file_path_obj.suffix})"
                    )

    except subprocess.CalledProcessError as e:
        errors.append(f"Git command failed: {e.stderr}")

    return errors


def main() -> int:
    """Run all hygiene checks."""
    parser = argparse.ArgumentParser(description="Check repository hygiene")
    parser.add_argument(
        "--base",
        help="Base ref for PR range check (e.g., origin/main or commit SHA)",
    )
    parser.add_argument(
        "--head",
        default="HEAD",
        help="Head ref for PR range check (default: HEAD)",
    )

    args = parser.parse_args()

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

    # Check PR blob additions if base ref provided
    if args.base:
        print(f"Checking blobs added in PR range {args.base}..{args.head}...")
        pr_errors = check_pr_blob_additions(args.base, args.head)
        if pr_errors:
            all_errors.extend(pr_errors)
            for error in pr_errors:
                print(f"  ❌ {error}")
        else:
            print("  ✅ No violations in PR blob range")
        print()

    if all_errors:
        print(f"❌ Repository hygiene check FAILED with {len(all_errors)} error(s)")
        return 1

    print("✅ Repository hygiene check PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
