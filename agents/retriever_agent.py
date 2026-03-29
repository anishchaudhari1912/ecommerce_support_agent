"""
Policy Retriever Agent
======================
Queries the ChromaDB vector store to find relevant policy chunks for a given
support ticket. Returns ranked, cited excerpts with relevance scores.

Retrieval strategy:
- Generates multiple targeted sub-queries from the ticket context.
- Runs each sub-query independently for broader coverage.
- Deduplicates and re-ranks results.
- Sets a minimum evidence threshold (MIN_SCORE) before returning.
- All returned chunks carry full citation metadata.
"""

from __future__ import annotations
import json
import re
from typing import List, Dict, Any, Optional

import chromadb
from sentence_transformers import SentenceTransformer

from utils.models import (
    SupportTicket, TriageResult, PolicyRetrievalResult,
    PolicyChunk, Citation, IssueType
)
from utils.llm_client import call_llm
from ingestion.ingestion import retrieve


# ──────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────
TOP_K_PER_QUERY  = 5     # results per sub-query
MIN_SCORE        = 0.25  # minimum cosine similarity to include
MAX_CHUNKS       = 8     # max unique chunks to return
MIN_CHUNKS_FOR_DECISION = 2  # must have at least this many to proceed


QUERY_GENERATION_PROMPT = """You are a retrieval query specialist for an e-commerce policy knowledge base.

Given a customer support ticket and its classification, generate 2-4 focused search queries 
that will retrieve the most relevant policy sections from these policy documents:
- Returns & Refunds Policy (POL-001)
- Cancellations Policy (POL-002)
- Shipping & Delivery Policy (POL-003)
- Promotions & Coupons Policy (POL-004)
- Disputes Policy (POL-005)
- Regional Policies Policy (POL-006)
- Fraud & Security Policy (POL-007)
- Payment & Billing Policy (POL-008)
- Marketplace Policy (POL-009)
- Warranty & Escalation Policy (POL-010)
- Membership Policy (POL-011)
- Special Circumstances Policy (POL-012)

Rules:
- Each query should target a DIFFERENT aspect of the issue.
- Keep queries specific: include item category, fulfillment type, region if relevant.
- Queries should be 5-15 words.
- Output ONLY a JSON array of strings. No markdown, no explanation.

Example output:
["perishable food refund damaged arrived", "marketplace seller return policy 14 day minimum"]"""


def generate_retrieval_queries(ticket: SupportTicket, triage: TriageResult) -> List[str]:
    """Use LLM to generate targeted retrieval queries for the ticket."""
    prompt = f"""TICKET: "{ticket.ticket_text}"
ISSUE TYPE: {triage.issue_type.value}
ITEM CATEGORY: {ticket.order_context.item_category}
FULFILLMENT: {ticket.order_context.fulfillment_type.value}
REGION: {ticket.order_context.shipping_region}
FLAGS: {', '.join(triage.flags)}
IS FINAL SALE: {ticket.order_context.is_final_sale}

Generate 2-4 focused search queries to retrieve relevant policy sections."""

    raw = call_llm(
        system=QUERY_GENERATION_PROMPT,
        user=prompt,
        temperature=0.2,
        max_tokens=300,
    )

    try:
        raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
        queries = json.loads(raw)
        if isinstance(queries, list):
            return [str(q) for q in queries if q][:4]
    except Exception:
        pass

    # Fallback: build queries from ticket fields
    return _fallback_queries(ticket, triage)


def _fallback_queries(ticket: SupportTicket, triage: TriageResult) -> List[str]:
    """Build deterministic queries when LLM query generation fails."""
    ctx = ticket.order_context
    q = [
        f"{triage.issue_type.value} policy {ctx.item_category}",
        f"{ctx.item_category} return refund exception",
    ]
    if ctx.is_marketplace:
        q.append("marketplace seller A-to-Z guarantee")
    if ctx.shipping_region.startswith("EU") or ctx.shipping_region.startswith("UK"):
        q.append(f"regional policy {ctx.shipping_region} consumer rights")
    if ctx.is_final_sale:
        q.append("final sale non-returnable exception")
    return q[:4]


def run_policy_retriever_agent(
    ticket:     SupportTicket,
    triage:     TriageResult,
    model:      SentenceTransformer,
    collection: chromadb.Collection,
) -> PolicyRetrievalResult:
    """
    Retrieve relevant policy chunks for a ticket.

    Returns PolicyRetrievalResult with deduplicated, ranked chunks and citations.
    """
    queries = generate_retrieval_queries(ticket, triage)
    print(f"  [retriever] queries: {queries}")

    seen_ids: Dict[str, PolicyChunk] = {}

    for q in queries:
        hits = retrieve(q, model, collection, top_k=TOP_K_PER_QUERY)
        for h in hits:
            if h["score"] < MIN_SCORE:
                continue
            cid = h["chunk_id"]
            if cid not in seen_ids or h["score"] > seen_ids[cid].score:
                seen_ids[cid] = PolicyChunk(
                    chunk_id   = h["chunk_id"],
                    doc_id     = h["doc_id"],
                    doc_title  = h["doc_title"],
                    source_url = h["source_url"],
                    section    = h["section"],
                    subsection = h["subsection"],
                    text       = h["text"],
                    score      = h["score"],
                )

    # Sort by score descending, keep top MAX_CHUNKS
    ranked = sorted(seen_ids.values(), key=lambda c: c.score, reverse=True)[:MAX_CHUNKS]

    citations = [
        Citation(
            doc_id     = c.doc_id,
            doc_title  = c.doc_title,
            source_url = c.source_url,
            section    = c.section,
            subsection = c.subsection,
            chunk_id   = c.chunk_id,
        )
        for c in ranked
    ]

    sufficient = len(ranked) >= MIN_CHUNKS_FOR_DECISION

    return PolicyRetrievalResult(
        query_used     = " | ".join(queries),
        chunks         = ranked,
        citations      = citations,
        evidence_count = len(ranked),
        sufficient     = sufficient,
    )


def format_evidence_for_llm(retrieval: PolicyRetrievalResult) -> str:
    """Format retrieved chunks into a string suitable for LLM context."""
    if not retrieval.chunks:
        return "NO RELEVANT POLICY FOUND."

    lines = ["RETRIEVED POLICY EVIDENCE:\n"]
    for i, chunk in enumerate(retrieval.chunks, 1):
        lines.append(
            f"[EVIDENCE {i}]\n"
            f"Source: {chunk.doc_title} | {chunk.section} | {chunk.subsection}\n"
            f"Citation ID: {chunk.chunk_id}\n"
            f"Relevance Score: {chunk.score:.3f}\n"
            f"---\n{chunk.text}\n"
        )
    return "\n".join(lines)