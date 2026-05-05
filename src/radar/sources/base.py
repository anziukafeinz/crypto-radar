"""Base class shared by every data source adapter."""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


class SourceError(Exception):
    """Raised when a source adapter cannot complete a request."""


class BaseSource:
    """Shared HTTP client with retry, backoff, and structured logging."""

    name: str = "base"
    base_url: str = ""
    default_timeout: float = 15.0

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._owned_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.default_timeout,
            headers={"User-Agent": "crypto-radar/0.1"},
        )

    async def aclose(self) -> None:
        if self._owned_client:
            await self._client.aclose()

    async def __aenter__(self) -> BaseSource:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, SourceError)),
        wait=wait_exponential(multiplier=1, min=1, max=15),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    async def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET ``path`` and return parsed JSON, with retry on transient errors."""
        try:
            response = await self._client.get(path, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "{} HTTP {} on {} params={}",
                self.name,
                exc.response.status_code,
                path,
                params,
            )
            raise SourceError(f"{self.name}: HTTP {exc.response.status_code}") from exc
        return response.json()
