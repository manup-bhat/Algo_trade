"""
engine/core/notification_registry.py — Alert fan-out system.

Every alert in the engine (margin approaching limit, unhedged leg detected,
circuit breaker tripped, WS disconnect, EOD failure) is raised as an
`AlertEvent` and fanned out to every registered `NotificationChannel`.

Current channels:
    "telegram"  — sends to configured TELEGRAM_CHAT_ID via bot token
    "log"       — structlog CRITICAL (always registered, cannot be removed)

Adding a new channel (Discord, SMS, push notification, PagerDuty) is
one class + one registration line in runner.py — zero edits to call sites.

Pattern: Observer / Pub-Sub (Part3 §3.6).
"""

from __future__ import annotations

import dataclasses
import datetime
from typing import Any, Protocol, runtime_checkable

import structlog

from engine.core.registry import Registry

log = structlog.get_logger(__name__)


# ── AlertEvent ────────────────────────────────────────────────────────────────

@dataclasses.dataclass(slots=True)
class AlertEvent:
    """
    Typed alert payload fanned out to all registered notification channels.

    Attributes:
        type:       Machine-readable event type (snake_case).
                    Examples: "unhedged_leg", "circuit_breaker_tripped",
                    "eod_exit_failed", "margin_near_limit", "ws_fatal_disconnect".
        severity:   "INFO" | "WARNING" | "ERROR" | "CRITICAL"
        payload:    Arbitrary metadata dict for the channel renderer.
        strategy_id: The strategy that triggered the alert, or "" for engine-wide.
        timestamp:  UTC ISO-8601 string.
    """
    type: str
    severity: str                     # INFO | WARNING | ERROR | CRITICAL
    payload: dict[str, Any]
    strategy_id: str = ""
    timestamp: str = dataclasses.field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


# ── NotificationChannel Protocol ──────────────────────────────────────────────

@runtime_checkable
class NotificationChannel(Protocol):
    """
    Interface every notification channel must implement.

    `send()` must be non-blocking and must NEVER raise — log internally on
    failure. The notification subsystem must not be a reliability boundary
    for the trading engine.

    Implementations:
        LogChannel       — always registered, logs via structlog
        TelegramChannel  — engine/notifications/telegram_channel.py
    """

    key: str  # Registry key — "telegram", "log", "sms", "discord"

    async def send(self, event: AlertEvent) -> None:
        """Send the alert. Must not raise on failure."""
        ...


# ── Built-in: Log Channel ─────────────────────────────────────────────────────

class LogChannel:
    """
    Always-registered notification channel that logs via structlog.

    Guarantees that every alert is at minimum written to the structured log,
    even if no other channel is configured.
    """

    key = "log"

    async def send(self, event: AlertEvent) -> None:
        log_fn = {
            "CRITICAL": log.critical,
            "ERROR":    log.error,
            "WARNING":  log.warning,
        }.get(event.severity, log.info)

        log_fn(
            "alert_event",
            alert_type=event.type,
            severity=event.severity,
            strategy_id=event.strategy_id or "engine",
            **{k: v for k, v in event.payload.items() if isinstance(v, (str, int, float, bool))},
        )


# ── Singleton Registry ────────────────────────────────────────────────────────

#: Global notification registry — LogChannel is always pre-registered.
notification_registry: Registry[NotificationChannel] = Registry()
notification_registry.register("log", LogChannel())


# ── Fan-out helper ────────────────────────────────────────────────────────────

async def publish_alert(event: AlertEvent) -> None:
    """
    Fan out `event` to every registered notification channel.

    Channel failures are caught and logged — a broken Telegram connection
    must never prevent the CRITICAL log from being written.

    Args:
        event: Alert to publish.

    Usage:
        await publish_alert(AlertEvent(
            type="unhedged_leg",
            severity="CRITICAL",
            payload={"group_id": group.group_id, "symbol": leg.symbol},
            strategy_id="options_momentum",
        ))
    """
    for key in notification_registry.list_keys():
        channel = notification_registry.get_or_none(key)
        if channel is None:
            continue
        try:
            await channel.send(event)
        except Exception as exc:
            # Don't use log.error here — might recurse; use print as last resort
            print(f"[notification_registry] channel={key!r} send failed: {exc}")


def make_alert(
    type: str,
    severity: str,
    strategy_id: str = "",
    **payload_kwargs: Any,
) -> AlertEvent:
    """Convenience constructor for common alert patterns."""
    return AlertEvent(
        type=type,
        severity=severity,
        strategy_id=strategy_id,
        payload=payload_kwargs,
    )
