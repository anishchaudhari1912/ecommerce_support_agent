"""
Test Suite — 20 Tickets
========================
8 standard | 6 exception-heavy | 3 conflict | 3 not-in-policy

Each ticket includes:
- ticket_id, ticket_text
- Full OrderContext
- expected_decision  (for evaluation scoring)
- test_category      ("standard" | "exception" | "conflict" | "not_in_policy")
- notes              (what makes this case interesting)
"""

from utils.models import (
    SupportTicket, OrderContext,
    FulfillmentType, OrderStatus, Decision, IssueType
)

# ──────────────────────────────────────────────────────────────
# Helper
# ──────────────────────────────────────────────────────────────
def make_ticket(
    ticket_id:        str,
    ticket_text:      str,
    order_id:         str,
    order_date:       str,
    delivery_date:    str | None,
    item_name:        str,
    item_category:    str,
    item_value:       float,
    fulfillment_type: FulfillmentType,
    shipping_region:  str,
    order_status:     OrderStatus,
    payment_method:   str | None = "credit_card",
    is_final_sale:    bool = False,
    is_marketplace:   bool = False,
    seller_id:        str | None = None,
    membership_tier:  str | None = None,
) -> SupportTicket:
    return SupportTicket(
        ticket_id    = ticket_id,
        ticket_text  = ticket_text,
        order_context= OrderContext(
            order_id         = order_id,
            order_date       = order_date,
            delivery_date    = delivery_date,
            item_name        = item_name,
            item_category    = item_category,
            item_value       = item_value,
            fulfillment_type = fulfillment_type,
            shipping_region  = shipping_region,
            order_status     = order_status,
            payment_method   = payment_method,
            is_final_sale    = is_final_sale,
            is_marketplace   = is_marketplace,
            seller_id        = seller_id,
            membership_tier  = membership_tier,
        ),
    )


# ══════════════════════════════════════════════════════════════
# STANDARD CASES (8)
# ══════════════════════════════════════════════════════════════

