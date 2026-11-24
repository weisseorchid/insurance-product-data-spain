# Source Manifest (per insurer)

The source manifest records, in git, **where each product's public documents come from**, so that
documents can be (re-)fetched reproducibly by `scripts/fetch_product_documents.py`. The PDFs and
markdown themselves never go into git: they live in the gitignored cache (`.cache/insurance-docs`),
and their provenance goes into the company's `documents.jsonl`.

## File layout

- One file per insurer: `data/sources/<company_key>.jsonl` (e.g. `data/sources/C0058.jsonl`).
- One JSON object per line. Each line is either a **document** or a **product** record, discriminated
  by `record_type`.
- Lines are sorted by `(record_type, id)`: all `document` records first (by `doc_id`), then all
  `product` records (by `product_name`).
- Validated by the pydantic models in `scripts/utils/source_manifest.py` and in CI by
  `scripts/ci/check_data_integrity.py`.

Products and documents are **many-to-many**: a product lists the `doc_id`s it uses, and one
document (e.g. a shared *condiciones generales*) can be used by several products.

## `document` records

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `record_type` | `"document"` | Yes | Discriminator |
| `doc_id` | `str` | Yes | Stable id, unique in the file, lowercase `[a-z0-9_-]` |
| `doc_type` | enum | Yes | `ipid`, `nota_informativa`, `condiciones_generales`, `condiciones_especiales`, `kid`, `folleto`, `other` |
| `source` | object | Yes | How to download it (see below), discriminated by `source.type` |
| `source_url` | `str` | Yes | **Human-facing** page where the document is offered (product page or documentation portal) |
| `title` | `str` | No | Title as shown by the insurer |
| `filename` | `str` | No | `*.pdf` name used in `documents.jsonl` (default `<doc_id>.pdf`) |
| `notes` | `str` | No | Free text (edition date, caveats, ...) |

### Source types

| `source.type` | Fields | Adapter | Notes |
|---------------|--------|---------|-------|
| `url` | `url` | `UrlAdapter` | Stable, direct PDF URL. Redirects are followed one hop at a time, robots-checked per host. |
| `mapfre_docprecon` | `document_id`, `entidad` | `MapfreDocpreconAdapter` | Mapfre's documentation portal (`www.mapfre.es/documentacion-precontractual/`). `entidad` `001` = C0058 Mapfre España, `003` = C0511 Mapfre Vida; CI checks it matches the file's company. |

New source types are added as a pydantic model in `source_manifest.py` plus an adapter registered in
`fetch_product_documents.default_adapters()`.

## `product` records

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `record_type` | `"product"` | Yes | Discriminator |
| `product_id` | `str` | Yes | URN `urn:<company_key>-NN`, same as in `index.json` |
| `product_name` | `str` | Yes | ASCII snake_case slug, same as in `index.json` |
| `display_name` | `str` | No | Commercial name |
| `product_page_url` | `str` | No | Public product page |
| `branches` | `list[str]` | Yes | DGSFP branch codes; must exist in `data/insurance_branches.jsonl` |
| `documents` | `list[str]` | Yes | `doc_id`s of the documents describing this product |
| `notes` | `str` | No | Free text (gaps, naming doubts, ...) |

## Validation rules (CI)

- Schema of every record (unknown fields are rejected), absolute `http(s)` URLs, enum values.
- File name is `<company_key>.jsonl` and the company exists in `data/insurance_companies.jsonl`.
- Sorted by `(record_type, id)`; `doc_id`, `product_name`, `product_id`, document filenames and
  document sources are unique.
- Every `doc_id` referenced by a product exists, and every document is used by at least one product.
- `product_id` starts with `urn:<company_key>-`; Mapfre `entidad` matches the company.
- Branch codes exist in `data/insurance_branches.jsonl`.

## Example (Mapfre España, C0058)

`data/sources/C0058.jsonl`:

