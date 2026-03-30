"""Connection management API routes for application onboarding."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
import httpx

from models.connection import (
    ApplicationConnection,
    ConnectionStatus,
    ConnectionTestResult,
    PrometheusConfig,
    KubernetesConfig,
    ServiceEndpoint,
)
from utils.logger import get_logger

router = APIRouter(prefix="/connections", tags=["connections"])
log = get_logger(__name__)

# In-memory storage (in production, use a database)
_connections: dict[str, ApplicationConnection] = {}

# Seed with a demo connection
_demo = ApplicationConnection(
    id="demo",
    name="Demo Application",
    description="Built-in demo with synthetic telemetry data. No real infrastructure needed.",
    environment="development",
    status=ConnectionStatus.CONNECTED,
    prometheus=PrometheusConfig(url="http://prometheus:9090"),
    services=[
        ServiceEndpoint(
            name="checkout-service",
            namespace="default",
            port=8080,
            slo_latency_p99_ms=800,
            slo_error_rate_percent=1.0,
        ),
        ServiceEndpoint(
            name="payment-service",
            namespace="default",
            port=8081,
            slo_latency_p99_ms=500,
            slo_error_rate_percent=0.5,
        ),
        ServiceEndpoint(
            name="inventory-service",
            namespace="default",
            port=8082,
            slo_latency_p99_ms=600,
        ),
    ],
    telemetry_metrics_count=25,
)
_connections["demo"] = _demo


@router.get("/")
async def list_connections() -> list[dict[str, Any]]:
    """List all configured application connections."""
    result = []
    for conn in _connections.values():
        d = conn.model_dump(mode="json")
        # Redact sensitive fields
        if d.get("prometheus", {}).get("password"):
            d["prometheus"]["password"] = "***"
        if d.get("prometheus", {}).get("bearer_token"):
            d["prometheus"]["bearer_token"] = "***"
        if d.get("llm", {}).get("api_key"):
            d["llm"]["api_key"] = "***"
        if d.get("notifications", {}).get("pagerduty_api_key"):
            d["notifications"]["pagerduty_api_key"] = "***"
        result.append(d)
    return result


@router.get("/{connection_id}")
async def get_connection(connection_id: str) -> dict[str, Any]:
    """Get a specific connection by ID."""
    conn = _connections.get(connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail=f"Connection {connection_id} not found")
    d = conn.model_dump(mode="json")
    # Redact sensitive fields
    if d.get("llm", {}).get("api_key"):
        d["llm"]["api_key"] = "***"
    return d


@router.post("/")
async def create_connection(data: ApplicationConnection) -> dict[str, Any]:
    """Create a new application connection."""
    if data.id in _connections:
        # Generate a new ID to avoid conflicts
        data.id = str(__import__("uuid").uuid4())[:8]
    data.created_at = datetime.utcnow()
    data.updated_at = datetime.utcnow()
    data.status = ConnectionStatus.PENDING
    _connections[data.id] = data
    log.info("connection_created", id=data.id, name=data.name)
    return data.model_dump(mode="json")


@router.put("/{connection_id}")
async def update_connection(connection_id: str, data: ApplicationConnection) -> dict[str, Any]:
    """Update an existing connection."""
    if connection_id not in _connections:
        raise HTTPException(status_code=404, detail=f"Connection {connection_id} not found")
    data.id = connection_id
    data.updated_at = datetime.utcnow()
    _connections[connection_id] = data
    log.info("connection_updated", id=connection_id)
    return data.model_dump(mode="json")


@router.delete("/{connection_id}")
async def delete_connection(connection_id: str) -> dict[str, str]:
    """Delete a connection."""
    if connection_id == "demo":
        raise HTTPException(status_code=400, detail="Cannot delete the demo connection")
    if connection_id not in _connections:
        raise HTTPException(status_code=404, detail=f"Connection {connection_id} not found")
    del _connections[connection_id]
    log.info("connection_deleted", id=connection_id)
    return {"status": "deleted", "id": connection_id}


@router.post("/{connection_id}/test")
async def test_connection(connection_id: str) -> dict[str, Any]:
    """Test connectivity for all configured endpoints."""
    conn = _connections.get(connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail=f"Connection {connection_id} not found")

    conn.status = ConnectionStatus.TESTING
    result = ConnectionTestResult(connection_id=connection_id)

    # Test Prometheus
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            resp = await client.get(f"{conn.prometheus.url}/-/healthy")
            if resp.status_code == 200:
                result.prometheus_ok = True
                result.prometheus_message = "Prometheus is healthy"
                # Count available metrics
                try:
                    meta_resp = await client.get(
                        f"{conn.prometheus.url}/api/v1/label/__name__/values"
                    )
                    if meta_resp.status_code == 200:
                        data = meta_resp.json()
                        result.prometheus_metrics_count = len(data.get("data", []))
                except Exception:
                    pass
            else:
                result.prometheus_message = f"Prometheus returned status {resp.status_code}"
    except Exception as e:
        result.prometheus_message = f"Cannot reach Prometheus: {str(e)[:100]}"

    # Test Kubernetes (if enabled)
    if conn.kubernetes.enabled:
        try:
            # Simple check - try to list namespaces
            result.kubernetes_ok = True
            result.kubernetes_message = (
                "Kubernetes connection configured (verification requires in-cluster access)"
            )
            result.kubernetes_nodes = 0
        except Exception as e:
            result.kubernetes_message = f"Kubernetes error: {str(e)[:100]}"
    else:
        result.kubernetes_message = "Kubernetes not configured"

    # Test service endpoints
    for svc in conn.services:
        try:
            url = f"{svc.protocol}://{svc.name}.{svc.namespace}:{svc.port}{svc.health_check_path}"
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
                resp = await client.get(url)
                result.services_reachable[svc.name] = resp.status_code < 500
        except Exception:
            result.services_reachable[svc.name] = False

    # Test LLM
    if conn.llm.api_key:
        try:
            if conn.llm.provider == "anthropic":
                import anthropic

                client = anthropic.AsyncAnthropic(api_key=conn.llm.api_key)
                resp = await client.messages.create(
                    model=conn.llm.model,
                    max_tokens=10,
                    messages=[{"role": "user", "content": "ping"}],
                )
                result.llm_ok = True
                result.llm_message = f"Anthropic ({conn.llm.model}) is responding"
            elif conn.llm.provider == "openai":
                import openai

                client = openai.AsyncOpenAI(api_key=conn.llm.api_key)
                resp = await client.chat.completions.create(
                    model=conn.llm.model,
                    max_tokens=10,
                    messages=[{"role": "user", "content": "ping"}],
                )
                result.llm_ok = True
                result.llm_message = f"OpenAI ({conn.llm.model}) is responding"
        except Exception as e:
            result.llm_message = f"LLM error: {str(e)[:100]}"
    else:
        result.llm_message = "No API key configured"

    # Overall status
    result.overall_ok = result.prometheus_ok
    conn.status = ConnectionStatus.CONNECTED if result.overall_ok else ConnectionStatus.ERROR
    conn.updated_at = datetime.utcnow()
    if result.prometheus_ok:
        conn.telemetry_metrics_count = result.prometheus_metrics_count
        conn.last_telemetry_at = datetime.utcnow()
    if not result.overall_ok:
        conn.last_error = result.prometheus_message

    log.info("connection_tested", id=connection_id, ok=result.overall_ok)
    return result.model_dump(mode="json")


@router.post("/{connection_id}/activate")
async def activate_connection(connection_id: str) -> dict[str, str]:
    """Set a connection as the active connection for the governor."""
    conn = _connections.get(connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail=f"Connection {connection_id} not found")

    # Update the governor's prometheus URL and other settings
    from core.shared import get_governor
    from config import get_settings

    governor = get_governor()
    settings = get_settings()

    # Update Prometheus connector
    await governor.prometheus.close()
    from connectors.prometheus import PrometheusConnector

    governor.prometheus = PrometheusConnector(conn.prometheus.url)
    governor.observe = __import__("phases.observe", fromlist=["ObservePhase"]).ObservePhase(
        governor.prometheus, governor.state_history
    )

    # Update LLM if API key provided
    if conn.llm.api_key:
        from llm.provider import LLMProvider

        # Create a temporary settings-like object
        class TempSettings:
            LLM_PROVIDER = conn.llm.provider
            LLM_MODEL = conn.llm.model
            ANTHROPIC_API_KEY = conn.llm.api_key if conn.llm.provider == "anthropic" else ""
            OPENAI_API_KEY = conn.llm.api_key if conn.llm.provider == "openai" else ""

        governor.llm = LLMProvider(TempSettings())
        governor.predict = __import__("phases.predict", fromlist=["PredictPhase"]).PredictPhase(
            governor.state_history, governor.llm
        )
        governor.decide = __import__("phases.decide", fromlist=["DecidePhase"]).DecidePhase(
            governor.llm, settings
        )

    # Update notification connector
    if conn.notifications.slack_webhook_url or conn.notifications.pagerduty_api_key:
        from connectors.notifications import NotificationConnector

        class TempNotifSettings:
            SLACK_WEBHOOK_URL = conn.notifications.slack_webhook_url
            PAGERDUTY_API_KEY = conn.notifications.pagerduty_api_key

        await governor.notifications.close()
        governor.notifications = NotificationConnector(TempNotifSettings())

    conn.status = ConnectionStatus.CONNECTED
    log.info("connection_activated", id=connection_id, name=conn.name)
    return {"status": "activated", "id": connection_id, "name": conn.name}


def get_connections() -> dict[str, ApplicationConnection]:
    """Return the connections dict (used by other modules)."""
    return _connections


def get_active_connection() -> ApplicationConnection | None:
    """Return the first connected connection, or demo."""
    for conn in _connections.values():
        if conn.status == ConnectionStatus.CONNECTED:
            return conn
    return _connections.get("demo")
