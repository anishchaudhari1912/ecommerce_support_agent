# ShopCore E-Commerce Support Resolution Agent

A multi-agent RAG system that resolves customer support tickets using policy documents with strong controls against hallucination, missing citations, and unsafe outputs.

---

## Architecture Overview

```
SupportTicket (ticket_text + OrderContext JSON)
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│  AGENT 1: Triage Agent                                          │
│  • Classifies issue type (refund/shipping/fraud/dispute/...)    │
│  • Identifies missing fields                                    │
│  • Generates ≤3 clarifying questions if needed                 │
│  • Flags priority + risk signals                                │
└──────────────────────┬──────────────────────────────────────────┘
                       │ TriageResult
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  AGENT 2: Policy Retriever Agent                                │
│  • Generates 2–4 targeted sub-queries via LLM                  │
│  • Queries ChromaDB (cosine similarity, top-5 per query)        │
│  • Deduplicates & re-ranks results                              │
│  • Returns citations (doc_id + section + chunk_id + URL)        │
└──────────────────────┬──────────────────────────────────────────┘
                       │ PolicyRetrievalResult
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  AGENT 3: Resolution Writer Agent                               │
│  • Evidence-only generation (no policy invented)                │
│  • References [EVIDENCE N] markers in rationale                 │
│  • Produces: decision, rationale, customer response, next steps │
│  • Abstains if evidence insufficient                            │
└──────────────────────┬──────────────────────────────────────────┘
                       │ ResolutionDraft
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  AGENT 4: Compliance / Safety Agent                             │
│  • Deterministic checks: data leakage, forbidden promises       │
│  • LLM audit: hallucinations, unsupported claims, violations    │
│  • Can force rewrite, escalation, or block response             │
│  • Outputs final compliance-cleared decision                    │
└──────────────────────┬──────────────────────────────────────────┘
                       │ TicketResolution (structured final output)
                       ▼
              Delivered to customer / agent
```

---

## Setup & Installation

