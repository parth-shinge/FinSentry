"""
FinSentry - API Package
============================

FastAPI backend exposing the FinSentry pipeline through REST endpoints.

Modules:
    main      -- FastAPI application instance.
    routes    -- API endpoint definitions.
    schemas   -- Pydantic request/response models.
    services/ -- Pipeline orchestration and state management.
"""

from api.main import app

__all__ = ["app"]
