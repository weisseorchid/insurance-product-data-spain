# Fetching Insurance Products per Company (Mineco-Style)

This document summarizes how to fetch **insurance product–like data per insurance company** in an automated or semi-automated way, following the same approach as the DGSFP/Mineco registries (`rrpp.dgsfp.mineco.es`).

---

## 1. What “Insurance Products” Means Here

In the **regulatory (DGSFP) sense**, “products” = **authorized lines of business** (**Ramos** and **Modalidades**) per insurer: what each company is allowed to sell (e.g. Vida, No Vida, Accidentes, Responsabilidad civil general, Defensa jurídica, etc.).  
This is **not** a catalog of individual commercial products (e.g. “Mapfre Hogar Plus”); DGSFP does not publish that. EIOPA’s IDD/IPID framework obliges manufacturers to provide IPIDs, but there is no public “all products per company” registry or API.

---

## 2. Mineco Approach (Already Implemented)

The project already uses the **rrpp.dgsfp.mineco.es** backend in the same way as the portal:

| Endpoint | Method | Returns | Usage in project |
|----------|--------|---------|------------------|
| `/Aseguradora/GetAseguradorasBusqueda` | POST | JSON list of insurers | `get_insurance_companies()` |
| `/Aseguradora/GetAseguradora/?clave=XXX` | GET | HTML detail page | `get_insurance_company_details()` |
| `/MEDIADOR/GetMediadoresBusqueda` | POST | JSON list of distributors | `get_insurance_distributors()` |

- **Base URL**: `https://rrpp.dgsfp.mineco.es/`
- **Culture**: `?culture=es-ES&ui-culture=es-ES`
- **Headers**: `mineco_headers` / `mineco_html_headers` (see `api_headers.py`)

---

## 3. “Products” per Company = `insurance_branches`

**Products per company** (in the regulatory sense) = the **Ramos/Modalidades** each insurer is authorized for.

These come from the **detail page** of each company:

- **Source**: `GetAseguradora` HTML → JavaScript `loadGridModalidades`
- **In the project**: `get_insurance_company_details(company_key)` → `details['insurance_branches']`
- **Schema**: `InsuranceCompanyDetails.insurance_branches` (list of `{codigo, ramo, modalidad, fechaAlta, estado, ...}`)

Your enriched `insurance_companies.json` already includes `insurance_branches` per company. No extra “product” API is required for this.

**Example** (from `data/insurance_companies.json`):

```json
"insurance_branches": [
  { "codigo": "01", "ramo": "1/Accidentes", "modalidad": "(Ramo Completo)", "estado": "Activo", ... },
  { "codigo": "13", "ramo": "13/Responsabilidad civil general", "modalidad": "(Ramo Completo)", ... }
]
```

---

## 4. Automated Fetch Options (Mineco-Style)

### A. Products per company (already in place)

1. **Search insurers**: `get_insurance_companies()` → list of companies (with `clave`).
2. **Enrich each**: `get_insurance_company_details(clave)` or `enrich_insurance_companies(companies)`.
3. **Use** `insurance_branches` as “products” (Ramos/Modalidades) per company.

Same pattern as Mineco: POST search → GET detail per entity.

### B. Insurers per product line (inverse mapping)

Use **`GetAseguradorasBusqueda`** with product-line filters to get “insurers that sell product X”:

- **By Tipo de actividad**: `TipoActividadSeleccionada` = `Vida`, `No Vida`, `Vida + No Vida`, etc., and `OpcionBusqueda` = `actividad`.
- **By Ramo/Modalidad**: `OpcionBusqueda` = `ramos`, `Ramo` = e.g. `13` (Responsabilidad civil general), and optionally `Modalidades`, `Prestacion`.

Example (conceptual):

```python
# Insurers authorized for "Responsabilidad civil general" (Ramo 13)
get_insurance_companies(search_params={
    "OpcionBusqueda": "ramos",
    "Ramo": "13",
    "Modalidades": "",
    "Situacion": "1",
})
```