### Prerequisites
- Python 3.10+
- Google Groq API key ( (https://console.groq.com/) )

### 1. Clone and install

```bash
git clone https://github.com/your-org/ecommerce-support-agent
cd ecommerce-support-agent
pip install -r requirements.txt
```

### 2. Configure API key

```bash
cp .env.example .env
# Edit .env and set: GROQ_API_KEY=your-key
# Optional: GROQ_MODEL=... (default is "llama-3.1-8b-instant",). 
```

Or export directly:
```bash
export GROQ_KEY=your-key
```

### 3. Build the policy index

```bash
python main.py index
```

This reads all 12 policy documents from `data/policies/`, chunks them, embeds with `all-MiniLM-L6-v2`, and stores in ChromaDB at `data/chroma_db/`.

---

## Usage

### Resolve a single test ticket

```bash
python main.py resolve --ticket EXC-001   # exception case: melted cookies
python main.py resolve --ticket CON-001   # conflict case: Quebec vs seller
python main.py resolve --ticket NIP-001   # not-in-policy: emotional distress
```

### Run full 20-ticket evaluation

```bash
python main.py eval
```

Outputs metrics table + saves JSON results to `evaluation/results/`.


### Run a custom ticket from JSON

```bash
python main.py custom --file examples/custom_ticket.json
```

---

## Input Format

### Ticket text (free-form string)
```
"My order arrived late and the cookies are melted. I want a full refund and to keep the item."
```

### Order context (JSON / Python dict)
```json
{
  "order_id": "ORD-20001",
  "order_date": "2024-10-08",
  "delivery_date": "2024-10-14",
  "item_name": "Artisan Cookie Box",
  "item_category": "perishable",
  "item_value": 38.00,
  "fulfillment_type": "first_party",
  "shipping_region": "US-AZ",
  "order_status": "delivered",
  "payment_method": "credit_card",
  "is_final_sale": false,
  "is_marketplace": false,
  "seller_id": null,
  "membership_tier": null
}
```

**`fulfillment_type`** values: `first_party` | `marketplace` | `fulfilled_by_shopcore`  
**`order_status`** values: `placed` | `processing` | `shipped` | `delivered` | `returned` | `cancelled`  
**`shipping_region`**: ISO-style codes: `US-CA`, `EU-DE`, `CA-QC`, `UK-GB`, etc.

---

## Output Format

Every ticket produces a `TicketResolution` with 7 required fields:

```json
{
  "ticket_id": "EXC-001",
  "classification": {
    "issue_type": "refund",
    "confidence": 0.92,
    "sub_issues": ["perishable_damage", "late_delivery"],
    "priority": "normal",
    "flags": ["perishable"]
  },
  "clarifying_questions": [],
  "decision": "approve",
  "rationale": "Per [EVIDENCE 1] (POL-001 §6.2), perishable items damaged in transit qualify for full refund and customer may keep the item...",
  "citations": [
    {
      "chunk_id": "POL-001-003-abc123",
      "doc_id": "POL-001",
      "doc_title": "ShopCore Returns & Refunds Policy",
      "source_url": "https://shopcore.example.com/policies/returns-refunds",
      "section": "Section 6: Perishable & Food Item Policy",
      "subsection": "6.2 Perishable Damage Claims"
    }
  ],
  "customer_response": "We're sorry to hear your cookie box arrived damaged...",
  "next_steps": ["Issue full refund", "Do not require item return"],
  "internal_notes": "Perishable damage confirmed. Value under $75, no return required.",
  "compliance_passed": true,
  "compliance_flags": []
}
```

---

## Project Structure

```
ecommerce-support-agent/
├── main.py                          # CLI entry point
├── crew.py                          # Orchestration pipeline
├── requirements.txt
├── .env.example
│
├── agents/
│   ├── triage_agent.py              # Agent 1: Classification & clarification
│   ├── retriever_agent.py           # Agent 2: Vector search & citation
│   ├── resolution_writer_agent.py   # Agent 3: Evidence-only draft
│   └── compliance_agent.py          # Agent 4: Audit & safety gate
│
├── ingestion/
│   └── ingestion.py                 # Chunking, embedding, ChromaDB indexing
│
├── utils/
│   ├── models.py                    # Pydantic data models
│   └── llm_client.py                # GROQ API wrapper
│
├── data/
│   ├── policies/                    # 12 policy markdown documents
│   │   ├── 01_returns_refunds_policy.md
│   │   ├── 02_cancellations_policy.md
│   │   ├── 03_shipping_delivery_policy.md
│   │   ├── 04_promotions_coupons_policy.md
│   │   ├── 05_disputes_policy.md
│   │   ├── 06_regional_policies.md
│   │   ├── 07_fraud_security_policy.md
│   │   ├── 08_payment_billing_policy.md
│   │   ├── 09_marketplace_policy.md
│   │   ├── 10_warranty_escalation_policy.md
│   │   ├── 11_membership_subscription_policy.md
│   │   └── 12_special_circumstances_policy.md
│   └── chroma_db/                   # Generated vector store (gitignored)
│
├── evaluation/
│   ├── run_evaluation.py            # Evaluation runner & metrics
│   └── results/                     # JSON results (gitignored)
│
├── tests/
│   └── test_tickets.py              # 20 test tickets (8+6+3+3)
│
└── examples/
    └── custom_ticket.json           # Example custom input
```

---

## Chunking Strategy

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Chunk size | ~1800 chars (~600 tokens) | Large enough to preserve full subsection context; small enough for precise retrieval |
| Overlap | ~300 chars (~100 tokens) | Prevents information loss at chunk boundaries, especially for numbered policy lists |
| Split preference | Paragraph > Sentence > Token | Preserves semantic units |
| Section tagging | Each chunk carries H2/H3 headers | Enables section-level citation |

**Embedding model**: `all-MiniLM-L6-v2` (384-dim, fast, accurate, MIT license)  
**Vector store**: ChromaDB (persistent, cosine similarity, HNSW index)  
**Top-k per query**: 5 | **Minimum similarity score**: 0.25 | **Max chunks returned**: 8

---

## Anti-Hallucination Controls

1. **Evidence-only generation prompt**: Resolution Writer is explicitly forbidden from stating policy not found in retrieved chunks.
2. **Evidence reference markers**: Writer must cite `[EVIDENCE N]` in rationale, tied to specific chunk IDs.
3. **Minimum evidence threshold**: Pipeline requires ≥2 chunks before proceeding; abstains if threshold not met.
4. **Compliance Auditor**: LLM auditor cross-checks every claim against retrieved evidence; flags unsupported statements.
5. **Deterministic pattern checks**: Regex checks for data leakage, forbidden promises — no LLM required.
6. **Low temperature**: All agents use temperature=0.1 to minimise creative drift.
7. **Abstain path**: If evidence doesn't cover the request → `decision=abstain`, escalate to human.

---

## Policy Corpus

12 synthetic policy documents authored to match real e-commerce standards:

| Doc ID | Title | Topics |
|--------|-------|--------|
| POL-001 | Returns & Refunds | Standard window, exceptions, perishables, final sale, hygiene, high-value |
| POL-002 | Cancellations | Pre/post-shipment, digital, subscriptions, marketplace |
| POL-003 | Shipping & Delivery | Options, guarantees, lost packages, regions |
| POL-004 | Promotions & Coupons | Stacking, price match, loyalty points, BOGO |
| POL-005 | Disputes | Wrong item, damage, SNAD, A-to-Z, chargeback |
| POL-006 | Regional Policies | CA, EU, UK, Canada, conflict hierarchy |
| POL-007 | Fraud & Security | Unauthorized charges, phishing, data protection |
| POL-008 | Payment & Billing | Methods, BNPL, refund timelines, billing errors |
| POL-009 | Marketplace | Seller standards, A-to-Z guarantee, fulfillment types |
| POL-010 | Warranty & Escalation | Manufacturer warranty, escalation paths, goodwill |
| POL-011 | Membership | Plus Standard/Prime, subscription boxes, gift memberships |
| POL-012 | Special Circumstances | Accessibility, bereavement, not-in-policy, pressure tactics |

**Sources**: Synthetic policy documents authored for this system, modeled after publicly available e-commerce policies from Amazon, Etsy, and Shopify (accessed 2024-03-28).

---

## Test Set & Evaluation

### 20-Ticket Test Set

| Category | Count | Tickets |
|----------|-------|---------|
| Standard | 8 | STD-001 through STD-008 |
| Exception-heavy | 6 | EXC-001 through EXC-006 |
| Conflict | 3 | CON-001 through CON-003 |
| Not-in-policy | 3 | NIP-001 through NIP-003 |

### Evaluation Metrics

| Metric | Definition |
|--------|-----------|
| **Citation coverage rate** | % of resolved tickets that include ≥1 citation |
| **Unsupported claim rate** | Avg. unsupported claims per ticket (manual rubric: any policy statement not in retrieved evidence) |
| **Correct escalation rate** | % of conflict/not-in-policy tickets correctly routed to escalation/abstain |
| **Decision accuracy** | % of tickets where actual decision matches expected (flexible: escalation decisions are equivalent) |

### Rubric for Unsupported Claims
A claim is "unsupported" if it:
- States a specific timeframe (e.g., "within 30 days") not found in retrieved chunks
- References a specific policy rule not present in the evidence
- Makes a promise (e.g., "full refund guaranteed") not backed by citations
- Invents a procedure not described in any policy document

---

## 3 Full Example Runs

See [EXAMPLE_RUNS.md](EXAMPLE_RUNS.md) for complete input/output for:
1. **EXC-001** — Perishable damage exception handled correctly
2. **CON-001** — Quebec law vs. marketplace seller conflict (escalation)
3. **NIP-001** — Emotional distress claim (correct abstention)

---

## What I Would Improve Next

1. **Human-in-the-loop for rewrites**: When compliance requires a rewrite, loop the Resolution Writer with compliance feedback instead of immediately escalating.
2. **Feedback loop**: Capture agent resolution outcomes and use them to fine-tune retrieval queries or re-rank chunks based on historical success.
3. **Real policy corpus**: Ingest live policy documents via URL/PDF pipeline with automatic re-indexing on policy updates.
4. **Streaming output**: Stream customer response tokens for real-time agent UI display.
5. **Multi-turn conversation**: Maintain ticket state across clarification turns instead of single-shot resolution.
6. **Confidence calibration**: Evaluate and calibrate confidence scores against human-labeled ground truth.
7. **CrewAI full integration**: Full CrewAI `Crew` + `Task` wiring for parallel agent execution and shared memory.
8. **Reranker model**: Add a cross-encoder reranker (e.g., `cross-encoder/ms-marco-MiniLM-L-6-v2`) to improve retrieval precision.

---

