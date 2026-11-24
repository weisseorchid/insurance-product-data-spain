"""Tests for the per-insurer source manifest (data/sources/<company_key>.jsonl)."""

import json
from pathlib import Path

import pytest

from scripts.utils.source_manifest import load_manifest, validate_manifest_file

PORTAL = (
    "https://www.mapfre.es/documentacion-precontractual/resultados/?entidad=001&tomador=Particulares&agrupacion=Coche"
)

# Real ids from the Mapfre discovery inventory (Coche: Seguro Terceros / Terceros Ampliado share one CG)
MAPFRE_RECORDS = [
    {
        "record_type": "document",
        "doc_id": "coche_cg_0900ab44c391e066",
        "doc_type": "condiciones_generales",
        "title": "Condiciones generales",
        "source": {"type": "mapfre_docprecon", "document_id": "0900ab44c391e066", "entidad": "001"},
        "source_url": PORTAL,
    },
    {
        "record_type": "document",
        "doc_id": "terceros_ipid_0900ab44c48adb6a",
        "doc_type": "ipid",
        "title": "Documento de Información del Producto de Seguro (DIPS)",
        "source": {"type": "mapfre_docprecon", "document_id": "0900ab44c48adb6a", "entidad": "001"},
        "source_url": PORTAL,
    },
    {
        "record_type": "document",
        "doc_id": "terceros_nota_0900ab44c48b450d",
        "doc_type": "nota_informativa",
        "source": {"type": "mapfre_docprecon", "document_id": "0900ab44c48b450d", "entidad": "001"},
        "source_url": PORTAL,
    },
    {
        "record_type": "product",
        "product_id": "urn:C0058-01",
        "product_name": "seguro_terceros",
        "display_name": "Seguro Terceros",
        "product_page_url": "https://www.mapfre.es/particulares/seguros-de-coche/terceros/",
        "branches": ["03", "10"],
        "documents": ["coche_cg_0900ab44c391e066", "terceros_ipid_0900ab44c48adb6a", "terceros_nota_0900ab44c48b450d"],
    },
    {
        "record_type": "product",
        "product_id": "urn:C0058-02",
        "product_name": "seguro_terceros_ampliado",
        "display_name": "Seguro Terceros Ampliado",
        "branches": ["03", "10"],
        "documents": ["coche_cg_0900ab44c391e066"],
    },
]


def write_manifest(tmp_path: Path, records: list[dict], name: str = "C0058.jsonl") -> Path:
    path = tmp_path / name
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    return path


def test_valid_mapfre_manifest_loads_with_shared_document(tmp_path):
    manifest = load_manifest(write_manifest(tmp_path, MAPFRE_RECORDS))
    assert manifest.company_key == "C0058"
    assert len(manifest.documents) == 3
    users = [p.product_name for p in manifest.products if "coche_cg_0900ab44c391e066" in p.documents]
    assert users == ["seguro_terceros", "seguro_terceros_ampliado"]
    cg = manifest.documents["coche_cg_0900ab44c391e066"]
    assert cg.source.type == "mapfre_docprecon"
    assert cg.resolved_filename() == "coche_cg_0900ab44c391e066.pdf"


def test_url_source_and_branch_validation(tmp_path):
    records = [
        {
            "record_type": "document",
            "doc_id": "hogar_ipid",
            "doc_type": "ipid",
            "source": {"type": "url", "url": "https://www.nnespana.es/docs/ipid-hogar.pdf"},
            "source_url": "https://www.nnespana.es/seguro-hogar",
            "filename": "IPID-hogar.pdf",
        },
        {
            "record_type": "product",
            "product_id": "urn:C0737-01",
            "product_name": "seguro_hogar",
            "branches": ["09", "21"],
            "documents": ["hogar_ipid"],
        },
    ]
    path = write_manifest(tmp_path, records, "C0737.jsonl")
    assert validate_manifest_file(path) == []
    errors = validate_manifest_file(path, valid_branch_codes={"09"})
    assert any("'21'" in e for e in errors)


def _errors_for(tmp_path, records, name="C0058.jsonl"):
    return "\n".join(validate_manifest_file(write_manifest(tmp_path, records, name)))


def test_unknown_reference_and_orphan_document(tmp_path):
    records = [dict(r) for r in MAPFRE_RECORDS]
    records[4] = {**records[4], "documents": ["missing_doc"]}
    errors = _errors_for(tmp_path, records)
    assert "unknown doc_id 'missing_doc'" in errors
    records = [r for r in MAPFRE_RECORDS if r.get("product_name") != "seguro_terceros"]
    errors = _errors_for(tmp_path, records)
    assert "terceros_ipid_0900ab44c48adb6a: not referenced by any product" in errors


def test_entidad_must_match_company(tmp_path):
    records = [
        {**r, "product_id": r["product_id"].replace("C0058", "C0511")} if r["record_type"] == "product" else r
        for r in MAPFRE_RECORDS
    ]
    errors = _errors_for(tmp_path, records, "C0511.jsonl")
    assert "entidad 001 belongs to C0058, not C0511" in errors


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda r: r.__setitem__(0, {**r[0], "source": {"type": "ftp", "url": "x"}}), "source"),
        (lambda r: r.__setitem__(0, {**r[0], "source": {"type": "url", "url": "not-a-url"}}), "absolute http(s) URL"),
        (lambda r: r.__setitem__(0, {**r[0], "source_url": "www.mapfre.es"}), "absolute http(s) URL"),
        (lambda r: r.__setitem__(0, {**r[0], "doc_type": "brochure"}), "doc_type"),
        (lambda r: r.__setitem__(0, {**r[0], "extra": 1}), "Extra inputs"),
        (lambda r: r.__setitem__(1, {**r[1], "source": r[0]["source"]}), "same source as"),
        (lambda r: r.reverse(), "not sorted"),
        (lambda r: r.__setitem__(4, {**r[4], "product_id": "urn:C0058-01"}), "duplicate product_id"),
        (lambda r: r.__setitem__(3, {**r[3], "product_name": "Seguro Terceros"}), "snake_case"),
        (
            lambda r: r.__setitem__(0, {**r[0], "source": {**r[0]["source"], "entidad": "002"}}),
            "unknown entidad",
        ),
    ],
)
def test_invalid_manifests(tmp_path, mutate, expected):
    records = [dict(r) for r in MAPFRE_RECORDS]
    mutate(records)
    assert expected in _errors_for(tmp_path, records)


def test_filename_must_match_company_key(tmp_path):
    assert "file name must be" in _errors_for(tmp_path, MAPFRE_RECORDS, "mapfre.jsonl")


def test_ci_check_validates_committed_manifests():
    import importlib.util

    root = Path(__file__).parent.parent
    spec = importlib.util.spec_from_file_location("cdi", root / "scripts/ci/check_data_integrity.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.check_source_manifests(root) == []
