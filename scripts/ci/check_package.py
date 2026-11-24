#!/usr/bin/env python3
"""Validate package build: wheel contains DB, install works, data counts OK."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

# Thresholds (not exact counts)
MIN_COMPANIES = 1000
MIN_DISTRIBUTORS = 50000


def check_wheel_contains_db(wheel_path: Path) -> tuple[bool, str]:
    """Check if wheel contains the database file."""
    try:
        with zipfile.ZipFile(wheel_path) as zf:
            files = zf.namelist()
            db_files = [f for f in files if "insurance.db" in f and f.endswith(".db")]

            if not db_files:
                return False, "Wheel does not contain insurance.db"

            # Check size
            db_file = db_files[0]
            info = zf.getinfo(db_file)
            size_mb = info.file_size / (1024 * 1024)

            if size_mb < 10:
                return False, f"Database in wheel is too small: {size_mb:.1f} MB (expected ~50+ MB)"

            return True, f"Found {db_file} ({size_mb:.1f} MB)"

    except Exception as e:
        return False, f"Error checking wheel: {e}"


def test_install_and_counts(wheel_path: Path) -> tuple[bool, str, dict]:
    """Install wheel in temp venv and check data counts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        venv_path = Path(tmpdir) / "test-venv"

        try:
            # Create venv
            subprocess.run(
                ["uv", "venv", str(venv_path)],
                check=True,
                capture_output=True,
            )

            # Install wheel
            subprocess.run(
                ["uv", "pip", "install", "--python", str(venv_path / "bin" / "python"), str(wheel_path)],
                check=True,
                capture_output=True,
            )

            # Test import and counts
            test_script = """
from insurance_product_data_sp import companies, distributors, branches, products
print(f"{len(companies)},{len(distributors)},{len(branches)},{len(products)}")
"""

            result = subprocess.run(
                [str(venv_path / "bin" / "python"), "-c", test_script],
                check=True,
                capture_output=True,
                text=True,
            )

            counts = result.stdout.strip().split(",")
            companies = int(counts[0])
            distributors = int(counts[1])
            branches = int(counts[2])
            products = int(counts[3])

            counts_dict = {
                "companies": companies,
                "distributors": distributors,
                "branches": branches,
                "products": products,
            }

            # Validate counts
            if companies < MIN_COMPANIES:
                return False, f"Companies count too low: {companies} < {MIN_COMPANIES}", counts_dict

            if distributors < MIN_DISTRIBUTORS:
                return False, f"Distributors count too low: {distributors} < {MIN_DISTRIBUTORS}", counts_dict

            return True, "Package install and data counts OK", counts_dict

        except subprocess.CalledProcessError as e:
            return False, f"Installation or test failed: {e.stderr if e.stderr else str(e)}", {}
        except Exception as e:
            return False, f"Error during test: {e}", {}


def main() -> int:
    """Run package validation."""
    print("🔍 Checking package build...")
    print()

    repo_root = Path(__file__).parent.parent.parent
    dist_dir = repo_root / "dist"

    # Find wheel file
    wheel_files = list(dist_dir.glob("*.whl"))
    if not wheel_files:
        print("❌ No wheel file found in dist/")
        print("   Run: uv build --wheel")
        return 1

    wheel_path = wheel_files[0]
    print(f"Found wheel: {wheel_path.name}")
    print()

    # Check wheel contains DB
    print("Checking wheel contains database...")
    contains_db, message = check_wheel_contains_db(wheel_path)
    if contains_db:
        print(f"  ✅ {message}")
    else:
        print(f"  ❌ {message}")
        return 1
    print()

    # Test installation and counts
    print("Testing installation in clean venv...")
    success, message, counts = test_install_and_counts(wheel_path)

    if success:
        print(f"  ✅ {message}")
        print(f"     Companies: {counts['companies']}")
        print(f"     Distributors: {counts['distributors']}")
        print(f"     Branches: {counts['branches']}")
        print(f"     Products: {counts['products']}")
    else:
        print(f"  ❌ {message}")
        if counts:
            print(f"     Got: Companies={counts.get('companies')}, Distributors={counts.get('distributors')}")
        return 1
    print()

    print("✅ Package validation PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
