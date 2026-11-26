"""Offline, deterministic repair of malformed company website fields.

Applies ``normalize_website`` to ``website`` and ``customer_service.web`` in
``data/insurance_companies.jsonl``. No network access; records whose values are
already well-formed are written back byte-identical. Use ``--check`` in CI-like
contexts to fail if any value would change.

Run with: uv run python -m scripts.normalize_company_websites [--check]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from scripts.config import INSURANCE_COMPANIES_JSONL
from scripts.utils.jsonl import load_jsonl, save_jsonl
from scripts.utils.text_transformations import normalize_website


def normalize_company_record(record: dict[str, Any]) -> list[tuple[str, str, str | None]]:
    """Normalize website fields in place; return the list of (field, old, new) changes."""
    changes: list[tuple[str, str, str | None]] = []
    website = record.get("website")
    if isinstance(website, str):
        new = normalize_website(website)
        if new != website:
            record["website"] = new
            changes.append(("website", website, new))
    service = record.get("customer_service")
    if isinstance(service, dict) and isinstance(service.get("web"), str):
        old = service["web"]
        new = normalize_website(old)
        if new != old:
            service["web"] = new
            changes.append(("customer_service.web", old, new))
    return changes


def main(argv: list[str] | None = None) -> int:
    summary = (__doc__ or "").splitlines()
    parser = argparse.ArgumentParser(description=summary[0] if summary else None)
    parser.add_argument("--path", type=Path, default=INSURANCE_COMPANIES_JSONL)
    parser.add_argument("--check", action="store_true", help="Only report; exit 1 if anything would change")
    args = parser.parse_args(argv)

    records = load_jsonl(args.path)
    total = 0
    for record in records:
        for field, old, new in normalize_company_record(record):
            total += 1
            print(f"{record.get('company_key')}: {field}: {old!r} -> {new!r}")

    if args.check:
        return 1 if total else 0
    if total:
        save_jsonl(records, args.path, sort_key=lambda x: x["company_key"])
    print(f"{total} value(s) normalized")
    return 0


if __name__ == "__main__":
    sys.exit(main())
