"""
Shared data models for the E-Commerce Support Resolution Agent system.
"""

from __future__ import annotations
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────────────────────
class IssueType(str, Enum):
    REFUND    = "refund"
    SHIPPING  = "shipping"
    PAYMENT   = "payment"
    PROMO     = "promo"
    FRAUD     = "fraud"
    DISPUTE   = "dispute"
    CANCEL    = "cancellation"
    WARRANTY  = "warranty"
    ACCOUNT   = "account"
    OTHER     = "other"


class Decision(str, Enum):
    APPROVE           = "approve"
    DENY              = "deny"
    PARTIAL           = "partial"
    NEEDS_ESCALATION  = "needs_escalation"
    NEEDS_INFO        = "needs_more_information"
    ABSTAIN           = "abstain"


class FulfillmentType(str, Enum):
    FIRST_PARTY = "first_party"
    MARKETPLACE = "marketplace"
    FBS         = "fulfilled_by_shopcore"    # seller-listed, shopcore-shipped


class OrderStatus(str, Enum):
    PLACED    = "placed"
    PROCESSING = "processing"
    SHIPPED   = "shipped"
    DELIVERED = "delivered"
    RETURNED  = "returned"
    CANCELLED = "cancelled"


# ──────────────────────────────────────────────────────────────
# Input models
# ──────────────────────────────────────────────────────────────
class OrderContext(BaseModel):
    order_id:          str
    order_date:        str                      # ISO date string YYYY-MM-DD
    delivery_date:     Optional[str] = None
    item_category:     str                      # e.g. "perishable", "apparel", "electronics"
    item_name:         str
    item_value:        float
    fulfillment_type:  FulfillmentType
    shipping_region:   str                      # e.g. "US-CA", "EU-DE", "CA-QC"
    order_status:      OrderStatus
    payment_method:    Optional[str] = None
    is_final_sale:     bool = False
    is_marketplace:    bool = False
    seller_id:        Optional[str] = None
    membership_tier:   Optional[str] = None     # "plus_standard", "plus_prime", None


class SupportTicket(BaseModel):
    ticket_id:    str
    ticket_text:  str
    order_context: OrderContext


# ──────────────────────────────────────────────────────────────
# Order context interpreter (pre-triage normalization & validation)
# ──────────────────────────────────────────────────────────────
class FraudSignal(BaseModel):
    code: str
    description: str
    severity: str = "low"  # low | medium | high | critical

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class ValidationError(BaseModel):
    field: str
    message: str
    severity: str = "error"  # warning | error | critical

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class DerivedOrderContext(BaseModel):
    """Deterministic facts derived from dates and values for downstream agents."""
    days_since_order: Optional[int] = None
    days_since_delivery: Optional[int] = None
    is_high_value: bool = False
    category_normalized: str = ""
    item_value_usd: float = 0.0

    def summary(self) -> str:
        parts = [
            f"Category (normalized): {self.category_normalized or 'unknown'}",
            f"High-value order (≥$500): {self.is_high_value}",
        ]
        if self.days_since_delivery is not None:
            parts.append(f"Days since delivery: {self.days_since_delivery}")
        elif self.days_since_order is not None:
            parts.append(f"Days since order: {self.days_since_order}")
        return "\n".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class OrderContextResult(BaseModel):
    original_ctx: OrderContext
    normalized_ctx: OrderContext
    fraud_risk_level: str  # low | medium | high
    fraud_signals: List[FraudSignal] = Field(default_factory=list)
    validation_errors: List[ValidationError] = Field(default_factory=list)
    derived: DerivedOrderContext

    @property
    def has_critical_errors(self) -> bool:
        return any(e.severity == "critical" for e in self.validation_errors)


# ──────────────────────────────────────────────────────────────
# Agent output models
# ──────────────────────────────────────────────────────────────
class TriageResult(BaseModel):
    issue_type:           IssueType
    confidence:           float = Field(ge=0.0, le=1.0)
    sub_issues:           List[str] = Field(default_factory=list)
    clarifying_questions: List[str] = Field(default_factory=list)   # max 3
    missing_fields:       List[str] = Field(default_factory=list)
    needs_clarification:  bool = False
    priority:             str = "normal"   # "low" | "normal" | "high" | "urgent"
    flags:                List[str] = Field(default_factory=list)    # e.g. ["fraud_risk", "high_value"]


class PolicyChunk(BaseModel):
    chunk_id:   str
    doc_id:     str
    doc_title:  str
    source_url: str
    section:    str
    subsection: str
    text:       str
    score:      float


class Citation(BaseModel):
    doc_id:     str
    doc_title:  str
    source_url: str
    section:    str
    subsection: str
    chunk_id:   str


class PolicyRetrievalResult(BaseModel):
    query_used:      str
    chunks:          List[PolicyChunk]
    citations:       List[Citation]
    evidence_count:  int
    sufficient:      bool   # True if enough evidence to make a decision


class ResolutionDraft(BaseModel):
    decision:           Decision
    rationale:          str
    customer_response:  str
    internal_notes:     str
    next_steps:         List[str]
    citations_used:     List[Citation]
    confidence:         float = Field(ge=0.0, le=1.0)
    goodwill_offered:   Optional[str] = None


class ComplianceFlag(BaseModel):
    flag_type:   str    # "unsupported_claim" | "missing_citation" | "policy_violation" | "data_leak" | "hallucination"
    description: str
    severity:    str    # "warning" | "error" | "critical"
    location:    str    # which part of the response has the issue


class ComplianceResult(BaseModel):
    passed:                  bool
    flags:                   List[ComplianceFlag] = Field(default_factory=list)
    citation_coverage:       float = Field(ge=0.0, le=1.0)
    unsupported_claim_count: int = 0
    requires_rewrite:        bool = False
    requires_escalation:     bool = False
    final_decision:          Decision
    compliance_notes:        str


# ──────────────────────────────────────────────────────────────
# Final structured output
# ──────────────────────────────────────────────────────────────
class TicketResolution(BaseModel):
    ticket_id:             str
    classification:        Dict[str, Any]    # {issue_type, confidence, sub_issues}
    clarifying_questions:  List[str]
    decision:              Decision
    rationale:             str
    citations:             List[Citation]
    customer_response:     str
    next_steps:            List[str]
    internal_notes:        str
    compliance_passed:     bool
    compliance_flags:      List[ComplianceFlag]
    metadata:              Dict[str, Any] = Field(default_factory=dict)