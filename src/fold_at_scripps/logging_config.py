"""Process-wide structured logging configuration."""

from __future__ import annotations

import logging.config

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%dT%H:%M:%S%z"


def configure_logging(level: str = "INFO") -> None:
    """Apply a consistent console logging configuration for the app/scheduler."""
    normalized = level.upper()
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"default": {"format": _FORMAT, "datefmt": _DATEFMT}},
            "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "default"}},
            "root": {"handlers": ["console"], "level": normalized},
            "loggers": {
                "uvicorn": {"level": normalized},
                "uvicorn.error": {"level": normalized},
                "uvicorn.access": {"level": normalized},
            },
        }
    )
