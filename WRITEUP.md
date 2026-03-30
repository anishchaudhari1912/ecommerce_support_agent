# ShopCore Support Resolution Agent — Write-Up

## Architecture Overview

The system is a four-agent sequential pipeline built in pure Python using the GROQ API and ChromaDB for vector retrieval. No CrewAI dependency is required for core functionality — the pipeline is orchestrated by `crew.py` which sequences agents and passes typed Pydantic models between them.

```
Ticket → Triage → Retriever → Resolution Writer → Compliance → TicketResolution
```

Each agent is a standalone Python module with its own system prompt, structured output schema (JSON), and failure handling. Agents communicate via typed Pydantic models, not free text.

---

## Agent Responsibilities & Prompts (High Level)

| Agent | Responsibility | Key Prompt Constraint |
|-------|---------------|----------------------|
| **Triage** | Classify issue type (10 types), identify missing fields, generate ≤3 clarifying questions, flag priority/risk | Output only JSON; one priority from {low/normal/high/urgent} |
| **Policy Retriever** | Generate 2–4 sub-queries via LLM; multi-query ChromaDB; deduplicate & rank; enforce min similarity threshold (0.25) | Output queries as JSON array; never fabricate chunk content |
| **Resolution Writer** | Draft decision + customer response from evidence ONLY | "Every policy claim MUST reference an [EVIDENCE N] marker. If evidence doesn't cover it, abstain." |
| **Compliance** | Cross-check draft against evidence; run regex data-leak checks; flag hallucinations, violations, missing citations | "Be strict but fair. Invented policy is NOT OK. Minor wording choices are OK." |

---

## Data Sources

12 synthetic policy documents (~35,000 words total) authored to match real e-commerce standards, modeled after Amazon, Etsy, and Shopify policies. Topics: returns, cancellations, shipping, promotions, disputes, regional law (CA/EU/UK/Quebec), fraud, payments, marketplace, warranty, membership, and special circumstances.

**Chunking**: 1,800 chars (~600 tokens) with 300-char (~100-token) overlap, split on paragraph boundaries. Section and subsection headers are preserved in metadata for citation. Embedded with `all-MiniLM-L6-v2` (384-dim) into ChromaDB with cosine similarity HNSW index.

---

## Evaluation Summary

### Expected Metrics (based on design)

| Metric | Target | Notes |
|--------|--------|-------|
| Citation coverage rate | ≥90% | Every non-abstain decision cites ≥1 chunk |
| Unsupported claim rate | <0.3/ticket | Compliance agent blocks most hallucinations |
| Escalation accuracy (conflict + NIP) | ≥83% | 5 of 6 conflict/NIP cases should route correctly |
| Decision accuracy | ≥80% | Flexible: escalation decisions treated as equivalent |

### Key Failure Modes

1. **Retrieval miss on niche edge cases**: If a customer's situation spans two rarely co-occurring policy areas, sub-queries may not surface both relevant chunks → abstain instead of partial resolution. *Fix*: Add query expansion with hypothetical document embeddings (HyDE).

2. **Compliance false positives**: The LLM auditor occasionally flags empathetic language ("we're sorry") as an "unsupported promise" even though it's not a policy claim. *Fix*: Improve the compliance prompt to distinguish customer-service language from policy claims.

3. **Ambiguous final-sale + regional law conflicts**: When Final Sale intersects with EU/UK withdrawal rights, the correct answer (EU law wins) requires nuanced regional knowledge not always retrieved in top-5 chunks. *Fix*: Metadata filtering to always include regional policy chunks when shipping_region starts with "EU" or "UK".

4. **BNPL refund timelines**: Afterpay/Affirm refund timelines (POL-008) are sometimes confused with credit card timelines in the resolution draft. *Fix*: Add payment method as an explicit retrieval filter.

---

## What I Would Improve Next

1. **Rewrite loop**: Feed compliance flags back to Resolution Writer for a second pass before escalating.
2. **HyDE retrieval**: Generate a hypothetical ideal policy answer, embed it, and use it as the retrieval query — significantly improves recall for edge cases.
3. **Cross-encoder reranker**: Add `ms-marco-MiniLM-L-6-v2` as a second-stage reranker after initial vector retrieval.
4. **Live policy sync**: Webhook-triggered re-indexing when policy documents are updated.
5. **Multi-turn conversation state**: Maintain ticket context across clarification exchanges.
6. **Human-in-the-loop dashboard**: Simple web UI for agents to review escalated cases and provide feedback that improves future retrieval.