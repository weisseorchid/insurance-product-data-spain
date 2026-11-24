"""Per-insurer source manifest: which public documents exist and which products use them.

One committed JSONL file per insurer, ``data/sources/<company_key>.jsonl``, holding two
kinds of records (discriminated by ``record_type``):

- ``document``: one public document, identified by a stable ``doc_id``, with a
  machine-readable ``source`` (how to download it; discriminated by ``source.type``)
  and a human-facing ``source_url`` (product page or documentation portal)
- ``product``: one commercial product, which references documents by ``doc_id``

Products and documents are many-to-many: one ``condiciones_generales`` can serve
several products. Records are sorted by (``record_type``, ``doc_id`` / ``product_name``).

The manifest is the input to ``scripts/fetch_product_documents.py`` and is validated in
CI by ``scripts/ci/check_data_integrity.py``. See docs/SOURCE_MANIFEST.md.
"""

from __future__ import annotations

import json
import re
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator, model_validator

from scripts.config import BASE_STORAGE_PATH

SOURCE_MANIFEST_DIR: Path = BASE_STORAGE_PATH / "sources"

ID_RE = re.compile(r"^[a-z0-9]+(?:[_-][a-z0-9]+)*$")
COMPANY_KEY_RE = re.compile(r"^[A-Z]{1,2}\d{3,4}$")
PRODUCT_ID_RE = re.compile(r"^urn:[A-Z]{1,2}\d{3,4}-\d{2,}$")
FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.pdf$")

# Mapfre documentation portal "entidad" codes and the DGSFP company they belong to.
MAPFRE_ENTIDAD_COMPANY = {"001": "C0058", "003": "C0511"}


class SourceDocType(str, Enum):
    """Document types, aligned with ``doc_type`` in documents.jsonl."""

    IPID = "ipid"  # Documento de información sobre el producto de seguro (DIPS/IPID)
    NOTA_INFORMATIVA = "nota_informativa"
    CONDICIONES_GENERALES = "condiciones_generales"
    CONDICIONES_ESPECIALES = "condiciones_especiales"
    KID = "kid"  # PRIIPs key information document
    FOLLETO = "folleto"
    OTHER = "other"


def _check_http_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or value != value.strip():
        raise ValueError(f"must be an absolute http(s) URL, got {value!r}")
    return value


# -- document sources (discriminated by "type") --------------------------------


class UrlSource(BaseModel):
    """A document with a stable, direct public URL."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["url"] = "url"
    url: str = Field(..., description="Exact public URL of the PDF")

    @field_validator("url")
    @classmethod
    def _url(cls, v: str) -> str:
        return _check_http_url(v)

    def key(self) -> str:
        return self.url


class MapfreDocpreconSource(BaseModel):
    """A document served by Mapfre's documentation portal (www.mapfre.es/documentacion-precontractual/)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["mapfre_docprecon"] = "mapfre_docprecon"
    document_id: str = Field(..., description="Portal document id (data-id of the download button)")
    entidad: str = Field(..., description="Portal entity code: 001 = C0058 Mapfre España, 003 = C0511 Mapfre Vida")

    @field_validator("document_id")
    @classmethod
    def _document_id(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9]{8,64}", v):
            raise ValueError(f"invalid document_id {v!r}")
        return v

    @field_validator("entidad")
    @classmethod
    def _entidad(cls, v: str) -> str:
        if v not in MAPFRE_ENTIDAD_COMPANY:
            raise ValueError(f"unknown entidad {v!r}; known: {sorted(MAPFRE_ENTIDAD_COMPANY)}")
        return v

    def key(self) -> str:
        return f"{self.entidad}:{self.document_id}"


DocumentSource = Annotated[UrlSource | MapfreDocpreconSource, Field(discriminator="type")]


# -- records ------------------------------------------------------------------


