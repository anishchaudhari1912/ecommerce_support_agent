"""Console tables for evaluation output (tabulate)."""

from __future__ import annotations
from typing import Any, Dict, List

from tabulate import tabulate


def build_evaluation_table(results: List[Dict[str, Any]], title: str | None = None) -> str:
    """Plain-text table for terminal / markdown embedding."""
    if not results:
        return "(no results)"
    headers = list(results[0].keys())
    rows = [[r.get(h, "") for h in headers] for r in results]
    return tabulate(rows, headers=headers, tablefmt="github")
