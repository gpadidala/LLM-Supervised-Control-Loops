"""Pydantic models for application connections and onboarding."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

import uuid


class ConnectionStatus(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    TESTING = "testing"
    PENDING = "pending"


class PrometheusConfig(BaseModel):
    """Prometheus connection configuration."""

    url: str = "http://localhost:9090"
    username: str = ""
    password: str = ""
    bearer_token: str = ""
    tls_skip_verify: bool = False
    custom_headers: dict[str, str] = {}


class KubernetesConfig(BaseModel):
    """Kubernetes cluster connection configuration."""

    enabled: bool = False
    cluster_name: str = ""
    kubeconfig_path: str = ""
    in_cluster: bool = False
    namespace: str = "default"
    context: str = ""


class ServiceEndpoint(BaseModel):
    """A service/application endpoint to monitor."""

    name: str
    namespace: str = "default"
    port: int = 80
    protocol: str = "http"
    health_check_path: str = "/health"
    metrics_path: str = "/metrics"
    slo_latency_p99_ms: float = 800.0
    slo_error_rate_percent: float = 1.0
    slo_availability_percent: float = 99.9
    labels: dict[str, str] = {}


class NotificationConfig(BaseModel):
    """Notification channel configuration."""

    slack_webhook_url: str = ""
    slack_channel: str = "#scl-governor"
    pagerduty_api_key: str = ""
    pagerduty_service_id: str = ""
    opsgenie_api_key: str = ""
    email_recipients: list[str] = []


class LLMConfig(BaseModel):
    """LLM provider configuration for this connection."""

    provider: str = "anthropic"  # anthropic, openai
    model: str = "claude-sonnet-4-20250514"
    api_key: str = ""
    temperature: float = 0.1
    max_tokens: int = 2048


class ApplicationConnection(BaseModel):
    """Complete connection profile for an onboarded application."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str
    description: str = ""
    environment: str = "production"  # production, staging, development
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    status: ConnectionStatus = ConnectionStatus.PENDING

    # Connection configs
    prometheus: PrometheusConfig = Field(default_factory=PrometheusConfig)
    kubernetes: KubernetesConfig = Field(default_factory=KubernetesConfig)
    services: list[ServiceEndpoint] = []
    notifications: NotificationConfig = Field(default_factory=NotificationConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)

    # Control loop settings for this connection
    cycle_interval_seconds: int = 15
    simulation_scenarios: int = 100
    auto_start: bool = False

    # Health/status
    last_telemetry_at: datetime | None = None
    last_error: str | None = None
    telemetry_metrics_count: int = 0


class ConnectionTestResult(BaseModel):
    """Result of testing a connection."""

    connection_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    prometheus_ok: bool = False
    prometheus_message: str = ""
    prometheus_metrics_count: int = 0
    kubernetes_ok: bool = False
    kubernetes_message: str = ""
    kubernetes_nodes: int = 0
    services_reachable: dict[str, bool] = {}
    llm_ok: bool = False
    llm_message: str = ""
    overall_ok: bool = False