```json
{"record_type":"document","doc_id":"coche_cg_0900ab44c391e066","doc_type":"condiciones_generales","title":"Condiciones generales","source":{"type":"mapfre_docprecon","document_id":"0900ab44c391e066","entidad":"001"},"source_url":"https://www.mapfre.es/documentacion-precontractual/resultados/?entidad=001&tomador=Particulares&agrupacion=Coche"}
{"record_type":"document","doc_id":"terceros_ipid_0900ab44c48adb6a","doc_type":"ipid","title":"Documento de Información del Producto de Seguro (DIPS)","source":{"type":"mapfre_docprecon","document_id":"0900ab44c48adb6a","entidad":"001"},"source_url":"https://www.mapfre.es/documentacion-precontractual/resultados/?entidad=001&tomador=Particulares&agrupacion=Coche"}
{"record_type":"document","doc_id":"terceros_nota_0900ab44c48b450d","doc_type":"nota_informativa","title":"Nota informativa","source":{"type":"mapfre_docprecon","document_id":"0900ab44c48b450d","entidad":"001"},"source_url":"https://www.mapfre.es/documentacion-precontractual/resultados/?entidad=001&tomador=Particulares&agrupacion=Coche"}
{"record_type":"product","product_id":"urn:C0058-01","product_name":"seguro_terceros","display_name":"Seguro Terceros","product_page_url":"https://www.mapfre.es/particulares/seguros-de-coche/terceros/","branches":["03","10"],"documents":["coche_cg_0900ab44c391e066","terceros_ipid_0900ab44c48adb6a","terceros_nota_0900ab44c48b450d"]}
{"record_type":"product","product_id":"urn:C0058-02","product_name":"seguro_terceros_ampliado","display_name":"Seguro Terceros Ampliado","branches":["03","10"],"documents":["coche_cg_0900ab44c391e066"]}
```

A plain-URL document looks like:

```json
{"record_type":"document","doc_id":"hogar_ipid","doc_type":"ipid","source":{"type":"url","url":"https://www.example-insurer.es/docs/ipid-hogar.pdf"},"source_url":"https://www.example-insurer.es/seguro-hogar","filename":"IPID-hogar.pdf"}
```

## Fetching

```bash
# List what would be fetched (no network)
uv run python -m scripts.fetch_product_documents --company-key C0058 --dry-run
# Fetch (one product, default 3 s between requests per host)
uv run python -m scripts.fetch_product_documents --company-key C0058 --product seguro_terceros
```

The fetcher:

- sends `User-Agent: insurance-product-data-spain-bot/0.1 (+https://github.com/weisseorchid/insurance-product-data-spain)`
  (never the browser UA used by the DGSFP client);
- checks `robots.txt` (and honours `Crawl-delay`); robots.txt that is unreachable, 5xx, 401/403 or 429
  means "do not crawl", 404 means "no rules";
- waits at least `--delay` seconds (default 3, minimum 1) between requests to the same host;
- retries only on 5xx, timeouts and connection errors (exponential backoff, `--max-retries`, default 3);
- **never bypasses protection**: 401/403/429 or a challenge/block page stops all further requests to
  that host for the run, and the affected documents are recorded as gaps;
- requires `%PDF-` magic bytes, stores the PDF by sha256 in the cache, converts and validates it
  (`scripts/utils/document_validation.py`) before recording anything;
- is idempotent: documents whose source is already in `documents.jsonl` with PDF and markdown in the
  cache are skipped unless `--force`;
- fetches a shared document once and upserts one `documents.jsonl` record per product using it;
- logs `fetch_gap` and `fetch_run` events to `data/runs.jsonl` and exits non-zero if there were gaps.

### `documents.jsonl` records written by the fetcher

`doc_id`, `doc_type`, `filename`, `markdown_sha256`, `pdf_sha256`, `pdf_size`, `product_id`,
`product_name`, `retrieved_at` (UTC ISO 8601), `source` (the manifest `source` object, for
re-fetching) and `source_url` (the human-facing page). Records are keyed by
(`product_id`, `filename`), so a re-fetch replaces the previous record.

### Mapfre documentation portal

The portal's download buttons have `href="#"` and a `data-id`; the portal's own JavaScript POSTs
`{"chunk": n}` (and `tempFile` from chunk 2) to `docpreconcomercialesdocument?documentId=<id>` and gets
`current/total#|#tempFile#|#fileName#|#<base64>` back, then sends a cleanup request. The adapter does
the same, with the honest UA, the per-host rate limit and the stop-on-block rules, then requires
`%PDF-`. Requests are governed by the robots.txt of `www.mapfre.es` (the portal page that uses the API).
The API key used by the portal is **not committed**; set `MAPFRE_DOCPRECON_API_KEY` in your local
environment (`.env` is gitignored). Without it every Mapfre document is recorded as a
`not_configured` gap.

## Downstream

- `scripts/process_pdfs.py --source cache` (default when there is no legacy `sources/` folder)
  converts cached PDFs listed in `documents.jsonl` and updates `markdown_sha256`.
- `scripts/analyze_products.py` reads each product's markdown from `documents.jsonl` + the cache
  (legacy `sources/{product}/*.md` is still used if present).
