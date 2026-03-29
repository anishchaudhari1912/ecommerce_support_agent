"""
ShopCore Support Resolution Crew
=================================
Orchestrates the four-agent pipeline:

  SupportTicket
      │
      ▼
  ┌─────────────┐
  │ Triage Agent│  → classifies issue, flags missing info, asks clarifying Qs
  └──────┬──────┘
         │ TriageResult
         ▼
  ┌─────────────────────┐
  │ Policy Retriever    │  → multi-query vector search, returns ranked citations
  └──────┬──────────────┘
         │ PolicyRetrievalResult
         ▼
  ┌─────────────────────┐
  │ Resolution Writer   │  → evidence-only draft with decision + customer response
  └──────┬──────────────┘
         │ ResolutionDraft
         ▼
  ┌─────────────────────┐
  │ Compliance Agent    │  → audits draft, may force rewrite or escalation
  └──────┬──────────────┘
         │ ComplianceResult
         ▼
  TicketResolution  (final structured output)

If needs_clarification is True, the pipeline short-circuits after Triage
and returns a TicketResolution with clarifying questions only.
"""

from __future__ import annotations
import time
from pathlib import Path
from typing import Optional

import chromadb
from sentence_transformers import SentenceTransformer

from utils.models import (
    SupportTicket, TicketResolution, Decision,
    ComplianceFlag, Citation
)
from agents.triage_agent             import run_triage_agent
from agents.retriever_agent          import run_policy_retriever_agent
from agents.resolution_writer_agent  import run_resolution_writer_agent
from agents.compliance_agent         import run_compliance_agent
from agents.order_context_agent      import run_order_context_interpreter, OrderContextResult
from ingestion.ingestion              import build_index, get_collection, get_embedding_model, CHROMA_DIR


