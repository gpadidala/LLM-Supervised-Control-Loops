"""Notification connectors for SCL-Governor (Slack, PagerDuty)."""

from __future__ import annotations

from typing import Any

import httpx

from utils.logger import get_logger

log = get_logger(__name__)


class NotificationConnector:
    """Sends notifications to external channels (Slack, PagerDuty).

    If credentials are not configured the connector silently logs and
    returns -- it never blocks or raises.
    """

    def __init__(self, settings: Any) -> None:
        self.slack_webhook: str = getattr(settings, "SLACK_WEBHOOK_URL", "")
        self.pagerduty_key: str = getattr(settings, "PAGERDUTY_API_KEY", "")
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(10.0))
        return self._client

    # ------------------------------------------------------------------
    # Slack
    # ------------------------------------------------------------------

    async def send_slack(
        self,
        message: str,
        channel: str = "#scl-governor",
        severity: str = "info",
    ) -> bool:
        """Post a message to Slack via an incoming webhook.

        Returns ``True`` on success, ``False`` otherwise.
        """
        if not self.slack_webhook:
            log.debug("slack_not_configured", message=message[:120])
            return False

        color_map = {
            "info": "#36a64f",
            "warning": "#ffa500",
            "error": "#ff0000",
            "critical": "#8b0000",
        }
        color = color_map.get(severity, "#36a64f")

        payload = {
            "channel": channel,
            "attachments": [
                {
                    "color": color,
                    "title": f"SCL-Governor [{severity.upper()}]",
                    "text": message,
                    "footer": "SCL-Governor Notification",
                }
            ],
        }

        try:
            client = await self._ensure_client()
            resp = await client.post(self.slack_webhook, json=payload)
            if resp.status_code == 200:
                log.info("slack_notification_sent", severity=severity)
                return True
            log.warning(
                "slack_notification_failed",
                status=resp.status_code,
                body=resp.text[:200],
            )
            return False
        except Exception as exc:
            log.error("slack_notification_error", error=str(exc))
            return False

    # ------------------------------------------------------------------
    # PagerDuty
    # ------------------------------------------------------------------

    async def send_pagerduty(
        self,
        title: str,
        details: str,
        severity: str = "warning",
    ) -> bool:
        """Create a PagerDuty event via the Events API v2.

        Returns ``True`` on success, ``False`` otherwise.
        """
        if not self.pagerduty_key:
            log.debug("pagerduty_not_configured", title=title[:120])
            return False

        # Map our severity levels to PagerDuty severity values
        pd_severity_map = {
            "info": "info",
            "warning": "warning",
            "error": "error",
            "critical": "critical",
        }
        pd_severity = pd_severity_map.get(severity, "warning")

        payload = {
            "routing_key": self.pagerduty_key,
            "event_action": "trigger",
            "payload": {
                "summary": title,
                "severity": pd_severity,
                "source": "scl-governor",
                "custom_details": {"details": details},
            },
        }

        try:
            client = await self._ensure_client()
            resp = await client.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=payload,
            )
            if resp.status_code in (200, 202):
                log.info("pagerduty_event_sent", severity=severity, title=title[:80])
                return True
            log.warning(
                "pagerduty_event_failed",
                status=resp.status_code,
                body=resp.text[:200],
            )
            return False
        except Exception as exc:
            log.error("pagerduty_event_error", error=str(exc))
            return False

    # ------------------------------------------------------------------
    # Unified notification based on autonomy level
    # ------------------------------------------------------------------

    async def notify(self, decision: Any, execution_log: list[str]) -> None:
        """Send notifications appropriate for the decision's autonomy level.

        - ``execute_autonomous``: Slack info
        - ``execute_with_notification``: Slack warning
        - ``recommend``: Slack info (recommendation)
        - ``escalate``: Slack critical + PagerDuty
        """
        autonomy = getattr(decision, "autonomy_level", None)
        if autonomy is None:
            return

        level_str = autonomy.value if hasattr(autonomy, "value") else str(autonomy)
        action_type = getattr(decision, "action_type", "unknown")
        target = getattr(decision, "target", "unknown")
        reasoning = getattr(decision, "reasoning", "")
        confidence = getattr(decision, "confidence", 0.0)

        log_summary = "\n".join(execution_log[-5:]) if execution_log else "(none)"
        base_msg = (
            f"*Action:* {action_type} on `{target}`\n"
            f"*Confidence:* {confidence:.0%}\n"
            f"*Autonomy:* {level_str}\n"
            f"*Reasoning:* {reasoning[:300]}\n"
            f"*Log:* ```{log_summary}```"
        )

        if level_str == "execute_autonomous":
            await self.send_slack(
                f"Auto-executed action.\n{base_msg}",
                severity="info",
            )

        elif level_str == "execute_with_notification":
            await self.send_slack(
                f"Action executed (notification required).\n{base_msg}",
                severity="warning",
            )

        elif level_str == "recommend":
            await self.send_slack(
                f"Recommended action (human approval needed).\n{base_msg}",
                severity="info",
            )

        elif level_str == "escalate":
            await self.send_slack(
                f"ESCALATION: Immediate attention required.\n{base_msg}",
                severity="critical",
            )
            await self.send_pagerduty(
                title=f"SCL-Governor Escalation: {action_type} on {target}",
                details=base_msg,
                severity="critical",
            )

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
