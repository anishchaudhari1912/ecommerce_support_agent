"""
Triage Agent
============
Classifies the support ticket issue type, identifies missing information,
and generates up to 3 clarifying questions when needed.

Uses the Google Gemini API via utils.llm_client (no CrewAI dependency required for basic use;
integrates as a CrewAI Agent when orchestrated via crew.py).
"""

from __future__ import annotations
import json
import re
from typing import Any, Dict

from utils.models import (
    SupportTicket, TriageResult, IssueType, OrderContext
)
from utils.llm_client import call_llm


TRIAGE_SYSTEM_PROMPT = """You are a Senior Customer Support Triage Specialist for ShopCore, a large e-commerce platform.

Your job is to:
1. Read a support ticket and the associated order context.
2. Classify the PRIMARY issue type from this list:
   - refund: customer wants money back
   - shipping: delivery issues, lost packages, tracking problems
   - payment: billing errors, duplicate charges, payment method issues
   - promo: coupon, promotion, price match, loyalty points
   - fraud: unauthorized charges, account takeover, counterfeit item
   - dispute: damaged item, wrong item, missing items, not as described
   - cancellation: wants to cancel order or subscription
   - warranty: product defect, warranty claim
   - account: account access, settings, subscription management
   - other: anything that doesn't fit above

3. Identify any sub-issues (secondary concerns in the same ticket).
4. Identify MISSING INFORMATION needed to resolve the ticket (fields that are null/unknown in the order context or unclear in the ticket text).
5. If critical information is missing, generate UP TO 3 clarifying questions.

IMPORTANT RULES:
- Only flag information as missing if it would materially change the resolution.
- Do NOT ask for information already present in the order context.
- Flag tickets as high priority if: fraud suspected, item value > $500, customer mentions legal action.
- Flag tickets as urgent if: safety concern, unauthorized account access, or potential data breach.
- Output ONLY valid JSON matching the schema below — no markdown, no commentary.

OUTPUT SCHEMA:
{
  "issue_type": "<one of the enum values>",
  "confidence": <0.0 to 1.0>,
  "sub_issues": ["<string>", ...],
  "clarifying_questions": ["<question>", ...],  // max 3, empty if not needed
  "missing_fields": ["<field_name>", ...],
  "needs_clarification": <true|false>,
  "priority": "<low|normal|high|urgent>",
  "flags": ["<flag>", ...]  // e.g. ["fraud_risk", "high_value", "legal_threat", "perishable"]
}"""


def build_triage_prompt(ticket: SupportTicket) -> str:
    ctx = ticket.order_context
    order_info = f"""
ORDER CONTEXT:
- Order ID: {ctx.order_id}
- Order Date: {ctx.order_date}
- Delivery Date: {ctx.delivery_date or 'NOT YET DELIVERED / UNKNOWN'}
- Item: {ctx.item_name}
- Item Category: {ctx.item_category}
- Item Value: ${ctx.item_value:.2f}
- Order Status: {ctx.order_status.value}
- Fulfillment: {ctx.fulfillment_type.value}
- Shipping Region: {ctx.shipping_region}
- Payment Method: {ctx.payment_method or 'unknown'}
- Final Sale: {ctx.is_final_sale}
- Marketplace Order: {ctx.is_marketplace}
- Seller ID: {ctx.seller_id or 'N/A'}
- Membership Tier: {ctx.membership_tier or 'none'}
"""
    return f"""TICKET TEXT:
"{ticket.ticket_text}"

{order_info}

Classify this ticket and output JSON only."""


def run_triage_agent(ticket: SupportTicket) -> TriageResult:
    """
    Run the Triage Agent on a support ticket.
    Returns a TriageResult with classification, flags, and clarifying questions.
    """
    prompt = build_triage_prompt(ticket)
    raw = call_llm(
        system=TRIAGE_SYSTEM_PROMPT,
        user=prompt,
        temperature=0.1,
        max_tokens=800,
    )

    try:
        data = json.loads(_extract_json(raw))
        return TriageResult(
            issue_type           = IssueType(data.get("issue_type", "other")),
            confidence           = float(data.get("confidence", 0.7)),
            sub_issues           = data.get("sub_issues", []),
            clarifying_questions = data.get("clarifying_questions", [])[:3],
            missing_fields       = data.get("missing_fields", []),
            needs_clarification  = bool(data.get("needs_clarification", False)),
            priority             = data.get("priority", "normal"),
            flags                = data.get("flags", []),
        )
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        # Fallback: parse what we can
        print(f"[triage] JSON parse error: {e}\nRaw: {raw[:300]}")
        return TriageResult(
            issue_type          = IssueType.OTHER,
            confidence          = 0.5,
            needs_clarification = True,
            clarifying_questions= ["Could you describe your issue in more detail?"],
            flags               = ["parse_error"],
        )


def _extract_json(text: str) -> str:
    """Strip markdown fences and extract JSON from LLM output."""
    text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    # Find the first { ... } block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return match.group(0)
    return text