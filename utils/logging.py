"""
FinSentry AI - Structured Logging System
=========================================

Provides JSON-structured logging with per-module logger factories.
Every log record emitted through this system includes:

* ``timestamp`` — ISO-8601 UTC timestamp
* ``module``    — logical module name (e.g. ``ingestion.loader``)
* ``level``     — severity level (DEBUG … CRITICAL)
* ``message``   — free-form message text

Usage::

    from utils.logging import get_logger

    logger = get_logger("ingestion.loader")
    logger.info("Loaded %d transactions", count)
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class _JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects.

    Output schema::

        {
            "timestamp": "2025-01-01T12:00:00.000000+00:00",
            "module": "ingestion.loader",
            "level": "INFO",
            "message": "Loaded 500 transactions"
        }
    """

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        """Return the log record as a JSON string."""
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "module": record.name,
            "level": record.levelname,
            "message": record.getMessage(),
        }
        # Attach exception information if present
        if record.exc_info and record.exc_info[1] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, default=str)


def _get_log_level() -> int:
    """Resolve the configured log level from environment/settings.

    Falls back to ``INFO`` if the configuration module is not yet
    importable (avoids circular imports during early startup).
    """
    try:
        from utils.config import settings  # noqa: WPS433
        level_name = settings.LOG_LEVEL
    except Exception:  # pragma: no cover
        level_name = "INFO"
    return getattr(logging, level_name, logging.INFO)


# ---------------------------------------------------------------------------
# Module-level handler — shared across all loggers to avoid duplicate
# handlers when ``get_logger`` is called multiple times.
# ---------------------------------------------------------------------------
_HANDLER: logging.StreamHandler | None = None


def _ensure_handler() -> logging.StreamHandler:
    """Create or return the singleton stream handler."""
    global _HANDLER  # noqa: WPS420
    if _HANDLER is None:
        _HANDLER = logging.StreamHandler(stream=sys.stdout)
        _HANDLER.setFormatter(_JSONFormatter())
    return _HANDLER


def get_logger(module_name: str) -> logging.Logger:
    """Create (or retrieve) a named logger with JSON formatting.

    Args:
        module_name: Dot-separated logical module name
                     (e.g. ``"ingestion.loader"``).

    Returns:
        A :class:`logging.Logger` instance configured with JSON output
        and the application-wide log level.

    Example::

        logger = get_logger("fraud_detection.detector")
        logger.warning("High anomaly score: %.4f", score)
    """
    logger = logging.getLogger(module_name)
    # Prevent duplicate handlers if get_logger is called more than once
    if not logger.handlers:
        logger.addHandler(_ensure_handler())
    logger.setLevel(_get_log_level())
    logger.propagate = False
    return logger
