"""
Run evaluation against the 20-ticket test set and single-ticket resolution helpers.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, TYPE_CHECKING

from utils.models import Decision, TicketResolution

from evaluation.metrics import save_evaluation_run

if TYPE_CHECKING:
    from crew import SupportResolutionCrew


def _decisions_flexible_match(expected: Decision, actual: Decision) -> bool:
    if expected == actual:
        return True
    # Escalation / safety bucket: human handoff or no safe auto-decision
    esc = {Decision.NEEDS_ESCALATION, Decision.ABSTAIN, Decision.NEEDS_INFO}
    if expected in esc and actual in esc:
        return True
    return False


def _print_resolution(resolution: TicketResolution) -> None:
    print(json.dumps(resolution.model_dump(), indent=2, default=str))


def run_single(ticket_id: str, crew: "SupportResolutionCrew") -> TicketResolution:
    from tests.test_ticket import get_ticket_by_id

    case = get_ticket_by_id(ticket_id)
    if case is None:
        raise ValueError(f"Unknown ticket id: {ticket_id!r}. Use STD-001, EXC-001, CON-001, NIP-001, etc.")
    resolution = crew.resolve(case["ticket"], verbose=True)
    _print_resolution(resolution)
    return resolution


def run_evaluation(crew: "SupportResolutionCrew", save_results: bool = True) -> Dict[str, Any]:
    from tests.test_ticket import get_all_tickets

    cases = get_all_tickets()
    rows: list[Dict[str, Any]] = []
    matches = 0
    with_citation = 0
    resolved_count = 0

    for case in cases:
        ticket = case["ticket"]
        expected: Decision = case["expected_decision"]
        cat = case["test_category"]

        resolution = crew.resolve(ticket, verbose=False)
        actual = resolution.decision
        ok = _decisions_flexible_match(expected, actual)
        if ok:
            matches += 1

        n_cit = len(resolution.citations)
        if actual not in (Decision.ABSTAIN, Decision.NEEDS_INFO) and n_cit >= 1:
            with_citation += 1
        if actual not in (Decision.NEEDS_INFO,):
            resolved_count += 1

        meta = resolution.metadata or {}
        rows.append(
            {
                "ticket_id": ticket.ticket_id,
                "test_category": cat,
                "expected_decision": expected.value,
                "actual_decision": actual.value,
                "match": ok,
                "citations_count": n_cit,
                "compliance_passed": resolution.compliance_passed,
                "elapsed_seconds": meta.get("elapsed_seconds"),
            }
        )

    n = len(cases)
    metrics = {
        "tickets": n,
        "decision_match_rate": round(matches / n, 4) if n else 0.0,
        "citation_coverage_rate": round(with_citation / max(resolved_count, 1), 4),
        "resolved_non_info": resolved_count,
    }

    payload = {
        "metrics": metrics,
        "results": rows,
    }

    print("\n=== Evaluation summary ===")
    for k, v in metrics.items():
        print(f"  {k}: {v}")
    print()

    if save_results:
        path = save_evaluation_run(payload)
        print(f"Saved results to {path}")

    return payload