class ManifestDocument(BaseModel):
    """One public document (may be shared by several products)."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    record_type: Literal["document"] = "document"
    doc_id: str = Field(..., description="Stable id, unique in the file (lowercase, [a-z0-9_-])")
    doc_type: SourceDocType
    source: DocumentSource
    source_url: str = Field(..., description="Human-facing page where the document is offered (product/portal page)")
    title: str | None = Field(None, description="Document title as shown by the insurer")
    filename: str | None = Field(None, description="Filename for documents.jsonl (default: <doc_id>.pdf)")
    notes: str | None = None

    @field_validator("doc_id")
    @classmethod
    def _doc_id(cls, v: str) -> str:
        if not ID_RE.match(v):
            raise ValueError(f"doc_id must be lowercase [a-z0-9_-], got {v!r}")
        return v

    @field_validator("source_url")
    @classmethod
    def _source_url(cls, v: str) -> str:
        return _check_http_url(v)

    @field_validator("filename")
    @classmethod
    def _filename(cls, v: str | None) -> str | None:
        if v is not None and not FILENAME_RE.match(v):
            raise ValueError(f"filename must be a plain *.pdf name without paths, got {v!r}")
        return v

    def resolved_filename(self) -> str:
        return self.filename or f"{self.doc_id}.pdf"


class ManifestProduct(BaseModel):
    """One commercial product and the documents that describe it."""

    model_config = ConfigDict(extra="forbid")

    record_type: Literal["product"] = "product"
    product_id: str = Field(..., description="Product URN, same as in index.json (e.g. urn:C0058-01)")
    product_name: str = Field(..., description="snake_case slug, same as in index.json")
    display_name: str | None = Field(None, description="Commercial name as shown by the insurer")
    product_page_url: str | None = Field(None, description="Public product page")
    branches: list[str] = Field(..., min_length=1, description="DGSFP branch codes (data/insurance_branches.jsonl)")
    documents: list[str] = Field(..., min_length=1, description="doc_ids of this product's documents")
    notes: str | None = None

    @field_validator("product_name")
    @classmethod
    def _product_name(cls, v: str) -> str:
        if not re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)*", v):
            raise ValueError(f"product_name must be ASCII snake_case, got {v!r}")
        return v

    @field_validator("product_id")
    @classmethod
    def _product_id(cls, v: str) -> str:
        if not PRODUCT_ID_RE.match(v):
            raise ValueError(f"product_id must look like urn:C0000-01, got {v!r}")
        return v

    @field_validator("product_page_url")
    @classmethod
    def _page(cls, v: str | None) -> str | None:
        return _check_http_url(v) if v is not None else v

    @field_validator("branches")
    @classmethod
    def _branches(cls, v: list[str]) -> list[str]:
        if any(not re.fullmatch(r"\d{2}", c) for c in v) or len(set(v)) != len(v):
            raise ValueError(f"branches must be unique two-digit codes, got {v!r}")
        return v

    @field_validator("documents")
    @classmethod
    def _documents(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("duplicate doc_id in documents")
        return v


ManifestRecord = Annotated[ManifestDocument | ManifestProduct, Field(discriminator="record_type")]
_RECORD_ADAPTER: TypeAdapter[ManifestDocument | ManifestProduct] = TypeAdapter(ManifestRecord)


class SourceManifest(BaseModel):
    """A validated manifest for one company."""

    company_key: str
    documents: dict[str, ManifestDocument]
    products: list[ManifestProduct]

    @model_validator(mode="after")
    def _references(self) -> SourceManifest:
        problems = manifest_reference_errors(self.company_key, self.documents, self.products)
        if problems:
            raise ValueError("; ".join(problems))
        return self

    def documents_for(self, product: ManifestProduct) -> list[ManifestDocument]:
        return [self.documents[d] for d in product.documents]


def _sort_key(record: ManifestDocument | ManifestProduct) -> tuple[str, str]:
    return (record.record_type, record.doc_id if isinstance(record, ManifestDocument) else record.product_name)


def manifest_reference_errors(
    company_key: str, documents: dict[str, ManifestDocument], products: list[ManifestProduct]
) -> list[str]:
    """Cross-record checks: ids, references, orphans, company consistency."""
    errors: list[str] = []
    referenced: set[str] = set()
    for product in products:
        if not product.product_id.startswith(f"urn:{company_key}-"):
            errors.append(
                f"product {product.product_name}: product_id {product.product_id} is not urn:{company_key}-NN"
            )
        for doc_id in product.documents:
            referenced.add(doc_id)
            if doc_id not in documents:
                errors.append(f"product {product.product_name}: unknown doc_id {doc_id!r}")
    for doc_id, doc in documents.items():
        if doc_id not in referenced:
            errors.append(f"document {doc_id}: not referenced by any product")
        if isinstance(doc.source, MapfreDocpreconSource):
            expected = MAPFRE_ENTIDAD_COMPANY[doc.source.entidad]
            if expected != company_key:
                errors.append(
                    f"document {doc_id}: entidad {doc.source.entidad} belongs to {expected}, not {company_key}"
                )
    sources: dict[tuple[str, str], str] = {}
    for doc_id, doc in documents.items():
        key = (doc.source.type, doc.source.key())
        if key in sources:
            errors.append(f"document {doc_id}: same source as {sources[key]}")
        sources[key] = doc_id
    return errors


def manifest_path(company_key: str, manifest_dir: Path | None = None) -> Path:
    return (manifest_dir or SOURCE_MANIFEST_DIR) / f"{company_key}.jsonl"


def validate_manifest_file(path: Path, valid_branch_codes: set[str] | None = None) -> list[str]:
    """Validate one manifest file; returns error messages (empty if valid)."""
    errors: list[str] = []
    company_key = path.stem
    if not COMPANY_KEY_RE.match(company_key):
        return [f"file name must be <company_key>.jsonl, got {path.name}"]
    documents: dict[str, ManifestDocument] = {}
    products: dict[str, ManifestProduct] = {}
    product_ids: set[str] = set()
    previous: tuple[str, str] | None = None
    for line_num, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = _RECORD_ADAPTER.validate_python(json.loads(line))
        except json.JSONDecodeError as e:
            errors.append(f"line {line_num}: invalid JSON: {e}")
            continue
        except ValidationError as e:
            for err in e.errors():
                loc = ".".join(str(p) for p in err["loc"]) or "<record>"
                errors.append(f"line {line_num}: {loc}: {err['msg']}")
            continue
        key = _sort_key(record)
        if previous is not None and key < previous:
            errors.append(f"line {line_num}: not sorted by (record_type, id): {key} after {previous}")
        previous = key
        if isinstance(record, ManifestDocument):
            if record.doc_id in documents:
                errors.append(f"line {line_num}: duplicate doc_id {record.doc_id!r}")
            documents[record.doc_id] = record
        else:
            if record.product_name in products:
                errors.append(f"line {line_num}: duplicate product_name {record.product_name!r}")
            if record.product_id in product_ids:
                errors.append(f"line {line_num}: duplicate product_id {record.product_id!r}")
            products[record.product_name] = record
            product_ids.add(record.product_id)
            if valid_branch_codes is not None:
                errors.extend(
                    f"line {line_num}: branch code {c!r} not in data/insurance_branches.jsonl"
                    for c in record.branches
                    if c not in valid_branch_codes
                )
    filenames: dict[str, str] = {}
    for doc in documents.values():
        name = doc.resolved_filename()
        if name in filenames:
            errors.append(f"document {doc.doc_id}: filename {name} also used by {filenames[name]}")
        filenames[name] = doc.doc_id
    errors.extend(manifest_reference_errors(company_key, documents, list(products.values())))
    return errors


def load_manifest(path: Path) -> SourceManifest:
    """Load and validate a manifest. Raises ValueError listing every problem."""
    errors = validate_manifest_file(path)
    if errors:
        raise ValueError(f"Invalid source manifest {path}:\n  " + "\n  ".join(errors))
    documents: dict[str, ManifestDocument] = {}
    products: list[ManifestProduct] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = _RECORD_ADAPTER.validate_python(json.loads(line))
            if isinstance(record, ManifestDocument):
                documents[record.doc_id] = record
            else:
                products.append(record)
    return SourceManifest(company_key=path.stem, documents=documents, products=products)
