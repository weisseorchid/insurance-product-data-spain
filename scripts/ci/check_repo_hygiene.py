"""Repository hygiene checks for pull requests.

This script checks all blobs added in a PR commit range (not just the final tree)
for:
- Blobs exceeding size limits
- Disallowed file extensions (e.g., .db, .sqlite)
- Accidentally committed binaries, secrets, or cache files

This prevents PRs from adding and then removing large files, which would still
bloat the repository history.

Exit codes:
- 0: All checks passed
- 1: Checks failed
"""

import argparse
import subprocess
import sys
from pathlib import Path

from insurance_product_data_sp.core.logging import logger

# Maximum blob size in bytes (50MB)
MAX_BLOB_SIZE = 50 * 1024 * 1024

# Disallowed file extensions
DISALLOWED_EXTENSIONS = {
    ".db",
    ".sqlite",
    ".sqlite3",
    ".pyc",
    ".pyo",
    ".so",
    ".dylib",
    ".dll",
    ".exe",
}

# Disallowed file patterns (paths that should never be committed)
DISALLOWED_PATTERNS = [
    ".env",
    ".cache/",
    "__pycache__/",
    ".pytest_cache/",
    "node_modules/",
    ".venv/",
    "venv/",
]


def get_added_blobs_in_range(base_ref: str, head_ref: str) -> list[tuple[str, str, int]]:
    """
    Get all blobs added in the commit range base_ref..head_ref.

    Args:
        base_ref: Base ref (e.g., 'origin/main')
        head_ref: Head ref (e.g., 'HEAD')

    Returns:
        List of tuples (blob_hash, file_path, size_bytes)
    """
    try:
        # Get all commits in the range
        result = subprocess.run(
            ["git", "rev-list", f"{base_ref}..{head_ref}"],
            capture_output=True,
            text=True,
            check=True,
        )
        commits = result.stdout.strip().split("\n")

        if not commits or commits == [""]:
            logger.warning(f"No commits found in range {base_ref}..{head_ref}")
            return []

        # For each commit, get all blobs added
        all_blobs: dict[str, tuple[str, int]] = {}  # blob_hash -> (path, size)

        for commit in commits:
            # Get tree of this commit
            tree_result = subprocess.run(
                ["git", "ls-tree", "-r", "-l", commit],
                capture_output=True,
                text=True,
                check=True,
            )

            # Parse ls-tree output: <mode> <type> <hash> <size> <path>
            for line in tree_result.stdout.strip().split("\n"):
                if not line:
                    continue

                parts = line.split(None, 4)
                if len(parts) < 5:
                    continue

                mode, obj_type, blob_hash, size_str, file_path = parts

                if obj_type != "blob":
                    continue

                try:
                    size = int(size_str)
                except ValueError:
                    continue

                # Store unique blobs
                if blob_hash not in all_blobs:
                    all_blobs[blob_hash] = (file_path, size)

        return [(blob, path, size) for blob, (path, size) in all_blobs.items()]

    except subprocess.CalledProcessError as e:
        logger.error(f"Git command failed: {e}")
        logger.error(f"stdout: {e.stdout}")
        logger.error(f"stderr: {e.stderr}")
        return []


def check_blob_size(blob_hash: str, file_path: str, size: int, max_size: int) -> bool:
    """
    Check if a blob exceeds the maximum size.

    Args:
        blob_hash: Git blob hash
        file_path: Path to the file
        size: Size in bytes
        max_size: Maximum allowed size in bytes

    Returns:
        True if check passed, False otherwise
    """
    if size > max_size:
        size_mb = size / (1024 * 1024)
        max_mb = max_size / (1024 * 1024)
        logger.error(
            f"[FAIL] Blob exceeds size limit: {file_path}\n"
            f"  Blob: {blob_hash}\n"
            f"  Size: {size_mb:.2f} MB (limit: {max_mb:.2f} MB)"
        )
        return False
    return True


def check_file_extension(file_path: str, disallowed_exts: set[str]) -> bool:
    """
    Check if a file has a disallowed extension.

    Args:
        file_path: Path to the file
        disallowed_exts: Set of disallowed extensions

    Returns:
        True if check passed, False otherwise
    """
    path = Path(file_path)
    if path.suffix.lower() in disallowed_exts:
        logger.error(f"[FAIL] Disallowed file extension: {file_path}\n  Extension: {path.suffix}")
        return False
    return True


def check_file_pattern(file_path: str, disallowed_patterns: list[str]) -> bool:
    """
    Check if a file path matches disallowed patterns.

    Args:
        file_path: Path to the file
        disallowed_patterns: List of disallowed path patterns

    Returns:
        True if check passed, False otherwise
    """
    for pattern in disallowed_patterns:
        if pattern in file_path:
            logger.error(f"[FAIL] Disallowed file pattern: {file_path}\n  Pattern: {pattern}")
            return False
    return True


def main():
    """Main entry point for repository hygiene checks."""
    parser = argparse.ArgumentParser(description="Check repository hygiene for pull requests")
    parser.add_argument(
        "--base",
        default="origin/main",
        help="Base ref to compare against (default: origin/main)",
    )
    parser.add_argument(
        "--head",
        default="HEAD",
        help="Head ref to check (default: HEAD)",
    )
    parser.add_argument(
        "--max-size-mb",
        type=float,
        default=50.0,
        help="Maximum blob size in MB (default: 50.0)",
    )

    args = parser.parse_args()

    max_size_bytes = int(args.max_size_mb * 1024 * 1024)

    logger.info("Running repository hygiene checks")
    logger.info(f"Commit range: {args.base}..{args.head}")
    logger.info(f"Max blob size: {args.max_size_mb} MB")

    # Get all blobs added in the range
    blobs = get_added_blobs_in_range(args.base, args.head)

    if not blobs:
        logger.info("No new blobs found in commit range")
        sys.exit(0)

    logger.info(f"Checking {len(blobs)} blobs added in commit range...")

    all_passed = True
    failed_checks = {
        "size": 0,
        "extension": 0,
        "pattern": 0,
    }

    for blob_hash, file_path, size in blobs:
        # Check size
        if not check_blob_size(blob_hash, file_path, size, max_size_bytes):
            failed_checks["size"] += 1
            all_passed = False

        # Check extension
        if not check_file_extension(file_path, DISALLOWED_EXTENSIONS):
            failed_checks["extension"] += 1
            all_passed = False

        # Check patterns
        if not check_file_pattern(file_path, DISALLOWED_PATTERNS):
            failed_checks["pattern"] += 1
            all_passed = False

    # Report summary
    logger.info("\n" + "=" * 60)
    logger.info("Repository Hygiene Check Summary")
    logger.info("=" * 60)
    logger.info(f"Blobs checked: {len(blobs)}")
    logger.info(f"Size violations: {failed_checks['size']}")
    logger.info(f"Extension violations: {failed_checks['extension']}")
    logger.info(f"Pattern violations: {failed_checks['pattern']}")
    logger.info("=" * 60)

    if all_passed:
        logger.info("✓ All repository hygiene checks passed")
        sys.exit(0)
    else:
        logger.error("✗ Repository hygiene checks failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
