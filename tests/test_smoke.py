"""Smoke tests that do not call the Gemini API."""

from agents.order_context_agent import run_order_context_interpreter
from tests.test_ticket import get_ticket_by_id


def test_order_context_normalizes_perishable():
    case = get_ticket_by_id("EXC-001")
    assert case is not None
    r = run_order_context_interpreter(case["ticket"])
    assert r.normalized_ctx.item_category == "perishable"
    assert r.fraud_risk_level in ("low", "medium", "high")
    assert not r.has_critical_errors


def test_project_imports():
    import evaluation.run_evaluation  # noqa: F401
    import evaluation.metrics  # noqa: F401
    import utils.formatting  # noqa: F401