Ramos/Modalidades values align with the rrpp form and Ayuda (e.g. Enfermedad, RC automóviles, Defensa jurídica). `get_insurance_companies` already accepts `search_params` and forwards them to the API.

### C. Other rrpp endpoints observed

- **`/Aseguradora/GetServceModalidades`** (POST): used by the portal for modalidades dropdowns (product-line metadata). Could be used to resolve Ramo/Modalidad options programmatically.
- **`/Aseguradora/Ayuda`** (GET): help text; describes Ramos, Modalidades, Prestaciones, etc. No API, but useful for reference.

---

## 5. Semi-Automated Options

### Exportar a Excel / PDF (rrpp portal)

- **Where**: Results page after “Buscar” on rrpp (Aseguradoras).
- **What**: “Exportar a Excel” and “Exportar a PDF” export the **current grid** (same data as `GetAseguradorasBusqueda`).
- **How**: Implemented via client-side JS (`excel.site.min.js`, `pdf.site.min.js`). There is **no dedicated REST export API**; the backend call used is still `GetAseguradorasBusqueda`.
- **Semi-automation**: Use a browser (e.g. Playwright) to run search → Exportar a Excel. Alternatively, keep using `get_insurance_companies()` (and detail calls) for full automation.

### Datos.gob.es

- **Catalog API**: e.g. `https://datos.gob.es/apidata/catalog/dataset?q=seguros&_pageSize=20&_page=1` (JSON).
- **Use case**: Discover datasets tagged “Seguros y servicios financieros” or DGSFP-related. Some contain **aggregate** DGSFP statistics (e.g. Memoria Estadística Anual), **not** product-level or per-company ramos/modalidades.
- **Reuse**: For any catalog hit, use the dataset’s distribution URL (CSV/JSON/etc.) for automated fetch. This complements, but does not replace, rrpp for “products per company”.

---

## 6. What Exists vs What Doesn’t

| Data | Available via Mineco-style API? | Where |
|------|---------------------------------|-------|
| Insurers list | ✅ Yes | `GetAseguradorasBusqueda` |
| Insurer details | ✅ Yes | `GetAseguradora` |
| **Products (Ramos/Modalidades) per company** | ✅ Yes | `GetAseguradora` → `insurance_branches` |
| Insurers per product line | ✅ Yes | `GetAseguradorasBusqueda` with Ramo/Modalidad/TipoActividad |
| Distributors | ✅ Yes | `GetMediadoresBusqueda` |
| Individual product catalog (IPID, policy names) | ❌ No | Not published by DGSFP/EIOPA |
| Bulk Excel/PDF export API | ❌ No | Only client-side export on rrpp |

---

## 7. Practical Recommendation

- **Fully automated, Mineco-style**:  
  Use **`get_insurance_companies`** + **`get_insurance_company_details`** (or **`enrich_insurance_companies`**). **`insurance_branches`** = products (Ramos/Modalidades) per company. Already implemented.

- **“Insurers per product”**:  
  Call **`get_insurance_companies(search_params={...})`** with **`OpcionBusqueda`**, **`Ramo`**, **`Modalidades`**, **`TipoActividadSeleccionada`** as needed. Same Mineco API.

- **Semi-automated**:  
  Browser automation for “Exportar a Excel” on rrpp, and/or **Datos.gob.es** API to discover and fetch relevant **seguros** datasets (e.g. statistics). Neither replaces rrpp for product-by-company data.

---

## 8. References

- **rrpp portal**: [https://rrpp.dgsfp.mineco.es/](https://rrpp.dgsfp.mineco.es/?culture=es-ES&ui-culture=es-ES)
- **Ayuda (Ramos, Modalidades, etc.)**: [https://rrpp.dgsfp.mineco.es/Aseguradora/Ayuda](https://rrpp.dgsfp.mineco.es/Aseguradora/Ayuda)
- **Datos.gob.es API**: [https://datos.gob.es/es/apidata](https://datos.gob.es/es/apidata)
- **DGSFP**: [https://dgsfp.mineco.gob.es/](https://dgsfp.mineco.gob.es/)
