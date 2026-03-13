"""
FinSentry - Graph Intelligence Data Models
===============================================

Pydantic models for graph analysis outputs.

Models
------
NodeMetrics
    Per-entity graph metrics including centrality, PageRank, and
    community assignment.
CommunityResult
    Community detection output with fraud density statistics.
PathResult
    Suspicious path between entities with transaction details.
EntityRiskScore
    Composite risk score combining graph-based indicators into an
    overall entity risk assessment.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class NodeMetrics(BaseModel):
    """Per-node graph metrics for a financial entity.

    Attributes:
        entity_id:              Unique entity identifier.
        node_type:              Entity type (individual, corporation, etc.).
        degree_centrality:      Degree centrality in [0, 1].
        betweenness_centrality: Betweenness centrality in [0, 1].
        pagerank:               PageRank score.
        in_degree:              Number of incoming edges.
        out_degree:             Number of outgoing edges.
        community_id:           Community assignment from detection.
    """

    entity_id: str
    node_type: str = "unknown"
    degree_centrality: float = Field(ge=0.0, default=0.0)
    betweenness_centrality: float = Field(ge=0.0, default=0.0)
    pagerank: float = Field(ge=0.0, default=0.0)
    in_degree: int = Field(ge=0, default=0)
    out_degree: int = Field(ge=0, default=0)
    community_id: int = -1


class CommunityResult(BaseModel):
    """Community detection output for a group of related entities.

    Attributes:
        community_id:       Unique community identifier.
        member_entities:    List of entity IDs in this community.
        member_count:       Number of entities in the community.
        avg_fraud_density:  Average fraud score of edges within the
                            community.
        high_risk_count:    Number of high-risk entities in the community.
    """

    community_id: int
    member_entities: list[str]
    member_count: int = Field(ge=0)
    avg_fraud_density: float = Field(ge=0.0, default=0.0)
    high_risk_count: int = Field(ge=0, default=0)


class PathResult(BaseModel):
    """A path between two entities in the transaction graph.

    Attributes:
        source:          Source entity ID.
        target:          Target entity ID.
        path_nodes:      Ordered list of entity IDs along the path.
        path_length:     Number of hops.
        total_amount:    Sum of transaction amounts along the path.
        max_fraud_score: Maximum fraud score encountered along the path.
    """

    source: str
    target: str
    path_nodes: list[str]
    path_length: int = Field(ge=0)
    total_amount: float = Field(ge=0.0, default=0.0)
    max_fraud_score: float = Field(ge=0.0, le=1.0, default=0.0)


class EntityRiskScore(BaseModel):
    """Composite graph-based risk score for a financial entity.

    Combines multiple graph-theoretic indicators into a single
    risk assessment.

    Attributes:
        entity_id:                Unique entity identifier.
        centrality_score:         Weighted centrality (degree + PageRank).
        community_fraud_density:  Average fraud density of the entity's
                                  community.
        high_risk_neighbor_count: Number of neighbors with high fraud
                                  activity.
        cycle_participation_count: Number of cycles the entity appears in.
        overall_risk_score:       Final composite risk score in [0, 1].
        suspicious_paths:         Notable suspicious paths involving this
                                  entity.
    """

    entity_id: str
    centrality_score: float = Field(ge=0.0, default=0.0)
    community_fraud_density: float = Field(ge=0.0, default=0.0)
    high_risk_neighbor_count: int = Field(ge=0, default=0)
    cycle_participation_count: int = Field(ge=0, default=0)
    overall_risk_score: float = Field(ge=0.0, le=1.0, default=0.0)
    suspicious_paths: list[PathResult] = Field(default_factory=list)
