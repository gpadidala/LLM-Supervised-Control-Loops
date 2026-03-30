"""Kubernetes API connector for SCL-Governor actuate phase."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from utils.logger import get_logger

log = get_logger(__name__)


class KubernetesConnector:
    """Kubernetes API client for scaling and configuration operations.

    When the Kubernetes Python client is not available or the cluster is
    unreachable, all methods fall back to **demo mode** -- they log the
    intended operation and return a synthetic success response so the rest
    of the control loop can proceed.
    """

    def __init__(self, settings: Any) -> None:
        self.settings = settings
        self._initialized = False
        self._apps_v1 = None
        self._core_v1 = None
        self._autoscaling_v1 = None
        self._custom_objects = None
        self._demo_mode = True
        self._initialize()

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def _initialize(self) -> None:
        """Try to load the Kubernetes client libraries and configure."""
        try:
            from kubernetes import client, config as k8s_config

            if self.settings.KUBERNETES_IN_CLUSTER:
                k8s_config.load_incluster_config()
            elif self.settings.KUBERNETES_KUBECONFIG:
                k8s_config.load_kube_config(
                    config_file=self.settings.KUBERNETES_KUBECONFIG,
                )
            else:
                k8s_config.load_kube_config()

            self._apps_v1 = client.AppsV1Api()
            self._core_v1 = client.CoreV1Api()
            self._autoscaling_v1 = client.AutoscalingV1Api()
            self._custom_objects = client.CustomObjectsApi()
            self._initialized = True
            self._demo_mode = False
            log.info("kubernetes_connector_initialized")
        except Exception as exc:
            log.warning(
                "kubernetes_connector_demo_mode",
                reason=str(exc),
            )
            self._demo_mode = True

    # ------------------------------------------------------------------
    # Deployment operations
    # ------------------------------------------------------------------

    async def scale_deployment(
        self, name: str, namespace: str, replicas: int
    ) -> dict[str, Any]:
        """Scale a Deployment to the specified number of replicas.

        Returns a dict with ``success``, ``name``, ``namespace``,
        ``replicas``, and ``timestamp`` keys.
        """
        ts = datetime.now(timezone.utc).isoformat()

        if self._demo_mode:
            log.info(
                "k8s_scale_deployment_demo",
                name=name,
                namespace=namespace,
                replicas=replicas,
            )
            return {
                "success": True,
                "demo": True,
                "name": name,
                "namespace": namespace,
                "replicas": replicas,
                "timestamp": ts,
            }

        try:
            body = {"spec": {"replicas": replicas}}
            self._apps_v1.patch_namespaced_deployment_scale(
                name=name,
                namespace=namespace,
                body=body,
            )
            log.info(
                "k8s_scale_deployment",
                name=name,
                namespace=namespace,
                replicas=replicas,
            )
            return {
                "success": True,
                "demo": False,
                "name": name,
                "namespace": namespace,
                "replicas": replicas,
                "timestamp": ts,
            }
        except Exception as exc:
            log.error(
                "k8s_scale_deployment_failed",
                name=name,
                namespace=namespace,
                error=str(exc),
            )
            return {
                "success": False,
                "demo": False,
                "name": name,
                "namespace": namespace,
                "error": str(exc),
                "timestamp": ts,
            }

    async def get_deployment_info(
        self, name: str, namespace: str
    ) -> dict[str, Any]:
        """Retrieve deployment status information."""
        if self._demo_mode:
            return {
                "name": name,
                "namespace": namespace,
                "replicas": 3,
                "available_replicas": 3,
                "ready_replicas": 3,
                "updated_replicas": 3,
                "demo": True,
            }

        try:
            dep = self._apps_v1.read_namespaced_deployment(
                name=name, namespace=namespace
            )
            status = dep.status
            return {
                "name": name,
                "namespace": namespace,
                "replicas": dep.spec.replicas,
                "available_replicas": status.available_replicas or 0,
                "ready_replicas": status.ready_replicas or 0,
                "updated_replicas": status.updated_replicas or 0,
                "demo": False,
            }
        except Exception as exc:
            log.error(
                "k8s_get_deployment_failed",
                name=name,
                namespace=namespace,
                error=str(exc),
            )
            return {"name": name, "namespace": namespace, "error": str(exc)}

    async def patch_hpa(
        self,
        name: str,
        namespace: str,
        min_replicas: int,
        max_replicas: int,
    ) -> dict[str, Any]:
        """Update an HPA's min/max replica bounds."""
        ts = datetime.now(timezone.utc).isoformat()

        if self._demo_mode:
            log.info(
                "k8s_patch_hpa_demo",
                name=name,
                namespace=namespace,
                min_replicas=min_replicas,
                max_replicas=max_replicas,
            )
            return {
                "success": True,
                "demo": True,
                "name": name,
                "namespace": namespace,
                "min_replicas": min_replicas,
                "max_replicas": max_replicas,
                "timestamp": ts,
            }

        try:
            body = {
                "spec": {
                    "minReplicas": min_replicas,
                    "maxReplicas": max_replicas,
                }
            }
            self._autoscaling_v1.patch_namespaced_horizontal_pod_autoscaler(
                name=name,
                namespace=namespace,
                body=body,
            )
            log.info(
                "k8s_patch_hpa",
                name=name,
                namespace=namespace,
                min_replicas=min_replicas,
                max_replicas=max_replicas,
            )
            return {
                "success": True,
                "demo": False,
                "name": name,
                "namespace": namespace,
                "min_replicas": min_replicas,
                "max_replicas": max_replicas,
                "timestamp": ts,
            }
        except Exception as exc:
            log.error("k8s_patch_hpa_failed", name=name, error=str(exc))
            return {"success": False, "error": str(exc), "timestamp": ts}

    async def get_pods(
        self, namespace: str, label_selector: str = ""
    ) -> list[dict[str, Any]]:
        """List pods in a namespace with an optional label selector."""
        if self._demo_mode:
            return [
                {
                    "name": "demo-pod-abc",
                    "namespace": namespace,
                    "status": "Running",
                    "ready": True,
                    "demo": True,
                }
            ]

        try:
            pod_list = self._core_v1.list_namespaced_pod(
                namespace=namespace,
                label_selector=label_selector,
            )
            results: list[dict[str, Any]] = []
            for pod in pod_list.items:
                ready = all(
                    cs.ready
                    for cs in (pod.status.container_statuses or [])
                )
                results.append(
                    {
                        "name": pod.metadata.name,
                        "namespace": pod.metadata.namespace,
                        "status": pod.status.phase,
                        "ready": ready,
                        "demo": False,
                    }
                )
            return results
        except Exception as exc:
            log.error("k8s_get_pods_failed", namespace=namespace, error=str(exc))
            return []

    async def get_node_metrics(self) -> list[dict[str, Any]]:
        """Get node resource utilisation from the metrics-server API.

        Falls back to demo data when unavailable.
        """
        if self._demo_mode:
            return [
                {
                    "name": "demo-node-1",
                    "cpu_usage_cores": 2.5,
                    "memory_usage_bytes": 4_294_967_296,
                    "demo": True,
                }
            ]

        try:
            data = self._custom_objects.list_cluster_custom_object(
                group="metrics.k8s.io",
                version="v1beta1",
                plural="nodes",
            )
            results: list[dict[str, Any]] = []
            for item in data.get("items", []):
                usage = item.get("usage", {})
                results.append(
                    {
                        "name": item["metadata"]["name"],
                        "cpu_usage_cores": _parse_cpu(usage.get("cpu", "0")),
                        "memory_usage_bytes": _parse_memory(
                            usage.get("memory", "0")
                        ),
                        "demo": False,
                    }
                )
            return results
        except Exception as exc:
            log.error("k8s_node_metrics_failed", error=str(exc))
            return []


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _parse_cpu(value: str) -> float:
    """Convert Kubernetes CPU string (e.g. '250m', '2') to cores."""
    value = value.strip()
    if value.endswith("m"):
        return float(value[:-1]) / 1000.0
    if value.endswith("n"):
        return float(value[:-1]) / 1e9
    try:
        return float(value)
    except ValueError:
        return 0.0


def _parse_memory(value: str) -> float:
    """Convert Kubernetes memory string (e.g. '512Mi', '1Gi') to bytes."""
    value = value.strip()
    multipliers = {
        "Ki": 1024,
        "Mi": 1024**2,
        "Gi": 1024**3,
        "Ti": 1024**4,
        "K": 1000,
        "M": 1000**2,
        "G": 1000**3,
        "T": 1000**4,
    }
    for suffix, mult in multipliers.items():
        if value.endswith(suffix):
            try:
                return float(value[: -len(suffix)]) * mult
            except ValueError:
                return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0
