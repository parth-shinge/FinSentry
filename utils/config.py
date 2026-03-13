"""
FinSentry AI - Configuration Manager
=====================================

Centralized configuration system that loads environment variables from a
``.env`` file using ``python-dotenv``. All application settings are exposed
through a single ``Settings`` dataclass instance (``settings``).

Environment Variables:
    DATABASE_URL : str
        PostgreSQL connection string.
        Default: ``postgresql://postgres:postgres@localhost:5432/finsentry``
    MODEL_PATH : str
        Filesystem path where trained ML model artifacts are stored.
        Default: ``models/``
    LOG_LEVEL : str
        Root log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        Default: ``INFO``
    BATCH_SIZE : int
        Number of records per database batch insert.
        Default: ``1000``
    LARGE_TRANSACTION_THRESHOLD : float
        Amount above which a transaction is flagged as "large".
        Default: ``10000.0``

Usage::

    from utils.config import settings

    print(settings.DATABASE_URL)
    print(settings.LOG_LEVEL)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Load .env from project root (two levels up from this file)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=_ENV_FILE)


@dataclass(frozen=True)
class Settings:
    """Immutable application-wide settings loaded from environment variables.

    Attributes:
        DATABASE_URL: PostgreSQL connection string.
        MODEL_PATH: Path where ML model artifacts are stored.
        LOG_LEVEL: Logging verbosity level.
        BATCH_SIZE: Rows per batch insert.
        LARGE_TRANSACTION_THRESHOLD: Amount considered "large".
        PROJECT_ROOT: Absolute path to the project root directory.
    """

    DATABASE_URL: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/finsentry",
        )
    )
    MODEL_PATH: str = field(
        default_factory=lambda: os.getenv("MODEL_PATH", "models/")
    )
    LOG_LEVEL: str = field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper()
    )
    BATCH_SIZE: int = field(
        default_factory=lambda: int(os.getenv("BATCH_SIZE", "1000"))
    )
    LARGE_TRANSACTION_THRESHOLD: float = field(
        default_factory=lambda: float(
            os.getenv("LARGE_TRANSACTION_THRESHOLD", "10000.0")
        )
    )
    PROJECT_ROOT: Path = field(default_factory=lambda: _PROJECT_ROOT)

    # -- convenience helpers -------------------------------------------------

    def as_dict(self) -> dict:
        """Return all settings as a plain dictionary (useful for logging)."""
        return {
            "DATABASE_URL": self.DATABASE_URL,
            "MODEL_PATH": self.MODEL_PATH,
            "LOG_LEVEL": self.LOG_LEVEL,
            "BATCH_SIZE": self.BATCH_SIZE,
            "LARGE_TRANSACTION_THRESHOLD": self.LARGE_TRANSACTION_THRESHOLD,
            "PROJECT_ROOT": str(self.PROJECT_ROOT),
        }


# ---------------------------------------------------------------------------
# Singleton settings instance — importable throughout the application
# ---------------------------------------------------------------------------
settings = Settings()
