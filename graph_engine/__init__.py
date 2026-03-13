"""
FinSentry - Graph Intelligence Engine
==========================================

Graph-based analysis of financial transaction networks for detecting
suspicious structures, shell company networks, and laundering chains.

Modules:
    builder   -- GraphBuilder (transaction → NetworkX DiGraph).
    analyzer  -- GraphAnalyzer (centrality, communities, cycles, risk).
    models    -- Pydantic output models.
"""

from graph_engine.models import (
    CommunityResult,
    EntityRiskScore,
    NodeMetrics,
    PathResult,
)
from graph_engine.builder import GraphBuilder
from graph_engine.analyzer import GraphAnalyzer

__all__ = [
    "GraphBuilder",
    "GraphAnalyzer",
    "NodeMetrics",
    "CommunityResult",
    "PathResult",
    "EntityRiskScore",
]
