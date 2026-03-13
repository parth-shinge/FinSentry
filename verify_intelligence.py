"""
FinSentry — Verification script for investigation intelligence features.

Runs the full investigation pipeline on each demo dataset and confirms:
- AML patterns detected
- Risk explanations generated
- Investigation narratives generated
- SAR reports still generated correctly
"""

import csv
import sys
from pathlib import Path

# Ensure project root on path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.orchestrator import InvestigationOrchestrator
from ingestion.schema import NormalizedTransaction


def load_csv(filepath: Path) -> list[NormalizedTransaction]:
    """Load a CSV into NormalizedTransaction objects."""
    txns = []
    with open(filepath, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            txns.append(NormalizedTransaction(
                transaction_id=row["transaction_id"],
                account_id=row["account_id"],
                sender_entity_id=row["sender_entity_id"],
                receiver_entity_id=row["receiver_entity_id"],
                amount=float(row["amount"]),
                currency=row["currency"].upper(),
                timestamp=row["timestamp"],
                origin_country=row["origin_country"].upper(),
                destination_country=row["destination_country"].upper(),
                merchant_category=row["merchant_category"],
                transaction_type=row["transaction_type"],
                channel=row["channel"],
                risk_flag=row.get("risk_flag") or None,
            ))
    return txns


def verify_dataset(name: str, filepath: Path) -> bool:
    """Run pipeline on a dataset and verify all features produce output."""
    print(f"\n{'='*60}")
    print(f"  DATASET: {name}")
    print(f"  FILE:    {filepath.name}")
    print(f"{'='*60}")

    txns = load_csv(filepath)
    print(f"  Loaded {len(txns)} transactions")

    orchestrator = InvestigationOrchestrator(
        fraud_threshold=0.3,
        contamination=0.15,
        n_estimators=100,
        explain_top_n=0,  # skip SHAP for speed
    )

    result = orchestrator.run_full_investigation(txns)

    # Check results
    checks = {
        "Transactions processed": result.transactions_processed > 0,
        "Fraud results generated": len(result.fraud_results) > 0,
        "Graph metrics computed": len(result.graph_metrics) > 0,
        "AML patterns detected": len(result.aml_patterns) > 0,
        "Risk explanations generated": len(result.risk_explanations) > 0,
        "Cases generated": len(result.cases) > 0,
        "Narratives generated": len(result.narratives) > 0,
        "SAR reports generated": len(result.sar_reports) > 0,
        "Compliance validations run": len(result.validation_results) > 0,
    }

    all_pass = True
    for check_name, passed in checks.items():
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  [{status}] {check_name}")

    # Print details
    print(f"\n  Details:")
    print(f"    Transactions:     {result.transactions_processed}")
    print(f"    High-risk:        {result.high_risk_count}")
    print(f"    AML patterns:     {len(result.aml_patterns)}")
    for p in result.aml_patterns:
        print(f"      - {p.pattern_type} (confidence={p.confidence:.2f}, severity={p.severity})")
    print(f"    Risk explanations: {len(result.risk_explanations)}")
    if result.risk_explanations:
        ex = result.risk_explanations[0]
        print(f"      Example: {ex.entity_id} (score={ex.risk_score:.2f}, {len(ex.drivers)} drivers)")
        for d in ex.drivers[:3]:
            print(f"        • {d.factor}")
    print(f"    Cases:            {len(result.cases)}")
    print(f"    Narratives:       {len(result.narratives)}")
    if result.narratives:
        n = result.narratives[0]
        print(f"      Summary: {n.summary[:120]}...")
    print(f"    SAR reports:      {len(result.sar_reports)}")
    print(f"    All SARs valid:   {result.all_reports_valid}")

    return all_pass


def main():
    data_dir = ROOT / "data"
    datasets = [
        ("Shell Company Laundering", data_dir / "demo_shell_laundering.csv"),
        ("Structuring", data_dir / "demo_structuring.csv"),
        ("Offshore Chain", data_dir / "demo_offshore_chain.csv"),
    ]

    results = {}
    for name, filepath in datasets:
        results[name] = verify_dataset(name, filepath)

    print(f"\n{'='*60}")
    print(f"  VERIFICATION SUMMARY")
    print(f"{'='*60}")
    all_pass = True
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  [{status}] {name}")

    print(f"\n  Overall: {'ALL PASSED' if all_pass else 'SOME FAILED'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
