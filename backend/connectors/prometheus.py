"""Async Prometheus query client for SCL-Governor observe phase."""

from __future__ import annotations

from typing import Any

import httpx

from utils.logger import get_logger

log = get_logger(__name__)


class PrometheusConnector:
    """Async Prometheus query client.

    Gracefully degrades when Prometheus is unreachable -- all query methods
    return empty results rather than raising, so the control loop can continue
    with whatever data is available.
    """

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Lazily create the async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(10.0, connect=5.0),
            )
        return self._client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def query(self, promql: str) -> list[dict[str, Any]]:
        """Execute an instant PromQL query.

        Returns a list of ``{"metric": dict, "value": [timestamp, value]}``
        dicts.  Returns an empty list on any error.
        """
        try:
            client = await self._ensure_client()
            resp = await client.get("/api/v1/query", params={"query": promql})
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("status") != "success":
                log.warning(
                    "prometheus_query_error",
                    promql=promql,
                    error=payload.get("error", "unknown"),
                )
                return []
            return payload.get("data", {}).get("result", [])
        except httpx.HTTPError as exc:
            log.warning("prometheus_query_failed", promql=promql, error=str(exc))
            return []
        except Exception as exc:
            log.error("prometheus_query_unexpected", promql=promql, error=str(exc))
            return []

    async def query_range(
        self,
        promql: str,
        start: float,
        end: float,
        step: str = "15s",
    ) -> list[dict[str, Any]]:
        """Execute a range PromQL query.

        Returns a list of ``{"metric": dict, "values": [[ts, val], ...]}``
        dicts.  Returns an empty list on any error.
        """
        try:
            client = await self._ensure_client()
            resp = await client.get(
                "/api/v1/query_range",
                params={
                    "query": promql,
                    "start": start,
                    "end": end,
                    "step": step,
                },
            )
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("status") != "success":
                log.warning(
                    "prometheus_range_query_error",
                    promql=promql,
                    error=payload.get("error", "unknown"),
                )
                return []
            return payload.get("data", {}).get("result", [])
        except httpx.HTTPError as exc:
            log.warning("prometheus_range_query_failed", promql=promql, error=str(exc))
            return []
        except Exception as exc:
            log.error("prometheus_range_query_unexpected", promql=promql, error=str(exc))
            return []

    async def check_health(self) -> bool:
        """Return ``True`` if Prometheus is reachable."""
        try:
            client = await self._ensure_client()
            resp = await client.get("/-/healthy")
            return resp.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
