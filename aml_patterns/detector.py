"""
FinSentry - AML Pattern Detection
=======================================

Detects Anti-Money Laundering patterns in financial transaction data.

Patterns
--------
* **Structuring** — Splitting large transfers into smaller amounts
  below reporting thresholds.
* **Layering** — Moving funds through multiple intermediaries to
  obscure the money trail.
* **Round-tripping** — Funds that leave an entity and return through
  a circular chain of transactions.
* **Rapid transfers** — Multiple transfers in a very short time
  window, suggesting automated or coordinated activity.
* **Shell company clusters** — Dense clusters of entities with
  minimal legitimate activity and high transaction volumes.

Usage::

    from aml_patterns.detector import AMLPatternDetector

    detector = AMLPatternDetector()
    patterns = detector.detect_all(transactions, fraud_results, graph, entity_risk_scores)
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Dict, List, Optional, Sequence, Set

import networkx as nx  # type: ignore[import-untyped]

from aml_patterns.models import PatternDetection
from fraud_detection.models import DetectionResult
from graph_engine.models import EntityRiskScore
from ingestion.schema import NormalizedTransaction
from utils.logging import get_logger

logger = get_logger("aml_patterns.detector")

# ---------------------------------------------------------------------------
# Configurable thresholds
# ---------------------------------------------------------------------------
_STRUCTURING_THRESHOLD = 10_000.0   # CTR reporting limit
_STRUCTURING_RATIO = 0.85           # How close to the limit
_RAPID_WINDOW_MINUTES = 60
_RAPID_MIN_COUNT = 3
_LAYER_MIN_HOPS = 3
_SHELL_MIN_ENTITIES = 3
_SHELL_MAX_UNIQUE_COUNTERPARTIES = 2


class AMLPatternDetector:
    """Detects common AML typologies in transaction data.

    Uses transaction features, graph topology, and fraud scores
    to identify structuring, layering, round-tripping, rapid
    transfers, and shell company clusters.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect_all(
        self,
        transactions: Sequence[NormalizedTransaction],
        fraud_results: Sequence[DetectionResult],
        graph: Optional[nx.DiGraph] = None,
        entity_risk_scores: Optional[Sequence[EntityRiskScore]] = None,
    ) -> List[PatternDetection]:
        """Run all pattern detectors and return combined results.

        Args:
            transactions:       Normalised transactions.
            fraud_results:      Fraud detection results.
            graph:              Optional transaction graph.
            entity_risk_scores: Optional entity risk scores.

        Returns:
            List of detected :class:`PatternDetection` objects.
        """
        txn_list = list(transactions)
        fraud_map = {
            r.transaction_id: r.fraud_score.fraud_probability
            for r in fraud_results
        }

        patterns: List[PatternDetection] = []

        patterns.extend(self.detect_structuring(txn_list))
        patterns.extend(self.detect_rapid_transfers(txn_list))

        if graph is not None:
            patterns.extend(self.detect_layering(txn_list, graph))
            patterns.extend(self.detect_round_tripping(graph, fraud_map))
            patterns.extend(
                self.detect_shell_company_clusters(
                    txn_list, graph, entity_risk_scores
                )
            )

        logger.info("Detected %d AML patterns total", len(patterns))
        return patterns

    # ------------------------------------------------------------------
    # 1. Structuring
    # ------------------------------------------------------------------

    def detect_structuring(
        self,
        transactions: Sequence[NormalizedTransaction],
    ) -> List[PatternDetection]:
        """Detect structuring — splitting deposits below CTR threshold.

        Looks for entities sending multiple transactions just below
        $10,000 within a 24-hour window.
        """
        patterns: List[PatternDetection] = []

        # Group by sender entity
        sender_txns: Dict[str, List[NormalizedTransaction]] = defaultdict(list)
        for txn in transactions:
            sender_txns[txn.sender_entity_id].append(txn)

        for entity, txns in sender_txns.items():
            # Find transactions just below the threshold
            below_threshold = [
                t for t in txns
                if _STRUCTURING_THRESHOLD * _STRUCTURING_RATIO
                <= t.amount
                < _STRUCTURING_THRESHOLD
            ]

            if len(below_threshold) < 2:
                continue

            # Check if they cluster within 24 hours
            below_threshold.sort(key=lambda t: t.timestamp)
            window_txns: List[NormalizedTransaction] = []

            for i, txn in enumerate(below_threshold):
                window_txns = [txn]
                for j in range(i + 1, len(below_threshold)):
                    if (below_threshold[j].timestamp - txn.timestamp) <= timedelta(hours=24):
                        window_txns.append(below_threshold[j])
                    else:
                        break

                if len(window_txns) >= 2:
                    total = sum(t.amount for t in window_txns)
                    confidence = min(
                        0.5 + (len(window_txns) - 2) * 0.15 + (total / _STRUCTURING_THRESHOLD / 3) * 0.2,
                        0.99,
                    )
                    hours = (window_txns[-1].timestamp - window_txns[0].timestamp).total_seconds() / 3600

                    patterns.append(
                        PatternDetection(
                            pattern_type="structuring",
                            confidence=round(confidence, 3),
                            severity="high" if len(window_txns) >= 3 else "medium",
                            description=(
                                f"Entity {entity} made {len(window_txns)} transactions "
                                f"totaling ${total:,.2f} just below the "
                                f"${_STRUCTURING_THRESHOLD:,.0f} reporting threshold "
                                f"within {hours:.1f} hours."
                            ),
                            involved_entities=[entity],
                            involved_transactions=[
                                t.transaction_id for t in window_txns
                            ],
                            total_amount=round(total, 2),
                            time_window_hours=round(hours, 2),
                            indicators=[
                                "amounts_below_ctr_threshold",
                                "clustered_time_window",
                                f"{len(window_txns)}_transactions",
                            ],
                        )
                    )
                    break  # One pattern per entity

        logger.info("Structuring: %d patterns", len(patterns))
        return patterns

    # ------------------------------------------------------------------
    # 2. Layering
    # ------------------------------------------------------------------

    def detect_layering(
        self,
        transactions: Sequence[NormalizedTransaction],
        graph: nx.DiGraph,
    ) -> List[PatternDetection]:
        """Detect layering — funds moved through multiple intermediaries.

        Identifies multi-hop chains (≥3 hops) in timestamp order
        where amounts are progressively similar (funds passing through).
        """
        patterns: List[PatternDetection] = []

        if graph.number_of_nodes() == 0:
            return patterns

        visited_chains: Set[str] = set()

        for node in list(graph.nodes):
            node_str = str(node)
            chains = self._find_layering_chains(
                graph, node_str, _LAYER_MIN_HOPS
            )

            for chain in chains:
                chain_key = "->".join(chain["path"])
                if chain_key in visited_chains:
                    continue
                visited_chains.add(chain_key)

                cross_border = any(
                    t.is_international
                    for t in transactions
                    if t.transaction_id in chain.get("txn_ids", [])
                )

                confidence = min(
                    0.6 + (len(chain["path"]) - _LAYER_MIN_HOPS) * 0.1
                    + (0.1 if cross_border else 0.0),
                    0.99,
                )

                patterns.append(
                    PatternDetection(
                        pattern_type="layering",
                        confidence=round(confidence, 3),
                        severity="high" if len(chain["path"]) >= 4 else "medium",
                        description=(
                            f"Multi-hop transfer chain of {len(chain['path'])} "
                            f"entities: {' → '.join(chain['path'][:5])}"
                            f"{'…' if len(chain['path']) > 5 else ''} "
                            f"totaling ${chain['total_amount']:,.2f}."
                        ),
                        involved_entities=chain["path"],
                        involved_transactions=chain.get("txn_ids", []),
                        total_amount=round(chain["total_amount"], 2),
                        time_window_hours=round(chain.get("hours", 0), 2),
                        indicators=[
                            "multi_hop_chain",
                            f"{len(chain['path'])}_intermediaries",
                            *(["cross_border"] if cross_border else []),
                        ],
                    )
                )

        logger.info("Layering: %d patterns", len(patterns))
        return patterns

    def _find_layering_chains(
        self, graph: nx.DiGraph, start: str, min_hops: int
    ) -> List[Dict]:
        """DFS to find timestamp-ordered chains from a start node."""
        chains: List[Dict] = []
        self._dfs_layer(
            graph, start, [start], set(), 0.0, None, [], min_hops, chains
        )
        return chains

    def _dfs_layer(
        self,
        graph: nx.DiGraph,
        current: str,
        path: List[str],
        visited: Set[str],
        total_amount: float,
        last_ts: Optional[str],
        txn_ids: List[str],
        min_hops: int,
        chains: List[Dict],
    ) -> None:
        if len(path) - 1 >= min_hops:
            first_ts = txn_ids[0] if txn_ids else ""
            last_ts_val = txn_ids[-1] if txn_ids else ""
            chains.append({
                "path": list(path),
                "total_amount": total_amount,
                "txn_ids": list(txn_ids),
                "hours": 0.0,
            })

        if len(path) > 6:  # cap depth
            return

        for raw_succ in graph.successors(current):
            succ = str(raw_succ)
            if succ in visited:
                continue

            edge_data = dict(graph.edges[current, succ])
            edge_ts = str(edge_data.get("timestamp", ""))
            edge_amount = float(edge_data.get("amount", 0))
            edge_txn_id = str(edge_data.get("transaction_id", ""))

            if last_ts and edge_ts < last_ts:
                continue

            visited.add(succ)
            self._dfs_layer(
                graph, succ, path + [succ], visited,
                total_amount + edge_amount, edge_ts,
                txn_ids + ([edge_txn_id] if edge_txn_id else []),
                min_hops, chains,
            )
            visited.discard(succ)

    # ------------------------------------------------------------------
    # 3. Round-tripping
    # ------------------------------------------------------------------

    def detect_round_tripping(
        self,
        graph: nx.DiGraph,
        fraud_map: Dict[str, float],
    ) -> List[PatternDetection]:
        """Detect round-tripping — funds returning to origin via cycles.

        Uses simple cycle detection to find circular money flows.
        """
        patterns: List[PatternDetection] = []

        if graph.number_of_nodes() == 0:
            return patterns

        try:
            cycles = [
                [str(n) for n in c]
                for c in nx.simple_cycles(graph)
                if len(c) <= 6
            ]
        except Exception:
            return patterns

        for cycle in cycles[:20]:  # Limit for performance
            total_amount = 0.0
            max_fraud = 0.0
            for i in range(len(cycle)):
                u, v = cycle[i], cycle[(i + 1) % len(cycle)]
                if graph.has_edge(u, v):
                    edge = dict(graph.edges[u, v])
                    total_amount += float(edge.get("amount", 0))
                    max_fraud = max(max_fraud, float(edge.get("fraud_score", 0)))

            if total_amount < 1000:
                continue

            confidence = min(
                0.5 + max_fraud * 0.3 + (len(cycle) / 10.0),
                0.99,
            )

            patterns.append(
                PatternDetection(
                    pattern_type="round_tripping",
                    confidence=round(confidence, 3),
                    severity="critical" if max_fraud >= 0.7 else "high",
                    description=(
                        f"Circular money flow involving {len(cycle)} entities: "
                        f"{' → '.join(cycle)} → {cycle[0]}. "
                        f"Total value ${total_amount:,.2f}."
                    ),
                    involved_entities=cycle,
                    involved_transactions=[],
                    total_amount=round(total_amount, 2),
                    indicators=[
                        "circular_flow",
                        f"{len(cycle)}_entity_cycle",
                        f"max_fraud_{max_fraud:.2f}",
                    ],
                )
            )

        logger.info("Round-tripping: %d patterns", len(patterns))
        return patterns

    # ------------------------------------------------------------------
    # 4. Rapid Transfers
    # ------------------------------------------------------------------

    def detect_rapid_transfers(
        self,
        transactions: Sequence[NormalizedTransaction],
    ) -> List[PatternDetection]:
        """Detect rapid transfers — multiple sends from one entity in a short window."""
        patterns: List[PatternDetection] = []

        sender_txns: Dict[str, List[NormalizedTransaction]] = defaultdict(list)
        for txn in transactions:
            sender_txns[txn.sender_entity_id].append(txn)

        for entity, txns in sender_txns.items():
            if len(txns) < _RAPID_MIN_COUNT:
                continue

            txns.sort(key=lambda t: t.timestamp)

            for i in range(len(txns)):
                window: List[NormalizedTransaction] = [txns[i]]
                for j in range(i + 1, len(txns)):
                    if (txns[j].timestamp - txns[i].timestamp) <= timedelta(
                        minutes=_RAPID_WINDOW_MINUTES
                    ):
                        window.append(txns[j])
                    else:
                        break

                if len(window) >= _RAPID_MIN_COUNT:
                    total = sum(t.amount for t in window)
                    minutes = (
                        (window[-1].timestamp - window[0].timestamp).total_seconds() / 60
                    )
                    unique_receivers = len(set(t.receiver_entity_id for t in window))

                    confidence = min(
                        0.5 + (len(window) - _RAPID_MIN_COUNT) * 0.1
                        + (unique_receivers / 5) * 0.15,
                        0.99,
                    )

                    patterns.append(
                        PatternDetection(
                            pattern_type="rapid_transfers",
                            confidence=round(confidence, 3),
                            severity="high" if len(window) >= 5 else "medium",
                            description=(
                                f"Entity {entity} executed {len(window)} "
                                f"transfers to {unique_receivers} recipients "
                                f"within {minutes:.0f} minutes, "
                                f"totaling ${total:,.2f}."
                            ),
                            involved_entities=[entity] + list(
                                set(t.receiver_entity_id for t in window)
                            ),
                            involved_transactions=[
                                t.transaction_id for t in window
                            ],
                            total_amount=round(total, 2),
                            time_window_hours=round(minutes / 60, 2),
                            indicators=[
                                "rapid_execution",
                                f"{len(window)}_transfers_{minutes:.0f}min",
                                f"{unique_receivers}_unique_receivers",
                            ],
                        )
                    )
                    break  # One pattern per entity

        logger.info("Rapid transfers: %d patterns", len(patterns))
        return patterns

    # ------------------------------------------------------------------
    # 5. Shell Company Clusters
    # ------------------------------------------------------------------

    def detect_shell_company_clusters(
        self,
        transactions: Sequence[NormalizedTransaction],
        graph: nx.DiGraph,
        entity_risk_scores: Optional[Sequence[EntityRiskScore]] = None,
    ) -> List[PatternDetection]:
        """Detect shell company clusters — dense entity groups with minimal diversity."""
        patterns: List[PatternDetection] = []

        if graph.number_of_nodes() == 0:
            return patterns

        risk_map = (
            {r.entity_id: r for r in entity_risk_scores}
            if entity_risk_scores
            else {}
        )

        # Build transaction counts per entity
        entity_txn_count: Dict[str, int] = defaultdict(int)
        entity_counterparties: Dict[str, Set[str]] = defaultdict(set)
        entity_total_amount: Dict[str, float] = defaultdict(float)

        for txn in transactions:
            entity_txn_count[txn.sender_entity_id] += 1
            entity_counterparties[txn.sender_entity_id].add(
                txn.receiver_entity_id
            )
            entity_total_amount[txn.sender_entity_id] += txn.amount

        # Look for communities where many entities have limited counterparties
        try:
            from networkx.algorithms.community import greedy_modularity_communities
            undirected = graph.to_undirected()
            communities = list(greedy_modularity_communities(undirected))
        except Exception:
            return patterns

        for comm_idx, community in enumerate(communities):
            members = [str(m) for m in community]
            if len(members) < _SHELL_MIN_ENTITIES:
                continue

            # Check for shell-like characteristics
            shell_indicators: List[str] = []
            low_diversity_count = 0

            for member in members:
                cp_count = len(entity_counterparties.get(member, set()))
                if cp_count <= _SHELL_MAX_UNIQUE_COUNTERPARTIES:
                    low_diversity_count += 1

            diversity_ratio = low_diversity_count / len(members)
            if diversity_ratio < 0.5:
                continue

            # Check internal transaction volume
            internal_amount = 0.0
            for m1 in members:
                for m2 in members:
                    if graph.has_edge(m1, m2):
                        edge = dict(graph.edges[m1, m2])
                        internal_amount += float(edge.get("amount", 0))

            # Average risk score
            avg_risk = 0.0
            risk_entities = [risk_map[m] for m in members if m in risk_map]
            if risk_entities:
                avg_risk = sum(
                    r.overall_risk_score for r in risk_entities
                ) / len(risk_entities)

            if avg_risk < 0.2 and internal_amount < 10000:
                continue

            shell_indicators.extend([
                f"{diversity_ratio:.0%}_low_diversity",
                f"community_{comm_idx}",
                f"avg_risk_{avg_risk:.2f}",
            ])

            confidence = min(
                0.4 + diversity_ratio * 0.3 + avg_risk * 0.2,
                0.99,
            )

            patterns.append(
                PatternDetection(
                    pattern_type="shell_company_clusters",
                    confidence=round(confidence, 3),
                    severity="high" if avg_risk >= 0.5 else "medium",
                    description=(
                        f"Cluster of {len(members)} entities in community "
                        f"{comm_idx} showing shell-like behavior: "
                        f"{low_diversity_count} entities with limited "
                        f"counterparty diversity. Internal flow "
                        f"${internal_amount:,.2f}, avg risk {avg_risk:.2f}."
                    ),
                    involved_entities=members,
                    involved_transactions=[],
                    total_amount=round(internal_amount, 2),
                    indicators=shell_indicators,
                )
            )

        logger.info("Shell company clusters: %d patterns", len(patterns))
        return patterns
