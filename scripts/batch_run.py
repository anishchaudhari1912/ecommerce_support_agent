"""
Batch-resolve tickets from a JSONL file (one JSON object per line).
Each line matches the structure of examples/custom_ticket.json.
"""

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

# Project root on path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from utils.models import (
    SupportTicket,
    OrderContext,
    FulfillmentType,
    OrderStatus,
)


def parse_ticket(obj: dict) -> SupportTicket:
    ctx_data = obj["order_context"]
    ctx = OrderContext(
        order_id=ctx_data["order_id"],
        order_date=ctx_data["order_date"],
        delivery_date=ctx_data.get("delivery_date"),
        item_name=ctx_data["item_name"],
        item_category=ctx_data["item_category"],
        item_value=float(ctx_data["item_value"]),
        fulfillment_type=FulfillmentType(ctx_data["fulfillment_type"]),
        shipping_region=ctx_data["shipping_region"],
        order_status=OrderStatus(ctx_data["order_status"]),
        payment_method=ctx_data.get("payment_method"),
        is_final_sale=ctx_data.get("is_final_sale", False),
        is_marketplace=ctx_data.get("is_marketplace", False),
        seller_id=ctx_data.get("seller_id"),
        membership_tier=ctx_data.get("membership_tier"),
    )
    return SupportTicket(
        ticket_id=obj.get("ticket_id", "BATCH-UNKNOWN"),
        ticket_text=obj["ticket_text"],
        order_context=ctx,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch-resolve support tickets from JSONL")
    parser.add_argument("--input", required=True, type=Path, help="Path to .jsonl file")
    parser.add_argument("--output", type=Path, help="Optional output JSONL for resolutions")
    parser.add_argument("--summary", action="store_true", help="Print one-line summary per ticket")
    args = parser.parse_args()

    import os

    _key = os.environ.get("GEMINI_API_KEY", "").strip() or os.environ.get(
        "GOOGLE_API_KEY", ""
    ).strip()
    if not _key:
        print("GEMINI_API_KEY or GOOGLE_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)

    from crew import SupportResolutionCrew

    crew = SupportResolutionCrew()
    out_lines: list[str] = []

    with args.input.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                ticket = parse_ticket(obj)
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                print(f"[line {line_no}] Skip invalid record: {e}", file=sys.stderr)
                continue

            res = crew.resolve(ticket, verbose=not args.summary)
            dumped = json.dumps(res.model_dump(), default=str)
            out_lines.append(dumped)
            if args.summary:
                print(f"{ticket.ticket_id}\t{res.decision.value}\t{len(res.citations)} citations")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("\n".join(out_lines) + ("\n" if out_lines else ""), encoding="utf-8")
        print(f"Wrote {len(out_lines)} resolutions to {args.output}")


if __name__ == "__main__":
    main()
