"""Tests for DGSFP website normalization."""

from typing import Any

import pytest

from scripts.normalize_company_websites import normalize_company_record
from scripts.utils.companies import load_companies
from scripts.utils.text_transformations import normalize_website


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "www.HTTPS//WW.MAPFRE.COM/MEDIA/ACCIONISTAS/2021/2020-SFCR-MAPFRE-ESPANA",
            "https://www.MAPFRE.COM/MEDIA/ACCIONISTAS/2021/2020-SFCR-MAPFRE-ESPANA",
        ),
        ("www.HTTPS//WWW.ALLIANZ.ES/", "https://WWW.ALLIANZ.ES/"),
        ("www.WWW.PSN.ES", "WWW.PSN.ES"),
        ("www.www.coface.es/", "www.coface.es/"),
        (":www.almudenaseguros.es", "www.almudenaseguros.es"),
        ("http:ofimed.es", "http://ofimed.es"),
        ("HTTP:\\\\WWW.ANTONYASOCIADOS.COM", "http://WWW.ANTONYASOCIADOS.COM"),
        ("www.https//sdmm.es/", "https://sdmm.es/"),
        # Well-formed values are left untouched
        ("HTTPS://WWW.OCASO.ES/", "HTTPS://WWW.OCASO.ES/"),
        ("WWW.ZURICH.ES", "WWW.ZURICH.ES"),
        ("https://divinaseguros.com/seguro/asegrup", "https://divinaseguros.com/seguro/asegrup"),
        ("  www.mutua.es  ", "www.mutua.es"),
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_normalize_website(raw, expected):
    assert normalize_website(raw) == expected
    assert normalize_website(expected) == expected  # idempotent


def test_normalize_company_record_reports_changes():
    service: dict[str, Any] = {"web": ":www.x.es"}
    record: dict[str, Any] = {"company_key": "C0311", "website": "www.WWW.X.ES", "customer_service": service}
    changes = normalize_company_record(record)
    assert record["website"] == "WWW.X.ES"
    assert service["web"] == "www.x.es"
    assert [c[0] for c in changes] == ["website", "customer_service.web"]


def test_committed_companies_jsonl_is_normalized():
    for record in load_companies():
        assert normalize_company_record(record) == [], record["company_key"]
