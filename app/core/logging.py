"""
app/core/logging.py — structlog JSON configuration.

All logs are emitted as machine-parseable JSON for easy querying.
Use: log = structlog.get_logger(__name__)
"""

from __future__ import annotations

import logging
import sys

import structlog


def redact_secrets_processor(logger, log_method, event_dict):
    """Redact sensitive keys from the log event dictionary."""
    sensitive_keys = {"app_key", "api_key", "secret", "pepper", "token", "password"}
    for key in list(event_dict.keys()):
        if any(s in key.lower() for s in sensitive_keys):
            event_dict[key] = "[REDACTED]"
    return event_dict

def configure_logging(level: str = "INFO") -> None:
    """
    Configure structlog for JSON output.
    Call once at application startup before any logging occurs.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Configure stdlib logging to route through structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            redact_secrets_processor,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.ExceptionRenderer(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
