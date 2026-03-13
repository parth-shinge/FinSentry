"""
FinSentry - Agents Package
================================

High-level orchestration agents that coordinate the FinSentry investigation
pipeline and provide intelligent analysis capabilities.

Modules:
    orchestrator -- Full pipeline orchestration.
    timeline     -- Transaction timeline reconstruction.
    models       -- Data models for agent outputs.
"""

from agents.models import InvestigationResult, TimelineEvent
from agents.orchestrator import InvestigationOrchestrator
from agents.timeline import build_transaction_timeline

__all__ = [
    "InvestigationOrchestrator",
    "InvestigationResult",
    "TimelineEvent",
    "build_transaction_timeline",
]
