# Fetching Insurance Data from DGSFP

This document describes how the project fetches regulatory data from the Spanish DGSFP/Mineco registry.

## Data Types

| Data | Source | Project Usage |
|------|--------|---------------|
| Insurance companies | `GetAseguradorasBusqueda` | `insurance_companies.json` |
| Company details | `GetAseguradora` | Company `insurance_branches` |
| Distributors | `GetMediadoresBusqueda` | `insurance_distributors.json` |

**Note**: DGSFP provides **regulatory authorization data** (which lines of business a company can sell), not commercial product catalogs.

## API Endpoints

| Endpoint | Method | Returns |
|----------|--------|---------|
| `/Aseguradora/GetAseguradorasBusqueda` | POST | List of insurers |
| `/Aseguradora/GetAseguradora/?clave=XXX` | GET | Company detail page (HTML) |
| `/MEDIADOR/GetMediadoresBusqueda` | POST | List of distributors |

Base URL: `https://rrpp.dgsfp.mineco.es/`

## Implementation

The project uses these functions in `scripts/fetchers/`:

```python
# Get all companies
companies = get_insurance_companies()

# Enrich with details (insurance_branches, executives, etc.)
enriched = enrich_insurance_companies(companies)

# Get all distributors  
distributors = get_insurance_distributors()
```

## insurance_branches

Each company's `insurance_branches` contains their authorized lines of business:

```json
{
  "codigo": "01",
  "ramo": "1/Accidentes",
  "modalidad": "(Ramo Completo)",
  "estado": "Activo"
}
```

## References

- [rrpp.dgsfp.mineco.es](https://rrpp.dgsfp.mineco.es/?culture=es-ES&ui-culture=es-ES)
- [DGSFP](https://dgsfp.mineco.gob.es/)
