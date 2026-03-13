"""
FinSentry - FastAPI Application
=====================================

Creates and configures the FastAPI application with CORS middleware,
health-check endpoint, and API router.

Usage::

    uvicorn api.main:app --reload
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router
from api.schemas import HealthResponse
from api.services.pipeline import get_state

app = FastAPI(
    title="FinSentry",
    description=(
        "Financial crime detection system exposing fraud detection, "
        "graph intelligence, investigation case management, SAR generation, "
        "and compliance validation through REST endpoints."
    ),
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# CORS Middleware — allow all origins for development / frontend compat
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Include API routes
# ---------------------------------------------------------------------------

app.include_router(router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Root health-check endpoint."""
    state = get_state()
    return HealthResponse(
        status="ok",
        service="FinSentry",
        modules_loaded=9,
        transactions_loaded=len(state.transactions),
        cases_generated=len(state.cases),
        sar_reports_generated=len(state.sar_reports),
    )
