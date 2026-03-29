"""
ShopCore Support Resolution Agent — Main Entry Point
=====================================================

Usage:
    # Build the policy index (run once)
    python main.py index

    # Resolve a single ticket interactively
    python main.py resolve --ticket EXC-001

    # Run full 20-ticket evaluation
    python main.py eval

    # Run a custom ticket from JSON
    python main.py custom --file examples/custom_ticket.json
"""

from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(_PROJECT_ROOT / ".env")

from rich.console import Console
console = Console()


def cmd_index(args):
    from ingestion.ingestion import build_index
    console.print("[bold cyan]Building policy index…[/bold cyan]")
    build_index(reset=args.reset)
    console.print("[green]Index built successfully.[/green]")


def cmd_resolve(args):
    from crew import SupportResolutionCrew
    from evaluation.run_evaluation import run_single
    crew = SupportResolutionCrew()
    run_single(args.ticket, crew)


def cmd_eval(args):
    from crew import SupportResolutionCrew
    from evaluation.run_evaluation import run_evaluation
    crew = SupportResolutionCrew()
    run_evaluation(crew, save_results=True)


def cmd_metrics(args):
    from evaluation.metrics import load_latest_result, load_result, print_metrics_panel, export_csv, export_markdown_report, build_evaluation_table
    from rich.console import Console as C
    c = C()
    data = load_latest_result() if args.latest else load_result(args.input)
    print_metrics_panel(data["metrics"])
    c.print(build_evaluation_table(data["results"]))
    if args.csv:      export_csv(data["results"], args.csv)
    if args.markdown: export_markdown_report(data, args.markdown)


def cmd_batch(args):
    from scripts.batch_run import main as batch_main
    import sys as _sys
    _sys.argv = ["batch_run.py", "--input", str(args.input), "--summary"]
    if args.output: _sys.argv += ["--output", str(args.output)]
    batch_main()


def cmd_custom(args):
    """Run a ticket from a JSON file."""
    from crew import SupportResolutionCrew
    from evaluation.run_evaluation import _print_resolution
    from utils.models import (
        SupportTicket, OrderContext,
        FulfillmentType, OrderStatus
    )

    with open(args.file) as f:
        data = json.load(f)

    ctx_data = data["order_context"]
    ctx = OrderContext(
        order_id         = ctx_data["order_id"],
        order_date       = ctx_data["order_date"],
        delivery_date    = ctx_data.get("delivery_date"),
        item_name        = ctx_data["item_name"],
        item_category    = ctx_data["item_category"],
        item_value       = float(ctx_data["item_value"]),
        fulfillment_type = FulfillmentType(ctx_data["fulfillment_type"]),
        shipping_region  = ctx_data["shipping_region"],
        order_status     = OrderStatus(ctx_data["order_status"]),
        payment_method   = ctx_data.get("payment_method"),
        is_final_sale    = ctx_data.get("is_final_sale", False),
        is_marketplace   = ctx_data.get("is_marketplace", False),
        seller_id        = ctx_data.get("seller_id"),
        membership_tier  = ctx_data.get("membership_tier"),
    )
    ticket = SupportTicket(
        ticket_id    = data.get("ticket_id", "CUSTOM-001"),
        ticket_text  = data["ticket_text"],
        order_context= ctx,
    )

    crew = SupportResolutionCrew()
    resolution = crew.resolve(ticket, verbose=True)
    _print_resolution(resolution)


def main():
    parser = argparse.ArgumentParser(
        description="ShopCore E-Commerce Support Resolution Agent"
    )
    sub = parser.add_subparsers(dest="command")

    # index
    p_index = sub.add_parser("index", help="Build ChromaDB policy index")
    p_index.add_argument("--reset", action="store_true", help="Delete and rebuild index")
    p_index.set_defaults(func=cmd_index)

    # resolve
    p_resolve = sub.add_parser("resolve", help="Resolve a single test ticket")
    p_resolve.add_argument("--ticket", required=True, help="Ticket ID e.g. EXC-001")
    p_resolve.set_defaults(func=cmd_resolve)

    # eval
    p_eval = sub.add_parser("eval", help="Run full 20-ticket evaluation")
    p_eval.set_defaults(func=cmd_eval)

    # metrics
    p_metrics = sub.add_parser("metrics", help="Report metrics from a saved evaluation JSON")
    grp = p_metrics.add_mutually_exclusive_group(required=True)
    grp.add_argument("--input",  type=Path, help="Path to evaluation JSON")
    grp.add_argument("--latest", action="store_true", help="Use most recent result file")
    p_metrics.add_argument("--csv",      type=Path, help="Export per-ticket CSV")
    p_metrics.add_argument("--markdown", type=Path, help="Export Markdown report")
    p_metrics.set_defaults(func=cmd_metrics)

    # batch
    p_batch = sub.add_parser("batch", help="Batch-resolve tickets from a JSONL file")
    p_batch.add_argument("--input",  required=True, type=Path, help="Path to .jsonl ticket file")
    p_batch.add_argument("--output", type=Path, help="Output directory for results")
    p_batch.set_defaults(func=cmd_batch)

    # custom
    p_custom = sub.add_parser("custom", help="Run a ticket from a JSON file")
    p_custom.add_argument("--file", required=True, help="Path to JSON ticket file")
    p_custom.set_defaults(func=cmd_custom)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    # Indexing uses local embeddings only; other commands call the Gemini API.
    _needs_api = args.command not in ("index", "metrics")
    _gemini = os.environ.get("GROQ_API_KEY", "").strip() or os.environ.get(
        "GOOGLE_API_KEY", ""
    ).strip()
    if _needs_api and not _gemini:
        console.print("[red]Error: GROQ_API_KEY (or GOOGLE_API_KEY) not set.[/red]")
        console.print(
            "Put the key in [bold].env[/bold] (same folder as main.py), not only in .env.example — "
            "the app never loads .env.example."
        )
        env_path = _PROJECT_ROOT / ".env"
        if env_path.is_file():
            try:
                for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                    line = line.strip()
                    if line.startswith("GROQ_API_KEY="):
                        val = line.split("=", 1)[-1].strip().strip('"').strip("'")
                        if not val:
                            console.print(
                                "[yellow]Your .env file has GROQ_API_KEY= but nothing after the '='. "
                                "Paste your API key, then save the file (Ctrl+S).[/yellow]"
                            )
                        break
            except OSError:
                pass
        else:
            console.print(f"[yellow]No .env found at {env_path}. Copy .env.example to .env and add your key.[/yellow]")
        console.print("Or set in PowerShell: [cyan]$env:GEMINI_API_KEY='your-key'[/cyan]")
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()