STANDARD_TICKETS = [

    {
        "ticket": make_ticket(
            ticket_id     = "STD-001",
            ticket_text   = "My order arrived 3 days ago but the shirt I received is the wrong size. I ordered a Medium and got an Extra Large. I would like an exchange or refund.",
            order_id      = "ORD-10001",
            order_date    = "2024-10-01",
            delivery_date = "2024-10-08",
            item_name     = "Classic Cotton T-Shirt",
            item_category = "apparel",
            item_value    = 29.99,
            fulfillment_type = FulfillmentType.FIRST_PARTY,
            shipping_region  = "US-NY",
            order_status     = OrderStatus.DELIVERED,
        ),
        "expected_decision": Decision.APPROVE,
        "test_category": "standard",
        "notes": "Wrong item/variant — clear approve case under POL-005 §1.3",
    },

    {
        "ticket": make_ticket(
            ticket_id     = "STD-002",
            ticket_text   = "I received my laptop 2 weeks ago and it works fine, but I changed my mind and want to return it. I haven't opened the box.",
            order_id      = "ORD-10002",
            order_date    = "2024-09-20",
            delivery_date = "2024-09-25",
            item_name     = "15-inch Laptop Pro",
            item_category = "electronics",
            item_value    = 899.99,
            fulfillment_type = FulfillmentType.FIRST_PARTY,
            shipping_region  = "US-TX",
            order_status     = OrderStatus.DELIVERED,
        ),
        "expected_decision": Decision.APPROVE,
        "test_category": "standard",
        "notes": "Within 30-day window, electronics unopened — should approve with note about customer paying return shipping",
    },

    {
        "ticket": make_ticket(
            ticket_id     = "STD-003",
            ticket_text   = "I placed an order 20 minutes ago and I want to cancel it. I haven't received any shipping confirmation.",
            order_id      = "ORD-10003",
            order_date    = "2024-10-10",
            delivery_date = None,
            item_name     = "Kitchen Blender",
            item_category = "appliance",
            item_value    = 79.99,
            fulfillment_type = FulfillmentType.FIRST_PARTY,
            shipping_region  = "US-IL",
            order_status     = OrderStatus.PLACED,
        ),
        "expected_decision": Decision.APPROVE,
        "test_category": "standard",
        "notes": "Within 1-hour cancellation window — should approve cancel immediately per POL-002 §1.1",
    },

    {
        "ticket": make_ticket(
            ticket_id     = "STD-004",
            ticket_text   = "My package was marked delivered yesterday but I never received it. I checked with my neighbors and the mailroom — nothing.",
            order_id      = "ORD-10004",
            order_date    = "2024-10-05",
            delivery_date = "2024-10-12",
            item_name     = "Wireless Earbuds",
            item_category = "electronics",
            item_value    = 149.99,
            fulfillment_type = FulfillmentType.FIRST_PARTY,
            shipping_region  = "US-CA",
            order_status     = OrderStatus.DELIVERED,
        ),
        "expected_decision": Decision.PARTIAL,
        "test_category": "standard",
        "notes": "Delivered-not-received: 48hr wait period required per POL-005 §6.1, then carrier investigation. Partial/pending.",
    },

    {
        "ticket": make_ticket(
            ticket_id     = "STD-005",
            ticket_text   = "I used a 15% off coupon on my order but it only took off 10%. The coupon code was SAVE15.",
            order_id      = "ORD-10005",
            order_date    = "2024-10-08",
            delivery_date = "2024-10-14",
            item_name     = "Yoga Mat",
            item_category = "fitness",
            item_value    = 45.00,
            fulfillment_type = FulfillmentType.FIRST_PARTY,
            shipping_region  = "US-WA",
            order_status     = OrderStatus.DELIVERED,
            payment_method   = "credit_card",
        ),
        "expected_decision": Decision.NEEDS_ESCALATION,
        "test_category": "standard",
        "notes": "Billing discrepancy — needs investigation. If error confirmed, difference refunded + $5 credit per POL-008 §4.3",
    },

    {
        "ticket": make_ticket(
            ticket_id     = "STD-006",
            ticket_text   = "I noticed a charge on my credit card for $89 that I don't recognize from ShopCore. I did not make this purchase.",
            order_id      = "ORD-10006",
            order_date    = "2024-10-01",
            delivery_date = None,
            item_name     = "Unknown",
            item_category = "unknown",
            item_value    = 89.00,
            fulfillment_type = FulfillmentType.FIRST_PARTY,
            shipping_region  = "US-FL",
            order_status     = OrderStatus.PLACED,
            payment_method   = "credit_card",
        ),
        "expected_decision": Decision.NEEDS_ESCALATION,
        "test_category": "standard",
        "notes": "Unauthorized charge — must escalate to Fraud team per POL-007 §1.1",
    },

    {
        "ticket": make_ticket(
            ticket_id     = "STD-007",
            ticket_text   = "I bought running shoes 3 weeks ago. One of the soles started peeling after just 5 uses. I want a replacement.",
            order_id      = "ORD-10007",
            order_date    = "2024-09-20",
            delivery_date = "2024-09-27",
            item_name     = "ProRun Trail Shoes",
            item_category = "footwear",
            item_value    = 120.00,
            fulfillment_type = FulfillmentType.FIRST_PARTY,
            shipping_region  = "US-CO",
            order_status     = OrderStatus.DELIVERED,
        ),
        "expected_decision": Decision.APPROVE,
        "test_category": "standard",
        "notes": "Manufacturing defect — approve replacement per POL-001 §4.1",
    },

    {
        "ticket": make_ticket(
            ticket_id     = "STD-008",
            ticket_text   = "I'm trying to apply my referral credit but it's not showing up at checkout. I referred a friend who made a purchase last week.",
            order_id      = "ORD-10008",
            order_date    = "2024-10-10",
            delivery_date = None,
            item_name     = "N/A",
            item_category = "N/A",
            item_value    = 0.00,
            fulfillment_type = FulfillmentType.FIRST_PARTY,
            shipping_region  = "US-GA",
            order_status     = OrderStatus.PLACED,
        ),
        "expected_decision": Decision.PARTIAL,
        "test_category": "standard",
        "notes": "Referral credit delay — credits applied within 30 days per POL-004 §4.1; may need to wait",
    },
]


