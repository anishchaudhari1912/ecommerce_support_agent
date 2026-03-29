"""
Order Context Interpreter
=========================
Normalizes category strings, validates order fields, derives timing/value signals,
and emits fraud-risk hints before triage. Pure Python + light heuristics (no LLM).
"""

from __future__ import annotations
from datetime import date, datetime
from typing import List, Optional, Tuple

from utils.models import (
    SupportTicket,
    OrderContext,
    OrderContextResult,
    FraudSignal,
    ValidationError,
    DerivedOrderContext,
)


_CATEGORY_ALIASES = {
    "perishables": "perishable",
    "food": "perishable",
    "grocery": "perishable",
    "clothing": "apparel",
    "clothes": "apparel",
    "shoes": "footwear",
    "sneakers": "footwear",
    "phone": "electronics",
    "laptop": "electronics",
    "computer": "electronics",
    "n/a": "unknown",
    "na": "unknown",
    "none": "unknown",
}


def _parse_iso_date(s: Optional[str]) -> Optional[date]:
    if not s or not str(s).strip():
        return None
    s = str(s).strip()[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _days_since(some: date, ref: date) -> int:
    return max(0, (ref - some).days)


def _normalize_category(raw: str) -> str:
    c = raw.strip().lower()
    return _CATEGORY_ALIASES.get(c, c)


def _validate(ctx: OrderContext) -> List[ValidationError]:
    errs: List[ValidationError] = []
    oid = (ctx.order_id or "").strip()
    if len(oid) < 4:
        errs.append(
            ValidationError(
                field="order_id",
                message="Order ID is missing or too short to look up the order.",
                severity="critical",
            )
        )
    if ctx.item_value is not None and ctx.item_value < 0:
        errs.append(
            ValidationError(
                field="item_value",
                message="Item value cannot be negative.",
                severity="critical",
            )
        )
    od = _parse_iso_date(ctx.order_date)
    if ctx.order_date and ctx.order_date.strip() and od is None:
        errs.append(
            ValidationError(
                field="order_date",
                message="Order date is not a valid YYYY-MM-DD value.",
                severity="error",
            )
        )
    dd = _parse_iso_date(ctx.delivery_date)
    if ctx.delivery_date and str(ctx.delivery_date).strip() and dd is None:
        errs.append(
            ValidationError(
                field="delivery_date",
                message="Delivery date is not a valid YYYY-MM-DD value.",
                severity="error",
            )
        )
    return errs


def _fraud_signals(ticket: SupportTicket, ctx: OrderContext) -> Tuple[List[FraudSignal], str]:
    signals: List[FraudSignal] = []
    text = ticket.ticket_text.lower()
    score = 0

    if ctx.item_value >= 500:
        signals.append(
            FraudSignal(
                code="HIGH_VALUE",
                description=f"Line item value ${ctx.item_value:.2f} meets high-value review threshold.",
                severity="medium",
            )
        )
        score += 2

    if ctx.is_marketplace and ctx.item_value >= 300:
        signals.append(
            FraudSignal(
                code="MARKETPLACE_HIGH_VALUE",
                description="Marketplace order with substantial item value — verify seller and A-to-Z eligibility.",
                severity="medium",
            )
        )
        score += 1

    if any(
        w in text
        for w in (
            "unauthorized",
            "didn't make this purchase",
            "did not make this purchase",
            "don't recognize",
            "do not recognize",
            "fraud",
            "stolen card",
        )
    ):
        signals.append(
            FraudSignal(
                code="FRAUD_KEYWORDS",
                description="Ticket language suggests possible unauthorized payment or fraud — route to fraud review if confirmed.",
                severity="high",
            )
        )
        score += 3

    if any(
        w in text
        for w in (
            "threaten",
            "negative review",
            "lawyer",
            "sue",
            "legal action",
        )
    ):
        signals.append(
            FraudSignal(
                code="PRESSURE_OR_THREAT",
                description="Customer pressure or legal/review threats — document and follow special-circumstances policy.",
                severity="medium",
            )
        )
        score += 1

    if score >= 4:
        level = "high"
    elif score >= 2:
        level = "medium"
    else:
        level = "low"

    return signals, level


def _derive(ctx: OrderContext, normalized_cat: str) -> DerivedOrderContext:
    today = date.today()
    od = _parse_iso_date(ctx.order_date)
    dd = _parse_iso_date(ctx.delivery_date)
    days_order: Optional[int] = _days_since(od, today) if od else None
    days_del: Optional[int] = _days_since(dd, today) if dd else None
    return DerivedOrderContext(
        days_since_order=days_order,
        days_since_delivery=days_del,
        is_high_value=ctx.item_value >= 500.0,
        category_normalized=normalized_cat,
        item_value_usd=float(ctx.item_value),
    )


def run_order_context_interpreter(ticket: SupportTicket) -> OrderContextResult:
    """
    Normalize order context, validate fields, compute fraud heuristics and derived facts.
    """
    ctx = ticket.order_context
    cat = _normalize_category(ctx.item_category)
    normalized = ctx.model_copy(
        update={
            "item_category": cat,
            "order_id": (ctx.order_id or "").strip(),
        }
    )

    validation_errors = _validate(normalized)
    fraud_signals, fraud_level = _fraud_signals(ticket, normalized)
    derived = _derive(normalized, cat)

    return OrderContextResult(
        original_ctx=ticket.order_context,
        normalized_ctx=normalized,
        fraud_risk_level=fraud_level,
        fraud_signals=fraud_signals,
        validation_errors=validation_errors,
        derived=derived,
    )
