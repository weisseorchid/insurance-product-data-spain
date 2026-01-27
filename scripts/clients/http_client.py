"""Centralized HTTP client with retry logic and connection pooling."""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from insurance_product_data_spain.core.logging import logger
from scripts.config import DEFAULT_TIMEOUT, MAX_RETRIES


class HTTPClient:
    """Centralized HTTP client with retry logic and connection pooling."""

    def __init__(self, timeout: int = DEFAULT_TIMEOUT, max_retries: int = MAX_RETRIES):
        self.timeout = timeout
        self.session = requests.Session()

        # Configure retry strategy
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=0.3,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=20)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def get(self, url: str, **kwargs) -> requests.Response:
        """GET request with error handling."""
        kwargs.setdefault("timeout", self.timeout)
        try:
            response = self.session.get(url, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            logger.error(f"HTTP GET failed for {url}: {e}")
            raise

    def post(self, url: str, **kwargs) -> requests.Response:
        """POST request with error handling."""
        kwargs.setdefault("timeout", self.timeout)
        try:
            response = self.session.post(url, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            logger.error(f"HTTP POST failed for {url}: {e}")
            raise


_http_client: HTTPClient | None = None


def get_http_client() -> HTTPClient:
    """Get or create the global HTTP client instance."""
    global _http_client
    if _http_client is None:
        _http_client = HTTPClient()
    return _http_client
