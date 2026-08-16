"""Configuration du logging applicatif : JSON structuré (facilite l'ingestion en prod)."""

import logging
import sys

from pythonjsonlogger.json import JsonFormatter


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter(
            "{asctime}{levelname}{name}{message}",
            style="{",
            rename_fields={"asctime": "timestamp", "levelname": "level", "name": "logger"},
        )
    )

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
