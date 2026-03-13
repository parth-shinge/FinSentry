"""
FinSentry AI - Shared Utilities Package
=======================================

Provides centralized configuration management and structured logging
used across all FinSentry AI modules.

Modules:
    config  - Environment-based configuration manager
    logging - JSON-structured logging system
"""

from utils.config import settings
from utils.logging import get_logger

__all__ = ["settings", "get_logger"]
