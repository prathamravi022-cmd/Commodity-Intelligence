"""Data-quality report export (roadmap 30 / 126).

Renders the same facts the Data Quality page shows — coverage, rejection
reasons, checksums, rules in force — as a Markdown document, so a review can be
attached to a run without screenshots. Pure function over data already on disk.
"""
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPORT_NAME = "data_quality_report.md"


def build_quality_report(clean: pd.DataFrame, rej: pd.DataFrame,
                         manifest: dict, rules: dict,
                         history: list[dict] | None = None) -> str:
    """Markdown data-quality report. No claim is made beyond the data given."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = ["# Data quality report", "",
             f"Generated {now} from the files currently in `data/`.", ""]

    lines += ["## Summary", "",
              "| Measure | Value |", "|---|---|",
              f"| Clean rows | {len(clean):,} |",
              f"| Rejected rows | {len(rej):,} |",
              f"| Distinct contracts | {clean['symbol'].nunique() if len(clean) else 0} |",
              f"| Trading days | {clean['trade_date'].nunique() if len(clean) else 0} |", ""]

    if len(clean):
        lines += ["## Coverage per contract", "",
                  "| Contract | Trading days | First | Last |", "|---|---|---|---|"]
        g = clean.groupby("symbol")["trade_date"].agg(["nunique", "min", "max"])
        for sym, row in g.iterrows():
            lines.append(f"| {sym} | {row['nunique']} | {row['min']:%Y-%m-%d} "
                         f"| {row['max']:%Y-%m-%d} |")
        lines.append("")

    lines += ["## Rejections", ""]
    if rej.empty:
        lines += ["No rows were rejected.", ""]
    else:
        lines += ["| Reason | Rows |", "|---|---|"]
        for reason, n in rej["reason"].value_counts().items():
            lines.append(f"| {reason} | {n} |")
        lines += ["", "Rejected rows are excluded from every downstream calculation. "
                  "They are never repaired in place.", ""]

    lines += ["## Source files (SHA-256, first 16 characters)", "",
              "| File | Checksum | Rows |", "|---|---|---|"]
    for name, meta in sorted(manifest.items()):
        if name == "_meta":
            continue
        lines.append(f"| {name} | `{meta['sha256'][:16]}…` | {meta['row_count']} |")
    lines.append("")

    if history:
        lines += ["## Import history", "",
                  "| File | Imported (UTC) | Accepted | Rejected |", "|---|---|---|---|"]
        for rec in history:
            stamp = str(rec.get("imported_utc", ""))[:19].replace("T", " ")
            lines.append(f"| {rec.get('file', '?')} | {stamp} "
                         f"| {rec.get('rows_accepted', '?')} "
                         f"| {rec.get('rows_rejected', '?')} |")
        lines.append("")

    lines += ["## Validation rules in force", "", "| Rule | Value |", "|---|---|"]
    for key, value in rules.items():
        lines.append(f"| {key} | {value} |")
    lines.append("")
    lines += ["---", "",
              "Produced by Commodity Derivatives Intelligence (Team Starway). "
              "Settlement prices are not executable fills; this report describes "
              "data handling, not market performance."]
    return "\n".join(lines)


def write_report(text: str, data_dir: Path) -> Path:
    path = Path(data_dir) / REPORT_NAME
    path.write_text(text, encoding="utf-8")
    return path