class SupportResolutionCrew:
    """
    Multi-agent pipeline for resolving e-commerce support tickets.
    Instantiate once and call .resolve(ticket) per ticket.
    """

    def __init__(self, chroma_dir: Path = CHROMA_DIR):
        print("[crew] Initializing SupportResolutionCrew…")
        self.collection = build_index()
        self.embed_model = get_embedding_model()
        print("[crew] Ready.")

    def resolve(self, ticket: SupportTicket, verbose: bool = True) -> TicketResolution:
        """
        Run the full 4-agent pipeline for a support ticket.

        Args:
            ticket:  SupportTicket with ticket_text and order_context.
            verbose: Print step-by-step progress.

        Returns:
            TicketResolution with all structured fields populated.
        """
        t0 = time.time()
        if verbose:
            print(f"\n{'='*60}")
            print(f"[crew] Processing ticket: {ticket.ticket_id}")
            print(f"  Ticket: {ticket.ticket_text[:100]}…")
            print(f"{'='*60}")

        # ── Step 0: Order Context Interpreter ──────────────────
        if verbose: print("\n[0/4] Running Order Context Interpreter…")
        ctx_result = run_order_context_interpreter(ticket)
        # Use normalized ticket for all downstream agents
        from utils.models import SupportTicket as ST
        ticket = ST(
            ticket_id    = ticket.ticket_id,
            ticket_text  = ticket.ticket_text,
            order_context= ctx_result.normalized_ctx,
        )
        if verbose:
            print(f"  → Category normalised: {ctx_result.original_ctx.item_category!r} → {ctx_result.normalized_ctx.item_category!r}")
            print(f"  → Fraud risk: {ctx_result.fraud_risk_level}")
            print(f"  → {ctx_result.derived.summary().splitlines()[0]}")
            if ctx_result.fraud_signals:
                for s in ctx_result.fraud_signals:
                    print(f"     [FRAUD/{s.severity.upper()}] {s.code}: {s.description}")
            if ctx_result.validation_errors:
                for e in ctx_result.validation_errors:
                    print(f"     [VALIDATION] {e.field}: {e.message}")

        # Block processing if critical validation errors found
        if ctx_result.has_critical_errors:
            if verbose: print("  [crew] Critical validation errors — blocking processing.")
            return TicketResolution(
                ticket_id            = ticket.ticket_id,
                classification       = {"issue_type": "other", "confidence": 0.0, "flags": ["critical_validation_error"]},
                clarifying_questions = ["Could you please provide your order number so we can look up your order?"],
                decision             = Decision.NEEDS_INFO,
                rationale            = "Critical order context validation errors prevent processing.",
                citations            = [],
                customer_response    = (
                    "Thank you for reaching out to ShopCore Support! To help you effectively, "
                    "we need a bit more information. Could you please provide your order number "
                    "and any relevant details? Once we have that, we'll get right on it."
                ),
                next_steps           = ["Obtain valid order ID from customer", "Re-process ticket"],
                internal_notes       = f"Validation errors: {[e.to_dict() for e in ctx_result.validation_errors]}",
                compliance_passed    = True,
                compliance_flags     = [],
                metadata             = {
                    "elapsed_seconds":     round(time.time() - t0, 2),
                    "validation_errors":   [e.to_dict() for e in ctx_result.validation_errors],
                    "fraud_signals":       [s.to_dict() for s in ctx_result.fraud_signals],
                },
            )

        # ── Step 1: Triage ─────────────────────────────────────
        if verbose: print("\n[1/4] Running Triage Agent…")
        triage = run_triage_agent(ticket)
        if verbose:
            print(f"  → Issue: {triage.issue_type.value} ({triage.confidence:.0%})")
            print(f"  → Priority: {triage.priority}")
            print(f"  → Flags: {triage.flags}")
            print(f"  → Needs clarification: {triage.needs_clarification}")

        # Short-circuit: return clarifying questions only
        if triage.needs_clarification and triage.clarifying_questions:
            if verbose:
                print("  [crew] Clarification needed — short-circuiting pipeline.")
            return TicketResolution(
                ticket_id            = ticket.ticket_id,
                classification       = {
                    "issue_type": triage.issue_type.value,
                    "confidence": triage.confidence,
                    "sub_issues": triage.sub_issues,
                    "priority":   triage.priority,
                    "flags":      triage.flags,
                },
                clarifying_questions = triage.clarifying_questions,
                decision             = Decision.NEEDS_INFO,
                rationale            = "Insufficient information to determine resolution. Clarifying questions generated.",
                citations            = [],
                customer_response    = self._format_clarification_response(
                    ticket, triage.clarifying_questions
                ),
                next_steps           = ["Await customer response to clarifying questions", "Re-process ticket once information received"],
                internal_notes       = f"Missing fields: {triage.missing_fields}. Awaiting customer input.",
                compliance_passed    = True,
                compliance_flags     = [],
                metadata             = {"elapsed_seconds": round(time.time() - t0, 2)},
            )

        # ── Step 2: Policy Retrieval ────────────────────────────
        if verbose: print("\n[2/4] Running Policy Retriever Agent…")
        retrieval = run_policy_retriever_agent(
            ticket, triage, self.embed_model, self.collection
        )
        if verbose:
            print(f"  → {retrieval.evidence_count} chunks retrieved")
            print(f"  → Sufficient: {retrieval.sufficient}")
            for c in retrieval.chunks[:3]:
                print(f"     [{c.score:.3f}] {c.doc_title} | {c.subsection}")

        # ── Step 3: Resolution Writer ───────────────────────────
        if verbose: print("\n[3/4] Running Resolution Writer Agent…")
        draft = run_resolution_writer_agent(ticket, triage, retrieval)
        if verbose:
            print(f"  → Decision: {draft.decision.value}")
            print(f"  → Confidence: {draft.confidence:.0%}")
            print(f"  → Citations: {len(draft.citations_used)}")

        # ── Step 4: Compliance Check ────────────────────────────
        if verbose: print("\n[4/4] Running Compliance Agent…")
        compliance = run_compliance_agent(ticket, triage, retrieval, draft)
        if verbose:
            print(f"  → Passed: {compliance.passed}")
            print(f"  → Final decision: {compliance.final_decision.value}")
            print(f"  → Flags: {len(compliance.flags)}")
            for f in compliance.flags:
                print(f"     [{f.severity.upper()}] {f.flag_type}: {f.description[:80]}")

        # If compliance forces escalation, override customer response
        customer_response = draft.customer_response
        if compliance.requires_escalation and compliance.final_decision == Decision.NEEDS_ESCALATION:
            customer_response = self._escalation_response(ticket)

        elapsed = round(time.time() - t0, 2)
        if verbose:
            print(f"\n[crew] Completed in {elapsed}s")

        return TicketResolution(
            ticket_id            = ticket.ticket_id,
            classification       = {
                "issue_type": triage.issue_type.value,
                "confidence": triage.confidence,
                "sub_issues": triage.sub_issues,
                "priority":   triage.priority,
                "flags":      triage.flags,
            },
            clarifying_questions = triage.clarifying_questions,
            decision             = compliance.final_decision,
            rationale            = draft.rationale,
            citations            = draft.citations_used,
            customer_response    = customer_response,
            next_steps           = draft.next_steps,
            internal_notes       = (
                draft.internal_notes
                + (f"\n[COMPLIANCE] {compliance.compliance_notes}" if compliance.compliance_notes else "")
            ),
            compliance_passed    = compliance.passed,
            compliance_flags     = compliance.flags,
            metadata             = {
                "elapsed_seconds":       elapsed,
                "evidence_count":        retrieval.evidence_count,
                "citation_coverage":     compliance.citation_coverage,
                "requires_rewrite":      compliance.requires_rewrite,
                "requires_escalation":   compliance.requires_escalation,
                "draft_confidence":      draft.confidence,
                "goodwill_offered":      draft.goodwill_offered,
                "queries_used":          retrieval.query_used,
                "fraud_risk_level":      ctx_result.fraud_risk_level,
                "fraud_signals":         [s.to_dict() for s in ctx_result.fraud_signals],
                "derived_context":       ctx_result.derived.to_dict(),
            },
        )

    def _format_clarification_response(
        self, ticket: SupportTicket, questions: list[str]
    ) -> str:
        qs = "\n".join(f"  {i+1}. {q}" for i, q in enumerate(questions))
        return (
            f"Thank you for contacting ShopCore Support! I'd be happy to help with your request. "
            f"To make sure I resolve this correctly, could you please clarify a few things?\n\n"
            f"{qs}\n\n"
            f"Once I have this information, I'll be able to assist you right away."
        )

    def _escalation_response(self, ticket: SupportTicket) -> str:
        return (
            "Thank you for reaching out to ShopCore Support. We've received your request and "
            "are escalating it to our specialist team to ensure you receive the most accurate "
            "resolution. You can expect a follow-up from us within 24–48 hours. "
            "We appreciate your patience and apologize for any inconvenience."
        )