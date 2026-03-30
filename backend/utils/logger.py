"""Structured logging configuration for SCL-Governor.

Uses structlog with JSON output for production observability.
"""

from __future__ import annotations

import logging
import sys

import structlog


def _configure_structlog() -> None:
    """Configure structlog processors and output format once."""

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)


# Run once at import time.
_configure_structlog()


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger bound with the SCL-Governor service context.

    Parameters
    ----------
    name:
        Typically ``__name__`` of the calling module.
    """
    return structlog.get_logger(name).bind(service="scl-governor")
