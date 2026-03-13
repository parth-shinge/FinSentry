"""
FinSentry - Transaction Timeline Reconstruction
=====================================================

Builds a chronological timeline of events from an investigation case,
reconstructing the sequence of financial activities that triggered
suspicion.

Event Types
-----------
* **deposit**           — Inbound domestic transfer.
* **transfer**          — Outbound domestic transfer.
* **offshore_movement** — Cross-border transfer to/from a foreign jurisdiction.
* **withdrawal**        — Outbound transfer from an account (inferred).
* **flagged_transaction** — Transaction with elevated fraud score.

Usage::

    from agents.timeline import build_transaction_timeline

    events = build_transaction_timeline(case, transactions, fraud_results)
"""

from __future__ import annotations

from typing import Optional, Sequence

from agents.models import TimelineEvent
from case_builder.models import Case
from fraud_detection.models import DetectionResult
from ingestion.schema import NormalizedTransaction
from utils.logging import get_logger

logger = get_logger("agents.timeline")

# Fraud score threshold for flagging in the timeline
_FLAG_THRESHOLD = 0.5


def _classify_event(
    txn: NormalizedTransaction,
    primary_entity: str,
    fraud_prob: float,
) -> str:
    """Classify a transaction into a timeline event type.

    Args:
        txn:            The transaction to classify.
        primary_entity: The primary entity under investigation.
        fraud_prob:     Fraud probability for this transaction.

    Returns:
        Event type string.
    """
    is_sender = txn.sender_entity_id == primary_entity
    is_receiver = txn.receiver_entity_id == primary_entity

    # Cross-border always flagged as offshore movement
    if txn.is_international:
        return "offshore_movement"

    # Flagged high-risk transaction
    if fraud_prob >= _FLAG_THRESHOLD:
        return "flagged_transaction"

    # Direction-based classification
    if is_receiver and not is_sender:
        return "deposit"
    if is_sender and not is_receiver:
        if txn.transaction_type in ("withdrawal", "atm"):
            return "withdrawal"
        return "transfer"

    return "transfer"


def _build_description(
    txn: NormalizedTransaction,
    event_type: str,
    fraud_prob: float,
) -> str:
    """Build a human-readable description for a timeline event.

    Args:
        txn:        The transaction.
        event_type: Classified event type.
        fraud_prob: Fraud probability.

    Returns:
        Description string.
    """
    amount_str = f"${txn.amount:,.2f} {txn.currency}"

    descriptions = {
        "deposit": (
            f"Received {amount_str} from {txn.sender_entity_id} "
            f"via {txn.transaction_type} ({txn.channel})"
        ),
        "transfer": (
            f"Sent {amount_str} to {txn.receiver_entity_id} "
            f"via {txn.transaction_type} ({txn.channel})"
        ),
        "offshore_movement": (
            f"Cross-border transfer of {amount_str} from "
            f"{txn.origin_country} to {txn.destination_country} "
            f"({txn.sender_entity_id} → {txn.receiver_entity_id})"
        ),
        "withdrawal": (
            f"Withdrawal of {amount_str} from account "
            f"{txn.account_id} via {txn.channel}"
        ),
        "flagged_transaction": (
            f"FLAGGED: {amount_str} transferred "
            f"{txn.sender_entity_id} → {txn.receiver_entity_id} "
            f"(fraud probability: {fraud_prob:.2%})"
        ),
    }

    return descriptions.get(event_type, f"Transaction of {amount_str}")


def build_transaction_timeline(
    case: Case,
    transactions: Sequence[NormalizedTransaction],
    fraud_results: Optional[Sequence[DetectionResult]] = None,
) -> list[TimelineEvent]:
    """Build a chronological timeline of events for an investigation case.

    Filters the full transaction set to only those involving case entities,
    classifies each as a specific event type, and sorts chronologically.

    Args:
        case:          The investigation case to build a timeline for.
        transactions:  Full transaction dataset.
        fraud_results: Optional fraud detection results for enrichment.

    Returns:
        Chronologically sorted list of :class:`TimelineEvent`.
    """
    # Build fraud score lookup
    fraud_map: dict[str, DetectionResult] = {}
    if fraud_results:
        fraud_map = {r.transaction_id: r for r in fraud_results}

    # Identify all entities in this case
    case_entities = {case.primary_entity} | set(case.related_entities)
    case_txn_ids = set(case.transactions)

    # Filter transactions relevant to this case
    relevant_txns: list[NormalizedTransaction] = []
    for txn in transactions:
        if txn.transaction_id in case_txn_ids:
            relevant_txns.append(txn)
        elif (
            txn.sender_entity_id in case_entities
            or txn.receiver_entity_id in case_entities
        ):
            relevant_txns.append(txn)

    # Sort chronologically
    relevant_txns.sort(key=lambda t: t.timestamp)

    # Build timeline events
    events: list[TimelineEvent] = []
    for txn in relevant_txns:
        det = fraud_map.get(txn.transaction_id)
        fraud_prob = det.fraud_score.fraud_probability if det else 0.0
        risk_level = det.fraud_score.risk_level.value if det else None

        event_type = _classify_event(txn, case.primary_entity, fraud_prob)
        description = _build_description(txn, event_type, fraud_prob)

        events.append(
            TimelineEvent(
                timestamp=txn.timestamp.isoformat(),
                event_type=event_type,
                description=description,
                transaction_id=txn.transaction_id,
                sender=txn.sender_entity_id,
                receiver=txn.receiver_entity_id,
                amount=txn.amount,
                currency=txn.currency,
                origin_country=txn.origin_country,
                destination_country=txn.destination_country,
                fraud_score=fraud_prob,
                risk_level=risk_level,
            )
        )

    logger.info(
        "Built timeline for case %s: %d events from %d relevant transactions",
        case.case_id,
        len(events),
        len(relevant_txns),
    )
    return events
