# Architecture Review & Improvement Suggestions

## Current Architecture Analysis

### Strengths
- ✅ Clear separation of concerns (api, utils, constants)
- ✅ Type hints present (though using `dict[str, Any]` everywhere)
- ✅ Pydantic already in dependencies (not yet utilized)
- ✅ Good project structure with versioning

### Critical Issues

1. **No Data Access Abstraction**
   - Direct file I/O scattered across modules
   - Hardcoded file paths (`"data/insurance_companies.json"`)
   - No centralized data management

2. **No Data Validation**
   - Using `dict[str, Any]` everywhere
   - No schema validation
   - Risk of data corruption/inconsistency

3. **No Configuration Management**
   - Hardcoded URLs, delays, paths
   - Difficult to test or customize

4. **No Logging System**
   - Using `print()` statements
   - No log levels or structured logging

5. **Inconsistent Public API**
   - Some functions in `__init__.py`, others require deep imports
   - Inconsistent naming and patterns

6. **No Data Versioning/Metadata**
   - No way to track data freshness
   - No metadata about data collection

7. **Limited Error Handling**
   - Basic try/except but no structured error handling
   - No custom exceptions

## Minimal Changes for Robustness & Scalability

### 1. Data Access Layer (Repository Pattern)

**Create**: `src/insurance_data_spain/storage/repository.py`

Centralize all file operations in a simple repository class:

```python
from pathlib import Path
from typing import Any
import json
from datetime import datetime

class DataRepository:
    """Centralized data storage and retrieval."""
    
    def __init__(self, data_dir: Path | str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def save_companies(self, companies: list[dict[str, Any]], metadata: dict[str, Any] | None = None) -> Path:
        """Save companies with metadata."""
        data = {
            "metadata": {
                "version": "1.0",
                "collected_at": datetime.now().isoformat(),
                "count": len(companies),
                **(metadata or {})
            },
            "data": companies
        }
        file_path = self.data_dir / "insurance_companies.json"
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return file_path
    
    def load_companies(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Load companies and metadata."""
        file_path = self.data_dir / "insurance_companies.json"
        if not file_path.exists():
            return [], {}
        with open(file_path, encoding='utf-8') as f:
            data = json.load(f)
        return data.get("data", []), data.get("metadata", {})
```

**Benefits**:
- Single source of truth for data operations
- Easy to add caching, validation, or change storage backend
- Consistent error handling

### 2. Basic Data Models (Pydantic)

**Create**: `src/insurance_data_spain/models/__init__.py` and `company.py`

Use Pydantic for validation (already in dependencies):

```python
from pydantic import BaseModel, Field
from typing import Optional

class InsuranceCompany(BaseModel):
    """Insurance company data model."""
    company_key: str = Field(..., alias="clave")
    denomination: Optional[str] = None
    nif: Optional[str] = None
    status: Optional[str] = None
    # ... other fields with defaults
    
    class Config:
        populate_by_name = True  # Allow both alias and field name
```

**Benefits**:
- Type safety and validation
- Clear data contracts
- Auto-generated documentation
- Prevents data corruption

### 3. Configuration Management

**Create**: `src/insurance_data_spain/config.py`

```python
from pathlib import Path
from dataclasses import dataclass

@dataclass
class Config:
    """Application configuration."""
    data_dir: Path = Path("data")
    base_url: str = "https://rrpp.dgsfp.mineco.es/"
    request_delay: float = 0.1
    timeout: int = 30
    
    @classmethod
    def from_env(cls) -> "Config":
        """Load from environment variables if needed."""
        return cls()  # Can be extended later
```

**Benefits**:
- Centralized configuration
- Easy to test with different configs
- Can extend to environment variables later

### 4. Logging System

**Create**: `src/insurance_data_spain/utils/logger.py`

```python
import logging
import sys

def setup_logger(name: str = "insurance_data_spain", level: int = logging.INFO) -> logging.Logger:
    """Setup structured logger."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger
```

**Replace all `print()` with `logger.info()`**

**Benefits**:
- Proper log levels
- Can redirect to files
- Better debugging

### 5. Standardize Public API

**Update**: `src/insurance_data_spain/__init__.py`

```python
# High-level API
from .api.v1.get_insurance_companies import get_insurance_companies, get_insurance_company_details
from .api.v1.get_insurance_distributors import get_insurance_distributors, get_insurance_distributor_details
from .api.v1.sync_insurco_data_folders import sync_insurance_company_folders

# Data access
from .storage.repository import DataRepository

# Configuration
from .config import Config

__all__ = [
    "get_insurance_companies",
    "get_insurance_company_details", 
    "get_insurance_distributors",
    "get_insurance_distributor_details",
    "sync_insurance_company_folders",
    "DataRepository",
    "Config",
    "__version__",
]
```

**Benefits**:
- Consistent import paths
- Clear public API
- Easier for users

### 6. Custom Exceptions

**Create**: `src/insurance_data_spain/exceptions.py`

```python
class InsuranceDataError(Exception):
    """Base exception for insurance data operations."""
    pass

class DataNotFoundError(InsuranceDataError):
    """Raised when requested data is not found."""
    pass

class APIError(InsuranceDataError):
    """Raised when API requests fail."""
    pass
```

**Benefits**:
- Better error handling
- Users can catch specific exceptions
- Clearer error messages

### 7. Data Versioning Metadata

Already addressed in #1 (DataRepository), but ensure all data saves include:
- Collection timestamp
- Data version
- Source URL
- Record count

## Implementation Priority

### Phase 1: Critical (Do First)
1. ✅ **Data Repository** - Centralize file operations
2. ✅ **Logging** - Replace print statements
3. ✅ **Configuration** - Centralize config

### Phase 2: Important (Do Next)
4. ✅ **Public API** - Standardize exports
5. ✅ **Custom Exceptions** - Better error handling

### Phase 3: Nice to Have (Can Defer)
6. ✅ **Pydantic Models** - Add gradually, start with core models
7. ✅ **Data Versioning** - Already in repository pattern

## Migration Strategy

1. **Non-breaking**: Add new modules alongside existing code
2. **Gradual**: Update one module at a time
3. **Backward compatible**: Keep old functions working, add new ones
4. **Test**: Ensure existing functionality still works

## File Structure After Changes

```
src/insurance_data_spain/
├── __init__.py              # Updated with standardized exports
├── config.py                # NEW: Configuration
├── exceptions.py            # NEW: Custom exceptions
├── api/
│   └── v1/
│       ├── get_insurance_companies.py      # Updated: Use logger, config, repository
│       ├── get_insurance_distributors.py   # Updated: Use logger, config, repository
│       └── sync_insurco_data_folders.py   # Updated: Use logger, config, repository
├── storage/                 # NEW: Data access layer
│   ├── __init__.py
│   └── repository.py
├── models/                  # NEW: Data models (optional, can add gradually)
│   ├── __init__.py
│   └── company.py
├── constants/
│   ├── api_headers.py
│   └── public_urls.py
└── utils/
    ├── __init__.py
    ├── data_extraction.py
    ├── text_transformations.py
    └── logger.py            # NEW: Logging setup
```

## Benefits Summary

✅ **Maintainability**: Centralized code, easier to modify
✅ **Testability**: Can mock repository, config, logger
✅ **Scalability**: Easy to add new data sources or storage backends
✅ **Reliability**: Validation, error handling, logging
✅ **User Experience**: Consistent API, better error messages
✅ **Simplicity**: Minimal changes, backward compatible

## Next Steps

1. Review this document
2. Implement Phase 1 changes
3. Test thoroughly
4. Gradually migrate existing code
5. Add Phase 2 & 3 as needed

