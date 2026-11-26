"""Tests for the shared companies loader."""

import json
from pathlib import Path

import pytest

from scripts.utils import companies as companies_mod
from scripts.utils.companies import (
    company_folder_name,
    company_key_for_folder,
    find_company,
    load_companies,
    resolve_companies_path,
)

REPO_ROOT = Path(__file__).parent.parent


def test_default_path_is_canonical_jsonl():
    assert resolve_companies_path() == REPO_ROOT / "data" / "insurance_companies.jsonl"


def test_load_companies_from_repo_jsonl():
    companies = load_companies()
    assert len(companies) > 1000
    nn = find_company("C0737")
    assert nn is not None
    assert company_folder_name(nn).startswith("nationale_nederlanden_generales")


def test_company_key_for_existing_product_folder():
    folders = [p.name for p in (REPO_ROOT / "data" / "products_by_insurance_company").iterdir() if p.is_dir()]
    keys = {company_key_for_folder(name) for name in folders}
    assert {"C0737", "M0083"} <= keys


def test_falls_back_to_legacy_json(tmp_path, monkeypatch):
    legacy = tmp_path / "insurance_companies.json"
    legacy.write_text(json.dumps([{"company_key": "X1", "denomination": "Foo Seguros"}]), encoding="utf-8")
    monkeypatch.setattr(companies_mod, "INSURANCE_COMPANIES_JSONL", tmp_path / "insurance_companies.jsonl")
    monkeypatch.setattr(companies_mod, "INSURANCE_COMPANIES_JSON", legacy)
    assert resolve_companies_path() == legacy
    assert find_company("X1") == {"company_key": "X1", "denomination": "Foo Seguros"}


def test_jsonl_preferred_over_legacy_json(tmp_path, monkeypatch):
    jsonl = tmp_path / "insurance_companies.jsonl"
    jsonl.write_text('{"company_key":"A","denomination":"From JSONL"}\n', encoding="utf-8")
    legacy = tmp_path / "insurance_companies.json"
    legacy.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(companies_mod, "INSURANCE_COMPANIES_JSONL", jsonl)
    monkeypatch.setattr(companies_mod, "INSURANCE_COMPANIES_JSON", legacy)
    assert load_companies()[0]["denomination"] == "From JSONL"


def test_missing_files_raise(tmp_path, monkeypatch):
    monkeypatch.setattr(companies_mod, "INSURANCE_COMPANIES_JSONL", tmp_path / "a.jsonl")
    monkeypatch.setattr(companies_mod, "INSURANCE_COMPANIES_JSON", tmp_path / "a.json")
    with pytest.raises(FileNotFoundError):
        load_companies()


def test_legacy_descripcion_name_supported():
    assert company_folder_name({"descripcion": "Mutua Ejemplo, S.A."}) == "mutua_ejemplo_sa"


def test_no_script_reads_legacy_companies_json_directly():
    offenders = []
    for path in (REPO_ROOT / "scripts").rglob("*.py"):
        if path.name in {"config.py", "companies.py", "migrate_to_jsonl.py", "sync_data.py"}:
            continue
        if "INSURANCE_COMPANIES_JSON\n" in path.read_text() or 'insurance_companies.json"' in path.read_text():
            offenders.append(str(path))
    assert offenders == []