# ══════════════════════════════════════════════════════════════
# EXCEPTION-HEAVY CASES (6)
# ══════════════════════════════════════════════════════════════

EXCEPTION_TICKETS = [

    {
        "ticket": make_ticket(
            ticket_id     = "EXC-001",
            ticket_text   = "My order arrived late and the cookies are melted. I want a full refund and to keep the item.",
            order_id      = "ORD-20001",
            order_date    = "2024-10-08",
            delivery_date = "2024-10-14",
            item_name     = "Artisan Cookie Box",
            item_category = "perishable",
            item_value    = 38.00,
            fulfillment_type = FulfillmentType.FIRST_PARTY,
            shipping_region  = "US-AZ",
            order_status     = OrderStatus.DELIVERED,
        ),
        "expected_decision": Decision.APPROVE,
        "test_category": "exception",
        "notes": "Perishable damaged — should approve refund, customer keeps item per POL-001 §6.2. But must check 24hr report window.",
    },

    {
        "ticket": make_ticket(
            ticket_id     = "EXC-002",
            ticket_text   = "I bought a set of razors last month. I opened them and used one. I want to return all of them because I prefer my old brand.",
            order_id      = "ORD-20002",
            order_date    = "2024-09-10",
            delivery_date = "2024-09-15",
            item_name     = "5-Pack Premium Razors",
            item_category = "hygiene",
            item_value    = 24.99,
            fulfillment_type = FulfillmentType.FIRST_PARTY,
            shipping_region  = "US-PA",
            order_status     = OrderStatus.DELIVERED,
            is_final_sale    = False,
        ),
        "expected_decision": Decision.DENY,
        "test_category": "exception",
        "notes": "Hygiene items (razors used) are non-returnable per POL-001 §3.1. Preference complaint, not defect.",
    },

    {
        "ticket": make_ticket(
            ticket_id     = "EXC-003",
            ticket_text   = "I bought this dress on clearance marked FINAL SALE. It arrived and the color looks completely different from the photos. I want a full refund.",
            order_id      = "ORD-20003",
            order_date    = "2024-09-28",
            delivery_date = "2024-10-03",
            item_name     = "Summer Floral Dress",
            item_category = "apparel",
            item_value    = 18.00,
            fulfillment_type = FulfillmentType.FIRST_PARTY,
            shipping_region  = "US-OH",
            order_status     = OrderStatus.DELIVERED,
            is_final_sale    = True,
        ),
        "expected_decision": Decision.PARTIAL,
        "test_category": "exception",
        "notes": "Final sale + color discrepancy. Minor color variation = no refund (POL-005 §3.2). Significant misdescription = SNAD override. Agent must judge severity.",
    },

    {
        "ticket": make_ticket(
            ticket_id     = "EXC-004",
            ticket_text   = "I received my skincare serum 10 days ago and after using it I had a severe allergic reaction. I have a doctor's note. I want a full refund even though the bottle is half empty.",
            order_id      = "ORD-20004",
            order_date    = "2024-09-30",
            delivery_date = "2024-10-04",
            item_name     = "Brightening Vitamin C Serum",
            item_category = "cosmetics",
            item_value    = 65.00,
            fulfillment_type = FulfillmentType.FIRST_PARTY,
            shipping_region  = "US-CA",
            order_status     = OrderStatus.DELIVERED,
        ),
        "expected_decision": Decision.APPROVE,
        "test_category": "exception",
        "notes": "Opened cosmetic with adverse reaction — qualifies for refund per POL-001 §3.3. Has medical documentation. Value under $100 so no extra docs needed.",
    },

    {
        "ticket": make_ticket(
            ticket_id     = "EXC-005",
            ticket_text   = "I bought a high-value watch from a marketplace seller 3 weeks ago for $750. The seller refuses to accept my return even though their policy says 30-day returns.",
            order_id      = "ORD-20005",
            order_date    = "2024-09-18",
            delivery_date = "2024-09-24",
            item_name     = "Luxury Automatic Watch",
            item_category = "jewelry",
            item_value    = 750.00,
            fulfillment_type = FulfillmentType.MARKETPLACE,
            shipping_region  = "US-NY",
            order_status     = OrderStatus.DELIVERED,
            is_marketplace   = True,
            seller_id        = "SELLER-8891",
        ),
        "expected_decision": Decision.NEEDS_ESCALATION,
        "test_category": "exception",
        "notes": "High-value marketplace + seller refuses return within stated policy. A-to-Z Guarantee applies (POL-009 §3.1). Manager approval needed for >$500.",
    },

    {
        "ticket": make_ticket(
            ticket_id     = "EXC-006",
            ticket_text   = "I signed up for the Plus Prime annual membership 45 days ago but I want to cancel and get a refund. I haven't been using it.",
            order_id      = "ORD-20006",
            order_date    = "2024-08-27",
            delivery_date = None,
            item_name     = "Plus Prime Annual Membership",
            item_category = "subscription",
            item_value    = 129.00,
            fulfillment_type = FulfillmentType.FIRST_PARTY,
            shipping_region  = "US-WI",
            order_status     = OrderStatus.DELIVERED,
            membership_tier  = "plus_prime",
        ),
        "expected_decision": Decision.DENY,
        "test_category": "exception",
        "notes": "Annual membership cancellation after 30 days — no refund per POL-011 §1.3. Access continues until expiry.",
    },
]


