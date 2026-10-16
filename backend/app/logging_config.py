"""Structured JSON logging without PHI (owner: P1).

Log IDs, counts, codes and durations only. Never log document text, quotes, names, RČ, contacts or addresses.
The redaction processor below is a safety net, not a licence to pass PHI to the logger.
"""

from __future__ import annotations

import logging
from collections.abc import MutableMapping
from typing import Any

import structlog

# Keys that must never reach a log line. Matching is case-insensitive on the key name.
REDACTED_KEYS = frozenset(
    {
        "address",
        "api_key",
        "authorization",
        "birth_number",
        "content",
        "email",
        "family",
        "given",
        "name",
        "password",
        "phone",
        "quote",
        "rc",
        "text",
    }
)
REDACTED = "[redacted]"


def redact_phi(_logger: Any, _method: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    for key in list(event_dict):
        if key.lower() in REDACTED_KEYS:
            event_dict[key] = REDACTED
    return event_dict


def configure_logging(level: str = "INFO", *, json: bool = True) -> None:
    level_no = logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer(ensure_ascii=False) if json else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact_phi,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level_no),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )
