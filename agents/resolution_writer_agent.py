"""
Resolution Writer Agent
=======================
Drafts the customer-facing response and internal resolution based ONLY on
retrieved policy evidence. Contains strict evidence-only generation rules.

Anti-hallucination controls:
- System prompt explicitly forbids claims not backed by evidence chunks.
- Every policy claim must reference a specific [EVIDENCE N] marker.
- If evidence is insufficient, the agent must output decision=ABSTAIN.
- Temperature is kept very low (0.1) to minimise creative drift.
"""

from __future__ import annotations
import json
import re
from typing import List

from utils.models import (
    SupportTicket, TriageResult, PolicyRetrievalResult,
    ResolutionDraft, Decision, Citation
)
from utils.llm_client import call_llm
from agents.retriever_agent import format_evidence_for_llm


RESOLUTION_SYSTEM_PROMPT = """You are a Resolution Writer Agent for ShopCore e-commerce customer support.

YOUR RULES (MUST FOLLOW — NO EXCEPTIONS):
1. EVIDENCE-ONLY: Every policy claim you make MUST reference an [EVIDENCE N] marker from the retrieved chunks provided to you. You CANNOT invent, guess, or extrapolate policy terms.
2. NO HALLUCINATION: If the evidence does not cover a specific aspect of the request, you MUST say "I don't have enough policy information to confirm this" — do NOT make up a policy.
3. ABSTAIN WHEN NEEDED: If evidence is insufficient to make a confident decision, output decision="abstain" and explain what policy information is missing.
4. CITATION REQUIRED: Include exact chunk_ids from the evidence in the citations_used list. Never cite a chunk you didn't actually use.
5. CUSTOMER TONE: The customer_response must be professional, empathetic, and clear. Do not use jargon. Do not expose internal notes to the customer.
6. DECISIONS:
   - "approve": Policy clearly supports the customer's request.
   - "deny": Policy clearly does not support the request; explain why.
   - "partial": Policy supports part of the request but not all.
   - "needs_escalation": Conflicting policies, regional laws, or amount > $500.
   - "needs_more_information": Critical info is missing to make a determination.
   - "abstain": No relevant policy found; cannot make a safe determination.

OUTPUT FORMAT (JSON only, no markdown, no explanation outside JSON):
{
  "decision": "<approve|deny|partial|needs_escalation|needs_more_information|abstain>",
  "rationale": "<internal explanation citing evidence numbers, 2-4 sentences>",
  "customer_response": "<customer-facing message, professional tone, 3-6 sentences>",
  "internal_notes": "<what the support agent should do next, escalation path if needed>",
  "next_steps": ["<action item>", ...],
  "citations_used": [
    {
      "chunk_id": "<exact chunk_id from evidence>",
      "doc_id": "<doc_id>",
      "doc_title": "<title>",
      "source_url": "<url>",
      "section": "<section>",
      "subsection": "<subsection>"
    }
  ],
  "confidence": <0.0 to 1.0>,
  "goodwill_offered": "<null or description of any goodwill gesture offered>"
}"""


def build_resolution_prompt(
    ticket:    SupportTicket,
    triage:    TriageResult,
    retrieval: PolicyRetrievalResult,
) -> str:
    ctx = ticket.order_context
    evidence_text = format_evidence_for_llm(retrieval)

    return f"""CUSTOMER SUPPORT TICKET
========================
Ticket ID: {ticket.ticket_id}
Ticket Text: "{ticket.ticket_text}"

ORDER CONTEXT:
- Order ID: {ctx.order_id}
- Order Date: {ctx.order_date}
- Delivery Date: {ctx.delivery_date or 'Unknown/Not yet delivered'}
- Item: {ctx.item_name} (Category: {ctx.item_category})
- Item Value: ${ctx.item_value:.2f}
- Order Status: {ctx.order_status.value}
- Fulfillment: {ctx.fulfillment_type.value}
- Shipping Region: {ctx.shipping_region}
- Final Sale: {ctx.is_final_sale}
- Marketplace Order: {ctx.is_marketplace}
- Membership: {ctx.membership_tier or 'none'}

TRIAGE CLASSIFICATION:
- Issue Type: {triage.issue_type.value} (confidence: {triage.confidence:.0%})
- Sub-issues: {', '.join(triage.sub_issues) or 'none'}
- Flags: {', '.join(triage.flags) or 'none'}

{evidence_text}

INSTRUCTIONS:
Using ONLY the evidence above, draft the resolution. Reference specific [EVIDENCE N] numbers in your rationale.
If evidence is insufficient or conflicting, set decision to "needs_escalation" or "abstain".
Output JSON only."""


def run_resolution_writer_agent(
    ticket:    SupportTicket,
    triage:    TriageResult,
    retrieval: PolicyRetrievalResult,
) -> ResolutionDraft:
    """
    Draft a policy-grounded resolution for the ticket.
    Returns ResolutionDraft with decision, rationale, customer response, and citations.
    """
    # Early exit: insufficient evidence
    if not retrieval.sufficient or not retrieval.chunks:
        return ResolutionDraft(
            decision          = Decision.ABSTAIN,
            rationale         = "Insufficient policy evidence retrieved to make a safe determination.",
            customer_response = (
                "Thank you for reaching out to ShopCore Support. I want to make sure "
                "I address your situation correctly. Your case requires review by a specialist "
                "who can look into the applicable policies in detail. We will follow up within "
                "24 hours with a resolution."
            ),
            internal_notes    = "No relevant policy chunks retrieved. Escalate to Tier 2 for manual policy review.",
            next_steps        = ["Escalate to Tier 2 specialist", "Manual policy lookup required"],
            citations_used    = [],
            confidence        = 0.1,
        )

    prompt = build_resolution_prompt(ticket, triage, retrieval)
    raw = call_llm(
        system      = RESOLUTION_SYSTEM_PROMPT,
        user        = prompt,
        temperature = 0.1,
        max_tokens  = 1500,
    )

    try:
        data = json.loads(_extract_json(raw))
        citations = [
            Citation(
                chunk_id   = c.get("chunk_id", ""),
                doc_id     = c.get("doc_id", ""),
                doc_title  = c.get("doc_title", ""),
                source_url = c.get("source_url", ""),
                section    = c.get("section", ""),
                subsection = c.get("subsection", ""),
            )
            for c in data.get("citations_used", [])
        ]
        return ResolutionDraft(
            decision          = Decision(data.get("decision", "abstain")),
            rationale         = data.get("rationale", ""),
            customer_response = data.get("customer_response", ""),
            internal_notes    = data.get("internal_notes", ""),
            next_steps        = data.get("next_steps", []),
            citations_used    = citations,
            confidence        = float(data.get("confidence", 0.5)),
            goodwill_offered  = data.get("goodwill_offered"),
        )
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        print(f"[resolution] Parse error: {e}\nRaw: {raw[:400]}")
        return ResolutionDraft(
            decision          = Decision.NEEDS_ESCALATION,
            rationale         = "Resolution writer encountered a parsing error. Manual review required.",
            customer_response = (
                "Thank you for contacting ShopCore Support. We are reviewing your case and "
                "will provide a full response within 24 hours."
            ),
            internal_notes    = f"LLM parse error in resolution writer: {e}",
            next_steps        = ["Escalate to Tier 2", "Manual resolution required"],
            citations_used    = [],
            confidence        = 0.0,
        )


def _extract_json(text: str) -> str:
    text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return match.group(0)
    return text