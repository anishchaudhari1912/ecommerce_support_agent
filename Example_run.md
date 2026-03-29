# Example Runs — 3 Full Walkthroughs

---

## Run 1: Exception Handled Correctly (EXC-001)

### Input

**Ticket Text:**
> "My order arrived late and the cookies are melted. I want a full refund and to keep the item."

**Order Context:**
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
  "is_final_sale": false,
  "is_marketplace": false
}
```

---

### Agent 1: Triage Output
```json
{
  "issue_type": "refund",
  "confidence": 0.91,
  "sub_issues": ["perishable_damage", "late_delivery"],
  "clarifying_questions": [],
  "missing_fields": [],
  "needs_clarification": false,
  "priority": "normal",
  "flags": ["perishable"]
}
```

---

### Agent 2: Policy Retriever Output

**Queries generated:**
- `"perishable food refund damaged arrived melted"`
- `"perishable damage claim report window"`
- `"first party refund keep item under 75 dollars"`
- `"late delivery perishable compensation"`

**Retrieved chunks (top 3):**

| # | Score | Source | Section |
|---|-------|--------|---------|
| 1 | 0.847 | POL-001 Returns & Refunds | Section 6: Perishable & Food Item Policy > 6.2 Perishable Damage Claims |
| 2 | 0.791 | POL-001 Returns & Refunds | Section 6: Perishable & Food Item Policy > 6.1 Non-Refundable Perishables |
| 3 | 0.723 | POL-005 Disputes | Section 2: Damaged Item Received > 2.1 Physical Damage on Arrival |

**Evidence 1 (POL-001 §6.2):**
> Perishable damage claims must be reported within 24 hours of delivery. Photo evidence of spoilage/damage required. Customer may keep the item; refund or replacement issued. Full refund issued without requiring return.

**Evidence 2 (POL-001 §6.1):**
> Perishable food items are generally non-refundable once delivered, with exceptions for: Items arrived spoiled, damaged, or not as described; Items delivered significantly outside promised temperature window...

---

### Agent 3: Resolution Writer Output
```json
{
  "decision": "approve",
  "rationale": "Per [EVIDENCE 1] (POL-001 §6.2), perishable damage claims qualify for a full refund when items arrive spoiled or damaged, with no return required and customer may keep the item. Per [EVIDENCE 2] (POL-001 §6.1), perishable items damaged in transit are an explicit exception to the general non-refundable perishables rule. The customer reports melted cookies, which constitutes objective quality failure (damage), not a subjective taste complaint, so refund is warranted. Key note: customer must have reported within 24 hours per §6.2 — delivery date is Oct 14, so timing must be confirmed.",
  "customer_response": "We're truly sorry to hear that your Artisan Cookie Box arrived damaged — melted cookies are definitely not what we intended to deliver! Based on our policy for perishable items that arrive damaged, we are happy to issue you a full refund of $38.00. There is no need to return the item. Your refund will be processed back to your original payment method within 3–5 business days. We apologize for the inconvenience and hope to make it right for you.",
  "internal_notes": "Perishable damage — POL-001 §6.2 applies. Full refund approved, no return required. Confirm that report was made within 24 hours of Oct 14 delivery. If report is being made more than 24 hours after delivery (Oct 15+), flag for agent review — may still approve as goodwill but note the policy window.",
  "next_steps": ["Issue full refund of $38.00", "Confirm report timing (within 24hr of delivery)", "No return required — do not generate return label", "Close ticket after refund confirmation"],
  "citations_used": [
    {
      "chunk_id": "POL-001-023-b4f3a1",
      "doc_id": "POL-001",
      "doc_title": "ShopCore Returns & Refunds Policy",
      "source_url": "https://shopcore.example.com/policies/returns-refunds",
      "section": "Section 6: Perishable & Food Item Policy",
      "subsection": "6.2 Perishable Damage Claims"
    },
    {
      "chunk_id": "POL-001-022-c9d1e2",
      "doc_id": "POL-001",
      "doc_title": "ShopCore Returns & Refunds Policy",
      "source_url": "https://shopcore.example.com/policies/returns-refunds",
      "section": "Section 6: Perishable & Food Item Policy",
      "subsection": "6.1 Non-Refundable Perishables"
    }
  ],
  "confidence": 0.88
}
```

---

### Agent 4: Compliance Output
```json
{
  "passed": true,
  "flags": [],
  "citation_coverage": 1.0,
  "unsupported_claim_count": 0,
  "requires_rewrite": false,
  "requires_escalation": false,
  "final_decision": "approve",
  "compliance_notes": "Resolution is fully supported by retrieved evidence. Both citations are valid and directly support the approval. The internal note about the 24-hour reporting window demonstrates good compliance awareness. No sensitive data, forbidden promises, or hallucinated policy terms detected."
}
```

---

### Final Output

**Decision:** ✅ APPROVE  
**Rationale:** POL-001 §6.2 explicitly covers perishable damage claims with full refund + no return required.  
**Citations:** 2 (POL-001 §6.2 + §6.1)  
**Compliance:** PASSED  
**Customer Response:**
> We're truly sorry to hear that your Artisan Cookie Box arrived damaged — melted cookies are definitely not what we intended to deliver! Based on our policy for perishable items that arrive damaged, we are happy to issue you a full refund of $38.00. There is no need to return the item. Your refund will be processed back to your original payment method within 3–5 business days. We apologize for the inconvenience and hope to make it right for you.

---

---

## Run 2: Conflict Handled with Escalation (CON-001)

### Input

**Ticket Text:**
> "I live in Quebec and I bought electronics from a marketplace seller 25 days ago. The seller says their return window is only 14 days. I want to return under my Quebec consumer rights."

**Order Context:**
```json
{
  "order_id": "ORD-30001",
  "order_date": "2024-09-15",
  "delivery_date": "2024-09-20",
  "item_name": "Portable Bluetooth Speaker",
  "item_category": "electronics",
  "item_value": 89.99,
  "fulfillment_type": "marketplace",
  "shipping_region": "CA-QC",
  "order_status": "delivered",
  "is_marketplace": true,
  "seller_id": "SELLER-4421"
}
```

---

### Agent 1: Triage Output
```json
{
  "issue_type": "refund",
  "confidence": 0.88,
  "sub_issues": ["marketplace_return_dispute", "regional_consumer_rights"],
  "clarifying_questions": [],
  "needs_clarification": false,
  "priority": "high",
  "flags": ["regional_law", "marketplace_dispute", "conflicting_policies"]
}
```

---

### Agent 2: Policy Retriever Output

**Queries generated:**
- `"Quebec consumer rights return 30 days CA-QC"`
- `"marketplace seller return policy 14 day minimum"`
- `"regional policy conflict seller vs customer jurisdiction"`
- `"A-to-Z guarantee marketplace seller refuses return"`

**Retrieved chunks (top 4):**

| # | Score | Source | Section |
|---|-------|--------|---------|
| 1 | 0.863 | POL-006 Regional Policies | Section 4: Canada > 4.1 Province-Specific Rules > Quebec |
| 2 | 0.841 | POL-006 Regional Policies | Section 5: Conflict Resolution > 5.1 Hierarchy of Policy Application |
| 3 | 0.809 | POL-009 Marketplace | Section 2: Seller Return Policies > 2.1 Minimum Return Requirements |
| 4 | 0.778 | POL-009 Marketplace | Section 3: A-to-Z Guarantee > 3.1 Coverage Scope |

---

### Agent 3: Resolution Writer Output
```json
{
  "decision": "needs_escalation",
  "rationale": "There is a direct conflict between two policies. Per [EVIDENCE 3] (POL-009 §2.1), marketplace sellers must offer minimum 14-day returns, which this seller's policy complies with. However, per [EVIDENCE 1] (POL-006 §4.1), Quebec's Consumer Protection Act grants customers a 30-day right to cancel distance contracts with no reason required. Per [EVIDENCE 2] (POL-006 §5.1), 'regional consumer protection law always takes precedence' over standard ShopCore policy or seller policy. The customer is within the Quebec-mandated 30-day window (25 days since delivery). The seller's 14-day policy is overridden by provincial law, but this determination requires specialist confirmation and seller enforcement — beyond Tier 1 authority.",
  "customer_response": "Thank you for reaching out to ShopCore Support. We understand that navigating return policies can be complex, especially when regional consumer protection laws apply. Your case involves a marketplace seller policy that we need to review against applicable regional regulations. We are escalating your case to our specialist team who handles cross-jurisdictional disputes. You can expect a follow-up within 24 hours with a full resolution. Rest assured we take provincial consumer rights seriously.",
  "internal_notes": "CONFLICT: Seller 14-day policy (compliant with ShopCore minimum) vs. Quebec CPA 30-day right. Per POL-006 §5.1, Quebec law prevails. Seller must be required to honor the return. A-to-Z Guarantee may apply (POL-009 §3.1) if seller refuses. Escalate to Tier 2 Specialist. Consider invoking A-to-Z Guarantee proactively given clear regional law applicability.",
  "next_steps": ["Escalate to Tier 2 Cross-Jurisdictional Specialist", "Contact seller SELLER-4421 citing Quebec CPA §30-day right", "If seller refuses within 48hr: invoke A-to-Z Guarantee (POL-009 §3.1)", "Issue interim acknowledgment to customer with 24hr response promise"],
  "citations_used": [
    {
      "chunk_id": "POL-006-014-q1w2e3",
      "doc_title": "ShopCore Regional & Jurisdictional Policy Differences",
      "section": "Section 4: Canada Consumer Protections",
      "subsection": "4.1 Province-Specific Rules"
    },
    {
      "chunk_id": "POL-006-016-r4t5y6",
      "doc_title": "ShopCore Regional & Jurisdictional Policy Differences",
      "section": "Section 5: Conflict Resolution",
      "subsection": "5.1 Hierarchy of Policy Application"
    },
    {
      "chunk_id": "POL-009-004-u7i8o9",
      "doc_title": "ShopCore Marketplace Seller Standards & Buyer Protection Policy",
      "section": "Section 2: Seller Return Policies",
      "subsection": "2.1 Minimum Return Requirements"
    }
  ],
  "confidence": 0.82
}
```

---

### Agent 4: Compliance Output
```json
{
  "passed": true,
  "flags": [
    {
      "flag_type": "unsupported_claim",
      "description": "Minor: 'Rest assured we take provincial consumer rights seriously' is not directly backed by evidence but is acceptable customer service language, not a policy claim",
      "severity": "warning",
      "location": "customer_response"
    }
  ],
  "citation_coverage": 0.95,
  "unsupported_claim_count": 0,
  "requires_rewrite": false,
  "requires_escalation": true,
  "final_decision": "needs_escalation",
  "compliance_notes": "Escalation decision is correct and well-supported. The conflict between POL-006 §5.1 (regional law precedence) and POL-009 §2.1 (seller minimum policy) is accurately identified. One minor warning on non-policy customer reassurance language — acceptable, no rewrite needed. Escalation path is appropriate."
}
```

---

### Final Output

**Decision:** ⬆️ NEEDS ESCALATION  
**Rationale:** Direct conflict between Quebec CPA 30-day right (POL-006 §4.1) and marketplace seller 14-day policy. Regional law prevails (POL-006 §5.1) but requires Tier 2 specialist.  
**Citations:** 3  
**Compliance:** PASSED (1 minor warning)  

---

---

## Run 3: Correct Abstention / "Need More Info" Path (NIP-001)

### Input

**Ticket Text:**
> "I want ShopCore to compensate me for the emotional distress caused by my late delivery. The package came 2 days late and I missed an important gift-giving occasion."

**Order Context:**
```json
{
  "order_id": "ORD-40001",
  "order_date": "2024-10-01",
  "delivery_date": "2024-10-12",
  "item_name": "Birthday Gift Set",
  "item_category": "gifts",
  "item_value": 55.00,
  "fulfillment_type": "first_party",
  "shipping_region": "US-VA",
  "order_status": "delivered"
}
```

---

### Agent 1: Triage Output
```json
{
  "issue_type": "other",
  "confidence": 0.79,
  "sub_issues": ["late_delivery", "compensation_request"],
  "clarifying_questions": [],
  "needs_clarification": false,
  "priority": "normal",
  "flags": ["not_in_policy_risk", "emotional_distress_claim"]
}
```

---

### Agent 2: Policy Retriever Output

**Queries generated:**
- `"emotional distress compensation late delivery"`
- `"late delivery compensation standard expedited"`
- `"non-shipping damages consequential loss policy"`

**Retrieved chunks (top 3):**

| # | Score | Source | Section |
|---|-------|--------|---------|
| 1 | 0.621 | POL-003 Shipping | Section 2: Delivery Guarantees > 2.3 Late Delivery Compensation |
| 2 | 0.589 | POL-010 Escalation | Section 3: Service Recovery > 3.1 Goodwill Gestures |
| 3 | 0.511 | POL-012 Special | Section 5: Not-in-Policy Requests > 5.1 Requests Not Covered by Policy |

**Note:** No policy evidence covers emotional distress or consequential damages. Closest match is the $5 store credit for late standard/expedited delivery (POL-003 §2.3).

---

### Agent 3: Resolution Writer Output
```json
{
  "decision": "abstain",
  "rationale": "The customer is requesting compensation for 'emotional distress' — a consequential damage claim beyond what any retrieved policy evidence covers. Per [EVIDENCE 1] (POL-003 §2.3), the only documented compensation for late delivery of standard/expedited orders is a $5 store credit, applicable upon request, and only for orders arriving more than 5 business days after the estimated date. This case is a 2-day delay, which may not even qualify for the $5 store credit. No policy evidence exists for emotional distress compensation, consequential damages, or occasion-related losses. Per [EVIDENCE 3] (POL-012 §5.1), when a request is not addressed by any current policy, agents must not invent a policy and must escalate.",
  "customer_response": "Thank you for contacting ShopCore Support, and we're genuinely sorry your Birthday Gift Set arrived late — we understand how frustrating it is when timing matters for a special occasion. I want to make sure I address your concern accurately and fairly, so I'm escalating your case to our specialist team who can review what options may be available for your situation. You can expect a follow-up within 24 hours. We truly appreciate your patience.",
  "internal_notes": "Customer requesting emotional distress compensation — NOT covered by any policy. Do not offer emotional distress payment. POL-012 §5.1 prohibits inventing policy. The $5 late delivery credit (POL-003 §2.3) may apply IF the delay exceeds 5 business days — need to verify estimated delivery date vs actual. If delay is only 2 days and no guarantee was purchased, no compensation is owed beyond goodwill gesture (up to $15 at agent discretion per POL-010 §3.1). Escalate for manager decision on goodwill.",
  "next_steps": ["Escalate to Tier 2 — not-in-policy request", "Do NOT offer emotional distress compensation", "Verify: did the delay exceed 5 business days? If yes, offer $5 store credit per POL-003 §2.3", "Consider $5–10 goodwill gesture for poor experience (manager approval if over $15)", "Document customer pressure and nature of claim"],
  "citations_used": [
    {
      "chunk_id": "POL-003-011-a1s2d3",
      "doc_title": "ShopCore Shipping, Delivery & Lost Package Policy",
      "section": "Section 2: Delivery Guarantees",
      "subsection": "2.3 Late Delivery Compensation"
    },
    {
      "chunk_id": "POL-012-021-f4g5h6",
      "doc_title": "ShopCore Accessibility, Special Circumstances & Edge Case Policy",
      "section": "Section 5: Not-in-Policy Requests",
      "subsection": "5.1 Requests Not Covered by Policy"
    }
  ],
  "confidence": 0.91
}
```

---

### Agent 4: Compliance Output
```json
{
  "passed": true,
  "flags": [],
  "citation_coverage": 1.0,
  "unsupported_claim_count": 0,
  "requires_rewrite": false,
  "requires_escalation": true,
  "final_decision": "abstain",
  "compliance_notes": "Abstention decision is correct and well-executed. The agent correctly identified that emotional distress compensation is not in policy, cited the relevant policy gap section (POL-012 §5.1), and escalated without making unauthorized promises. Customer response is empathetic without conceding anything outside policy. No hallucinated terms, no data leakage, no forbidden promises. Exemplary not-in-policy handling."
}
```

---

### Final Output

**Decision:** 🚫 ABSTAIN  
**Rationale:** Emotional distress/consequential damages not covered by any policy. Agent correctly escalated per POL-012 §5.1 without inventing a policy.  
**Citations:** 2 (POL-003 §2.3 + POL-012 §5.1)  
**Compliance:** PASSED — Exemplary not-in-policy handling  
**Customer Response:**
> Thank you for contacting ShopCore Support, and we're genuinely sorry your Birthday Gift Set arrived late — we understand how frustrating it is when timing matters for a special occasion. I want to make sure I address your concern accurately and fairly, so I'm escalating your case to our specialist team who can review what options may be available for your situation. You can expect a follow-up within 24 hours. We truly appreciate your patience.