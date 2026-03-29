"""Load, summarize, and export evaluation runs."""

from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from rich.console import Console
from rich.panel import Panel

from utils.formatting import build_evaluation_table as format_results_table

RESULTS_DIR = Path(__file__).parent / "results"

# Re-export for `from evaluation.metrics import build_evaluation_table`
build_evaluation_table = format_results_table


def _ensure_results_dir() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def save_evaluation_run(data: Dict[str, Any]) -> Path:
    _ensure_results_dir()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = RESULTS_DIR / f"eval_{stamp}.json"
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return path


def load_result(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_latest_result() -> Dict[str, Any]:
    _ensure_results_dir()
    files = sorted(RESULTS_DIR.glob("eval_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError(f"No eval_*.json files in {RESULTS_DIR}")
    return load_result(files[0])


def print_metrics_panel(metrics: Dict[str, Any]) -> None:
    c = Console()
    lines = [f"{k}: {v}" for k, v in metrics.items()]
    c.print(Panel("\n".join(lines), title="Evaluation metrics", border_style="green"))


def export_csv(results: List[Dict[str, Any]], path: Path) -> None:
    import csv

    if not results:
        path.write_text("", encoding="utf-8")
        return
    keys = list(results[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in results:
            w.writerow({k: r.get(k, "") for k in keys})


def export_markdown_report(data: Dict[str, Any], path: Path) -> None:
    m = data.get("metrics", {})
    results = data.get("results", [])
    lines = [
        "# Evaluation report",
        "",
        "## Metrics",
        "",
    ]
    for k, v in m.items():
        lines.append(f"- **{k}**: {v}")
    lines.extend(["", "## Per ticket", "", format_results_table(results)])
    path.write_text("\n".join(lines), encoding="utf-8")