# ══════════════════════════════════════════════════════════════
# CONFLICT CASES (3)
# ══════════════════════════════════════════════════════════════

CONFLICT_TICKETS = [

    {
        "ticket": make_ticket(
            ticket_id     = "CON-001",
            ticket_text   = "I live in Quebec and I bought electronics from a marketplace seller 25 days ago. The seller says their return window is only 14 days. I want to return under my Quebec consumer rights.",
            order_id      = "ORD-30001",
            order_date    = "2024-09-15",
            delivery_date = "2024-09-20",
            item_name     = "Portable Bluetooth Speaker",
            item_category = "electronics",
            item_value    = 89.99,
            fulfillment_type = FulfillmentType.MARKETPLACE,
            shipping_region  = "CA-QC",
            order_status     = OrderStatus.DELIVERED,
            is_marketplace   = True,
            seller_id        = "SELLER-4421",
        ),
        "expected_decision": Decision.NEEDS_ESCALATION,
        "test_category": "conflict",
        "notes": "Conflict: Seller 14-day policy vs. Quebec 30-day consumer protection law. Regional law prevails per POL-006 §5.1 but requires specialist.",
    },

    {
        "ticket": make_ticket(
            ticket_id     = "CON-002",
            ticket_text   = "My EU order of a blender arrived with a cracked housing but I waited 10 days before reporting it because I was traveling. I want a full replacement.",
            order_id      = "ORD-30002",
            order_date    = "2024-09-10",
            delivery_date = "2024-09-18",
            item_name     = "High-Speed Blender Pro",
            item_category = "appliance",
            item_value    = 219.00,
            fulfillment_type = FulfillmentType.FIRST_PARTY,
            shipping_region  = "EU-DE",
            order_status     = OrderStatus.DELIVERED,
        ),
        "expected_decision": Decision.NEEDS_ESCALATION,
        "test_category": "conflict",
        "notes": "Conflict: 48-hour damage reporting window (POL-005 §2.1) vs EU 2-year legal guarantee (POL-006 §2.3). EU law overrides but needs legal/compliance.",
    },

    {
        "ticket": make_ticket(
            ticket_id     = "CON-003",
            ticket_text   = "I'm a ShopCore Plus Prime member. I bought a clearance item marked 'Final Sale' for $22. I want to return it within my 60-day Plus Prime window.",
            order_id      = "ORD-30003",
            order_date    = "2024-09-01",
            delivery_date = "2024-09-07",
            item_name     = "Clearance Desk Organizer",
            item_category = "home",
            item_value    = 22.00,
            fulfillment_type = FulfillmentType.FIRST_PARTY,
            shipping_region  = "US-OR",
            order_status     = OrderStatus.DELIVERED,
            is_final_sale    = True,
            membership_tier  = "plus_prime",
        ),
        "expected_decision": Decision.DENY,
        "test_category": "conflict",
        "notes": "Conflict: Plus Prime 60-day window (POL-011 §2.1) vs Final Sale non-returnable (POL-001 §3.2). Final Sale wins — Plus Prime does NOT override Final Sale.",
    },
]


