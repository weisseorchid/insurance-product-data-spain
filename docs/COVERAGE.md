# Coverage

Snapshot of first-batch insurers currently in this repository: Nationale-Nederlanden (C0737), Mutua Madrileña (M0083), Mapfre España (C0058) and Mapfre Vida (C0511).

This document records what is in `data/` today, including known gaps and data-quality issues. It is not a completeness claim for the Spanish market.

## Nationale-Nederlanden (C0737)

- Company folder: `nationale_nederlanden_generales_compañia_de_seguros_y_reaseguros_sociedad_anonima_española`
- 8 products, 29 documents, all with `analysis_path` set
- Analyses were produced with Gemini `gemini-2.5-flash-preview-05-20` (January 2026)

Known issues, already baselined in `data/quality/known_data_issues.jsonl`:

- All 8 analyses still use the deprecated `product_branch` field and are missing `metadata.quality_flags`

Likely misassigned branch codes in `index.json` (valid DGS codes, but they do not match the product):

- `salud_completo_autonomos` (`urn:C0737-04`) is coded `00` (life) rather than illness (`02`)
- `seguro_para_negocios` (`urn:C0737-06`) is coded `04` (railway vehicles)
- `seguro_salud_completo` (`urn:C0737-07`) is coded `05` and `06` (aircraft / marine) rather than illness (`02`)

These branch assignments have not been corrected in this change.

## Mutua Madrileña (M0083)

Current state on `main`. This change does not modify Mutua data.

- Company folder: `mutua_madrileña_automovilista_sociedad_de_seguros_a_prima_fija`
- 8 products, 23 document rows, all with `analysis_path` set
- Analyses were produced with Gemini `gemini-2.5-flash-preview-05-20` (February 2026)

Known issues, already baselined in `data/quality/known_data_issues.jsonl` and `data/quality/known_block_page_hashes.jsonl`:

- 19 document rows are legacy Cloudflare block pages (hash `9c2fcc5d899fb2a6196360ee14dfbff58676911c57fda1b59578702c341b0ff4`). They remain in `documents.jsonl` on purpose; they must not be deleted until Data Ops replaces them with real documents. New, unbaselined block-page hashes still fail CI. See [GENERATING_PRODUCT_POOL.md](GENERATING_PRODUCT_POOL.md).
- All 8 analyses still use deprecated `product_branch` and are missing `metadata.quality_flags`
- `decesos_completo` (`urn:M0083-07`) uses invalid branch code `21` (not in `data/insurance_branches.jsonl`) in both `index.json` and the analysis file

Likely misassigned branch codes in `index.json` (valid DGS codes, but they do not match the product):

- `moto_terceros_plus` (`urn:M0083-02`) is coded `06` (marine) rather than land vehicles (`03`)
- `salud_enfermedad` (`urn:M0083-04`) is coded `05` (aircraft) rather than illness (`02`)
- `ahorro_garantia` (`urn:M0083-08`) is coded `13` (general liability) rather than life (`00`)

These assignments have not been corrected in this change. Mutua documents were not re-fetched (the public site is still behind Imperva).

## Mapfre España (C0058) and Mapfre Vida (C0511)

First batch, fetched on 26 November 2026 from the public [documentación precontractual](https://www.mapfre.es/documentacion-precontractual/) portal (Mapfre España = entidad `001`, Mapfre Vida = entidad `003`).

| Company | Products | Unique source docs | Fetched | Analyses |
|---------|----------|--------------------|---------|----------|
| Mapfre España (C0058) | 11 | 30 | 29 | 10 of 11 |
| Mapfre Vida (C0511) | 6 | 11 | 11 | 6 of 6 |
| **Total** | **17** | **41** | **40** | **16 of 17** |

The 16 analyses were produced on 27 November 2026 with `--provider mistral` and `MISTRAL_MODEL=mistral-small-latest`. Gemini (`gemini-3.8-flash`) was the intended primary, but it returned `503 UNAVAILABLE` (high demand) on repeated test calls, so the batch used Mistral Small. Each analysis records provider and model under `metadata.analysis_provenance`.

Branch codes for this batch look consistent with the products (life `00`, accidents `01`, illness `02`, motor `03`+`10`, household `08`+`09`, death `19`).

### Fetch and processing gaps

- **Moto general conditions, `source_error`.** Docprecon document `0900ab44c3920abc` (`moto_cg_0900ab44c3920abc`, listed as the motorcycle CG and shared by `seguro_moto_terceros_ampliado`) was not retrieved. The portal returned a body of `Error` rather than a PDF. This is recorded in the C0058 source manifest and in `data/runs.jsonl`. The motorcycle analysis therefore ran on the IPID and prior note only. The pipeline did not set `incomplete_inputs` because the missing file never reached the analysis stage.
- **PIAS KID broken text layer.** `pias_ahorro_inversion_kid_0900ab44c361ea6c` is a real 3-page PDF (~2.8 MB) whose extracted markdown is unusable (`(cid:…)` glyphs, 118 characters). The prior note (`pias_ahorro_inversion_nota_0900ab44c69164db`) is usable and was the main analysis input. The KID was still passed to the model; its `extraction_confidence` in `source_documents` is `0.5`. Official length validation still accepted the markdown (threshold is 100 characters).

### Analysis gap

- **`seguro_hogar_familiar` (`urn:C0058-06`)** has no analysis file and `analysis_path` is `null`. A first-pass Mistral `429` rate limit was retried once, after a cooldown; the retry also returned `429`. No second retry pass was run. Source documents for this product were fetched and converted successfully.

### Spot-check notes (Mistral Small)

Three analyses were reviewed against their source markdown:

- **`seguro_v80`** (C0511, prior note only). Coherent term-life product: one coverage (death from any cause), standard exclusions, annual tacit renewal until age 57. Minor extraction nits: `administrative_code` is `C-0000` (should be C0511 / C-0511), and `cancellation_notice_days_*` looks like notice periods in months stored in a days field.
- **`seguro_terceros`** (C0058, shared car CG + IPID + note). The IPID states that damage to the insured vehicle is not covered except for optional guarantees. The analysis nevertheless lists own-vehicle damage, theft, fire, glass, atmospheric phenomena and substitute vehicle among the 17 coverages — almost the same list as `seguro_terceros_ampliado` and `seguro_todo_riesgo`. Those products share `coche_cg_0900ab44c391e066`; the model appears to have promoted CG modules to included coverages. Treat the motor analyses as a first pass, not as a faithful product-to-product comparison.
- **`pias_ahorro_inversion`** (C0511). Survival and death coverages, single-premium PIAS with extraordinary contributions, no partial surrenders, and tax/mobilisation rules match the prior note. Some contractual features (for example “no partial surrenders”) are listed under `exclusions`. The broken KID did not obviously contaminate the summary, which is grounded in the note.

These quality observations are not recorded as `has_known_quality_issues` in the analysis files (the analyser left that flag `false`).
