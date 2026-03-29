"""
Compliance / Safety Agent
==========================
Reviews the resolution draft for:
- Unsupported claims (policy statements not backed by citations)
- Missing or weak citations
- Policy violations (offering something policy explicitly prohibits)
- Sensitive data leakage (card numbers, SSN, other PII)
- Hallucinations (invented policy terms, made-up timeframes)

Can force a rewrite, trigger escalation, or block the response entirely.
This is the final gate before the resolution is delivered to the customer.
"""

from __future__ import annotations
import json
import re
from typing import List

from utils.models import (
    SupportTicket, TriageResult, PolicyRetrievalResult,
    ResolutionDraft, ComplianceResult, ComplianceFlag, Decision
)
from utils.llm_client import call_llm
from agents.retriever_agent import format_evidence_for_llm


# ──────────────────────────────────────────────────────────────
# Hardcoded safety checks (deterministic, no LLM needed)
# ──────────────────────────────────────────────────────────────
SENSITIVE_PATTERNS = [
    (r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b", "credit_card_number"),
    (r"\b\d{3}[\s\-]?\d{2}[\s\-]?\d{4}\b",               "ssn"),
    (r"\bcvv\s*[:\-]?\s*\d{3,4}\b",                       "cvv"),
    (r"\bpassword\s*[:\-]\s*\S+",                          "password"),
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "email_address"),
]

FORBIDDEN_PROMISES = [
    ("i guarantee",               "Absolute guarantees are prohibited without policy backing"),
    ("we will always",            "Unconditional promises not permitted"),
    ("no questions asked",        "Blanket 'no questions asked' promise may exceed policy"),
    ("100% refund regardless",    "Unconditional refund promise may contradict final sale / perishable rules"),
    ("i promise you",             "Agent personal promises not permitted"),
]


def run_deterministic_checks(draft: ResolutionDraft) -> List[ComplianceFlag]:
    """Run fast, rule-based checks that don't need an LLM."""
    flags: List[ComplianceFlag] = []
    full_text = (draft.customer_response + " " + draft.rationale).lower()

    # Check sensitive data patterns
    for pattern, label in SENSITIVE_PATTERNS:
        if re.search(pattern, full_text, re.IGNORECASE):
            flags.append(ComplianceFlag(
                flag_type   = "data_leak",
                description = f"Potential sensitive data ({label}) found in response",
                severity    = "critical",
                location    = "customer_response",
            ))

    # Check forbidden promises
    for phrase, reason in FORBIDDEN_PROMISES:
        if phrase in full_text:
            flags.append(ComplianceFlag(
                flag_type   = "policy_violation",
                description = f"Forbidden promise detected: '{phrase}'. {reason}",
                severity    = "error",
                location    = "customer_response",
            ))

    # Check citation presence
    if not draft.citations_used and draft.decision not in (Decision.ABSTAIN, Decision.NEEDS_INFO):
        flags.append(ComplianceFlag(
            flag_type   = "missing_citation",
            description = "Resolution makes no citations despite a concrete decision",
            severity    = "error",
            location    = "citations_used",
        ))

    # Low confidence + approve = risk
    if draft.decision == Decision.APPROVE and draft.confidence < 0.5:
        flags.append(ComplianceFlag(
            flag_type   = "unsupported_claim",
            description = f"Approval issued with low confidence ({draft.confidence:.0%}). Requires review.",
            severity    = "warning",
            location    = "decision",
        ))

    return flags


COMPLIANCE_SYSTEM_PROMPT = """You are a Compliance & Safety Auditor for ShopCore customer support.

Your job is to review a resolution draft against the retrieved policy evidence and check for:
1. UNSUPPORTED CLAIMS: Policy statements in the draft not backed by any evidence chunk.
2. HALLUCINATIONS: Made-up timeframes, amounts, procedures, or policy rules not found in evidence.
3. MISSING CITATIONS: Concrete policy claims that lack citation to a specific evidence chunk.
4. POLICY VIOLATIONS: The draft promises something the policy explicitly prohibits (e.g., refund on a final-sale item that policy says is non-returnable).
5. DATA LEAKAGE: Any PII, payment details, or other customer's data exposed in the draft.

RULES:
- Be strict but fair. Minor wording choices are OK. Invented policy is NOT OK.
- If the draft says "within 30 days" and evidence confirms 30 days → OK.
- If the draft says "within 45 days" but evidence says 30 days → flag as hallucination.
- If the draft approves a refund for a final-sale item that evidence says is non-refundable → flag as policy_violation.
- Consider whether escalation is required (conflicting policies, regional law, high-value claims).

OUTPUT FORMAT (JSON only):
{
  "passed": <true|false>,
  "flags": [
    {
      "flag_type": "<unsupported_claim|missing_citation|policy_violation|data_leak|hallucination>",
      "description": "<specific description>",
      "severity": "<warning|error|critical>",
      "location": "<which field: customer_response|rationale|citations_used|decision>"
    }
  ],
  "citation_coverage": <0.0 to 1.0>,
  "unsupported_claim_count": <integer>,
  "requires_rewrite": <true|false>,
  "requires_escalation": <true|false>,
  "final_decision": "<approve|deny|partial|needs_escalation|needs_more_information|abstain>",
  "compliance_notes": "<summary of what was checked and outcome>"
}"""


def build_compliance_prompt(
    ticket:    SupportTicket,
    retrieval: PolicyRetrievalResult,
    draft:     ResolutionDraft,
) -> str:
    evidence_text = format_evidence_for_llm(retrieval)
    citations_str = json.dumps(
        [c.model_dump() for c in draft.citations_used], indent=2
    ) if draft.citations_used else "[]"

    return f"""ORIGINAL TICKET: "{ticket.ticket_text}"

ORDER CONTEXT:
- Item: {ticket.order_context.item_name} ({ticket.order_context.item_category})
- Final Sale: {ticket.order_context.is_final_sale}
- Fulfillment: {ticket.order_context.fulfillment_type.value}
- Region: {ticket.order_context.shipping_region}
- Order Status: {ticket.order_context.order_status.value}
- Item Value: ${ticket.order_context.item_value:.2f}

{evidence_text}

RESOLUTION DRAFT TO AUDIT:
Decision: {draft.decision.value}
Confidence: {draft.confidence:.0%}
Rationale: {draft.rationale}
Customer Response: {draft.customer_response}
Internal Notes: {draft.internal_notes}
Citations Used: {citations_str}

Audit this draft against the retrieved evidence. Output JSON only."""


def run_compliance_agent(
    ticket:    SupportTicket,
    triage:    TriageResult,
    retrieval: PolicyRetrievalResult,
    draft:     ResolutionDraft,
) -> ComplianceResult:
    """
    Run compliance checks on the resolution draft.
    Returns ComplianceResult indicating whether the draft can proceed.
    """
    # Step 1: Deterministic rule-based checks (fast, no LLM)
    det_flags = run_deterministic_checks(draft)

    # Step 2: LLM-based semantic audit
    prompt = build_compliance_prompt(ticket, retrieval, draft)
    raw = call_llm(
        system      = COMPLIANCE_SYSTEM_PROMPT,
        user        = prompt,
        temperature = 0.1,
        max_tokens  = 1000,
    )

    try:
        data = json.loads(_extract_json(raw))
        llm_flags = [
            ComplianceFlag(
                flag_type   = f.get("flag_type", "unsupported_claim"),
                description = f.get("description", ""),
                severity    = f.get("severity", "warning"),
                location    = f.get("location", "unknown"),
            )
            for f in data.get("flags", [])
        ]

        all_flags = det_flags + llm_flags
        has_critical = any(f.severity == "critical" for f in all_flags)
        has_error    = any(f.severity == "error"    for f in all_flags)

        requires_rewrite    = data.get("requires_rewrite", False)    or has_critical or has_error
        requires_escalation = data.get("requires_escalation", False)

        # Final decision: compliance may override draft decision
        try:
            final_decision = Decision(data.get("final_decision", draft.decision.value))
        except ValueError:
            final_decision = draft.decision

        if requires_escalation and final_decision not in (
            Decision.NEEDS_ESCALATION, Decision.ABSTAIN
        ):
            final_decision = Decision.NEEDS_ESCALATION

        passed = not requires_rewrite and not has_critical

        return ComplianceResult(
            passed                  = passed,
            flags                   = all_flags,
            citation_coverage       = float(data.get("citation_coverage", 0.0)),
            unsupported_claim_count = int(data.get("unsupported_claim_count", 0)),
            requires_rewrite        = requires_rewrite,
            requires_escalation     = requires_escalation,
            final_decision          = final_decision,
            compliance_notes        = data.get("compliance_notes", ""),
        )

    except (json.JSONDecodeError, KeyError, ValueError) as e:
        print(f"[compliance] Parse error: {e}")
        # Conservative fallback: escalate
        return ComplianceResult(
            passed                  = False,
            flags                   = det_flags + [ComplianceFlag(
                flag_type   = "unsupported_claim",
                description = f"Compliance LLM parse error: {e}",
                severity    = "error",
                location    = "system",
            )],
            citation_coverage       = 0.0,
            unsupported_claim_count = 1,
            requires_rewrite        = True,
            requires_escalation     = True,
            final_decision          = Decision.NEEDS_ESCALATION,
            compliance_notes        = "Compliance check failed due to parse error; escalating as precaution.",
        )


def _extract_json(text: str) -> str:
    text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return match.group(0)
    return text