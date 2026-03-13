"""
FinSentry AI - Graph Builder
==============================

Constructs a directed financial transaction graph using NetworkX.

Nodes represent financial entities (accounts, individuals, corporations).
Edges represent transactions between entities, annotated with metadata
(amount, timestamp, fraud score, countries).

Usage::

    from graph_engine.builder import GraphBuilder

    builder = GraphBuilder()
    graph = builder.build_transaction_graph(transactions, fraud_scores)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Sequence

import networkx as nx

from ingestion.schema import NormalizedTransaction
from utils.logging import get_logger

logger = get_logger("graph_engine.builder")

#: Path to sample entities data (optional enrichment)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENTITIES_FILE = _PROJECT_ROOT / "data" / "sample_entities.json"


def _load_entity_metadata() -> dict[str, dict]:
    """Load entity metadata from sample_entities.json if available.

    Returns:
        Mapping of entity_id → metadata dict.
    """
    if not _ENTITIES_FILE.exists():
        return {}
    try:
        with open(_ENTITIES_FILE, encoding="utf-8") as fh:
            entities = json.load(fh)
        return {e["entity_id"]: e for e in entities}
    except Exception:
        logger.warning("Could not load entity metadata from %s", _ENTITIES_FILE)
        return {}


def _infer_entity_type(entity_id: str, metadata: dict[str, dict]) -> str:
    """Infer entity type from metadata or ID pattern.

    Args:
        entity_id: Entity identifier.
        metadata:  Pre-loaded entity metadata mapping.

    Returns:
        Entity type string (e.g. 'individual', 'corporation', 'unknown').
    """
    if entity_id in metadata:
        return metadata[entity_id].get("type", "unknown")
    # Fallback: infer from ID prefix pattern
    eid = entity_id.upper()
    if eid.startswith("ACC"):
        return "account"
    if eid.startswith("ENT"):
        return "entity"
    return "unknown"


class GraphBuilder:
    """Constructs a directed transaction graph from normalised transactions.

    The graph models sender → receiver relationships with edge metadata
    that includes transaction amounts, timestamps, fraud scores, and
    country codes.

    Args:
        load_metadata: Whether to load entity metadata from the sample
                       entities file for node enrichment.  Default True.

    Attributes:
        graph: The underlying ``networkx.DiGraph``.
    """

    def __init__(self, load_metadata: bool = True) -> None:
        self._graph = nx.DiGraph()
        self._transactions: list[NormalizedTransaction] = []
        self._fraud_scores: dict[str, float] = {}
        self._entity_metadata: dict[str, dict] = (
            _load_entity_metadata() if load_metadata else {}
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_transaction_graph(
        self,
        transactions: Sequence[NormalizedTransaction],
        fraud_scores: Optional[dict[str, float]] = None,
    ) -> nx.DiGraph:
        """Build the complete transaction graph.

        Args:
            transactions: Normalised transactions to model.
            fraud_scores: Optional mapping of transaction_id → fraud
                          probability in [0, 1].  When provided, each
                          edge is annotated with its fraud score.

        Returns:
            A ``networkx.DiGraph`` with entity nodes and transaction edges.
        """
        self._transactions = list(transactions)
        self._fraud_scores = fraud_scores or {}

        self._graph = nx.DiGraph()
        self.add_entity_nodes()
        self.add_transaction_edges()

        logger.info(
            "Built transaction graph: %d nodes, %d edges",
            self._graph.number_of_nodes(),
            self._graph.number_of_edges(),
        )
        return self._graph

    def add_entity_nodes(self) -> None:
        """Add entity nodes (senders and receivers) to the graph.

        Each node is annotated with:
        - ``entity_id``
        - ``entity_type`` (inferred from metadata or ID pattern)
        - ``country`` (jurisdiction from metadata, if available)
        """
        seen: set[str] = set()

        for txn in self._transactions:
            for eid in (txn.sender_entity_id, txn.receiver_entity_id):
                if eid not in seen:
                    seen.add(eid)
                    etype = _infer_entity_type(eid, self._entity_metadata)
                    meta = self._entity_metadata.get(eid, {})
                    self._graph.add_node(
                        eid,
                        entity_id=eid,
                        entity_type=etype,
                        country=meta.get("jurisdiction", ""),
                        risk_rating=meta.get("risk_rating", "unknown"),
                        name=meta.get("name", eid),
                    )

        logger.info("Added %d entity nodes", len(seen))

    def add_transaction_edges(self) -> None:
        """Add directed transaction edges (sender → receiver).

        Each edge stores:
        - ``transaction_id``
        - ``amount``
        - ``timestamp`` (ISO string)
        - ``fraud_score``
        - ``origin_country``
        - ``destination_country``
        - ``transaction_weight`` (amount × fraud_score)
        """
        for txn in self._transactions:
            fraud_score = self._fraud_scores.get(txn.transaction_id, 0.0)
            weight = txn.amount * fraud_score

            self._graph.add_edge(
                txn.sender_entity_id,
                txn.receiver_entity_id,
                transaction_id=txn.transaction_id,
                amount=txn.amount,
                timestamp=txn.timestamp.isoformat(),
                fraud_score=fraud_score,
                origin_country=txn.origin_country,
                destination_country=txn.destination_country,
                transaction_weight=weight,
            )

        logger.info("Added %d transaction edges", len(self._transactions))

    def get_graph(self) -> nx.DiGraph:
        """Return the built graph.

        Returns:
            The ``networkx.DiGraph`` (may be empty if
            :meth:`build_transaction_graph` has not been called).
        """
        return self._graph