# ══════════════════════════════════════════════════════════════
# NOT-IN-POLICY CASES (3)
# ══════════════════════════════════════════════════════════════

NOT_IN_POLICY_TICKETS = [

    {
        "ticket": make_ticket(
            ticket_id     = "NIP-001",
            ticket_text   = "I want ShopCore to compensate me for the emotional distress caused by my late delivery. The package came 2 days late and I missed an important gift-giving occasion.",
            order_id      = "ORD-40001",
            order_date    = "2024-10-01",
            delivery_date = "2024-10-12",
            item_name     = "Birthday Gift Set",
            item_category = "gifts",
            item_value    = 55.00,
            fulfillment_type = FulfillmentType.FIRST_PARTY,
            shipping_region  = "US-VA",
            order_status     = OrderStatus.DELIVERED,
        ),
        "expected_decision": Decision.ABSTAIN,
        "test_category": "not_in_policy",
        "notes": "Emotional distress compensation — not covered by any policy. Agent must not invent a policy. Should escalate or abstain with empathy.",
    },

    {
        "ticket": make_ticket(
            ticket_id     = "NIP-002",
            ticket_text   = "I want to transfer my ShopCore loyalty points to my friend's account as a gift. Can you do that for me?",
            order_id      = "ORD-40002",
            order_date    = "2024-09-15",
            delivery_date = None,
            item_name     = "N/A",
            item_category = "N/A",
            item_value    = 0.00,
            fulfillment_type = FulfillmentType.FIRST_PARTY,
            shipping_region  = "US-MN",
            order_status     = OrderStatus.PLACED,
        ),
        "expected_decision": Decision.ABSTAIN,
        "test_category": "not_in_policy",
        "notes": "Points transfer not addressed anywhere in policy. Should not approve or invent a process. Must escalate/abstain.",
    },

    {
        "ticket": make_ticket(
            ticket_id     = "NIP-003",
            ticket_text   = "I'm threatening to post a negative review on every platform if you don't give me a 50% discount on my next order. I've been a customer for 5 years.",
            order_id      = "ORD-40003",
            order_date    = "2024-10-09",
            delivery_date = "2024-10-11",
            item_name     = "Assorted Stationery Pack",
            item_category = "stationery",
            item_value    = 18.00,
            fulfillment_type = FulfillmentType.FIRST_PARTY,
            shipping_region  = "US-NC",
            order_status     = OrderStatus.DELIVERED,
        ),
        "expected_decision": Decision.DENY,
        "test_category": "not_in_policy",
        "notes": "Customer pressure/threats for unearned discount — must not concede per POL-012 §5.3. Agent should hold firm and document the pressure.",
    },
]


# ──────────────────────────────────────────────────────────────
# Combined test set
# ──────────────────────────────────────────────────────────────
ALL_TEST_CASES = STANDARD_TICKETS + EXCEPTION_TICKETS + CONFLICT_TICKETS + NOT_IN_POLICY_TICKETS

assert len(ALL_TEST_CASES) == 20, f"Expected 20 test cases, got {len(ALL_TEST_CASES)}"


def get_all_tickets() -> list[dict]:
    return ALL_TEST_CASES


def get_ticket_by_id(ticket_id: str) -> dict | None:
    for case in ALL_TEST_CASES:
        if case["ticket"].ticket_id == ticket_id:
            return case
    return None