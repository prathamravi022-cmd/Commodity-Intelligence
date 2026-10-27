"""Data Quality — what was ingested, what was rejected, and why."""
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.components import (caveat_box, chart_table, disclaimer_footer,
                            empty_state, kpi_row, page_header, section_head)
from app.dataio import DATA, load_clean, load_rejections
from app.theme import GOLD_DEEP, GOLD_BRIGHT, PLOTLY_CONFIG, WARN
from src.ingest import import_csv
from src.utils.config import load_config
from src.validate.report import build_quality_report

page_header("Data Quality",
            "Every row accounted for — accepted, rejected with a reason, or absent",
            actions=[("Methodology", "methodology"),
                     ("Settings", "settings")])

clean = load_clean()
rej = load_rejections()

if clean.empty:
    empty_state("No clean data", "Run python -m src.pipeline, then reload this page.")
    disclaimer_footer()
    st.stop()

kpi_row([
    {"label": "Clean rows", "value": f"{len(clean):,}",
     "help": "Rows that passed schema, price, date and duplicate validation."},
    {"label": "Rejected rows", "value": f"{len(rej):,}" if not rej.empty else "0",
     "help": "Rows removed by the validator; each carries a reason code."},
    {"label": "Trading days", "value": f"{clean['trade_date'].nunique():,}",
     "help": "Distinct settlement dates in the clean dataset."},
    {"label": "Contracts", "value": f"{clean['symbol'].nunique()}",
     "help": "Distinct MCX gold contracts present."},
])

# ---- Coverage ------------------------------------------------------------
section_head("Coverage per contract", "Trading days present, out of all days in the window")
cov = clean.groupby("symbol")["trade_date"].nunique().sort_values()
maxd = clean["trade_date"].nunique()
# A filled track per contract rather than four bars from zero: the question here
# is "how much of the window is present", so the empty part of the track carries
# as much meaning as the filled part.
track = go.Bar(x=[maxd] * len(cov), y=cov.index, orientation="h", width=0.58,
               marker=dict(color="rgba(255,255,255,0.08)"), hoverinfo="skip",
               showlegend=False)
fill = go.Bar(
    x=cov.values, y=cov.index, orientation="h", width=0.58,
    marker=dict(color=[GOLD_DEEP if v == maxd else GOLD_BRIGHT for v in cov.values]),
    text=[f"{v} / {maxd} days · {v / maxd * 100:.0f}%" for v in cov.values],
    textposition="outside", cliponaxis=False,
    hovertemplate=f"%{{y}}: %{{x}} of {maxd} trading days<extra></extra>",
    showlegend=False)
fig = go.Figure([track, fill])
fig.update_layout(
    barmode="overlay", height=240, margin=dict(l=8, r=8, t=6, b=6),
    xaxis=dict(range=[0, maxd * 1.34], showgrid=False, zeroline=False,
               showticklabels=False, title=None),
    yaxis=dict(title=None, tickfont=dict(size=11)))
st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)
for sym, n in cov.items():
    if n < maxd:
        st.caption(f"{sym}: {n}/{maxd} days ({n / maxd * 100:.0f}%) — short history, "
                   f"not a data error. Check first_year in config before drawing conclusions.")
# The same coverage as a table, so the bar lengths are never the only source.
chart_table(
    pd.DataFrame({"Contract": cov.index,
                  "Trading days": cov.to_numpy(),
                  "Share of window": [f"{v / maxd * 100:.0f}%" for v in cov.to_numpy()]}),
    "Table view — coverage per contract",
)

# ---- Presence heatmap ----------------------------------------------------
section_head("Rows per contract per date", "A gap here is a missing settlement, not a zero")
grid = (clean.groupby(["symbol", "trade_date"]).size().unstack(fill_value=0))
# One thin ribbon per contract, no cell gutters: at 273 dates the gaps used to
# turn the grid into a moiré pattern. A missing settlement now reads as a break
# of colour in a solid gold ribbon, which is exactly what it is.
gfig = go.Figure(go.Heatmap(
    z=grid.values, x=grid.columns, y=grid.index,
    zmin=0, zmax=1, colorscale=[[0.0, "#2A1D22"], [1.0, GOLD_DEEP]],
    showscale=False, xgap=0, ygap=3,
    hovertemplate="%{y} · %{x|%d %b %Y}<br>%{z} row(s)<extra></extra>"))
gfig.update_layout(
    height=60 + 30 * len(grid.index), margin=dict(l=8, r=8, t=6, b=6),
    xaxis=dict(tickformat="%b %Y", nticks=6, showgrid=False),
    yaxis=dict(title=None, tickfont=dict(size=11)))
st.plotly_chart(gfig, width="stretch", config=PLOTLY_CONFIG)
st.caption("One row per contract per date is expected; a pale cell is a missing "
           "settlement and is excluded from spreads rather than filled.")
# A heatmap cannot be read by a screen reader at all, and "which dates are
# missing" is the only question it answers. Answer it in words, with the exact
# dates rather than a colour the reader has to decode.
missing = {sym: [d for d in grid.columns if grid.at[sym, d] == 0]
           for sym in grid.index}
chart_table(
    pd.DataFrame({
        "Contract": list(missing),
        "Missing settlements": [len(dates) for dates in missing.values()],
        "Dates": [", ".join(d.strftime("%d %b %Y") for d in dates[:12]) or "none"
                  for dates in missing.values()],
    }),
    "Table view — missing settlements",
)

# ---- Rejections ----------------------------------------------------------
section_head("Rejection log", "Every rejected row carries a reason code")
if rej.empty:
    st.success("No rejections — every raw row validated cleanly.")
else:
    st.dataframe(rej, width="stretch", height=280)
    counts = rej["reason"].value_counts()
    rfig = go.Figure(go.Bar(
        x=counts.values, y=counts.index, orientation="h",
        marker=dict(color=WARN),
        hovertemplate="%{y}: %{x} rows<extra></extra>"))
    rfig.update_layout(height=max(200, 36 * len(counts)),
                       xaxis_title="Rejected rows", margin=dict(l=8, r=8, t=10, b=8))
    st.plotly_chart(rfig, width="stretch", config=PLOTLY_CONFIG)

    if "DATE_MISMATCH" in set(rej["reason"]):
        section_head("Date-mismatch examples", "Requested date versus date stamped in the file")
        dm = rej[rej["reason"] == "DATE_MISMATCH"]
        if "response_date" in dm.columns:
            st.dataframe(dm.head(20), width="stretch", hide_index=True)
        else:
            st.dataframe(dm.head(20), width="stretch", hide_index=True)
        st.caption("A mismatch means the exchange returned a different session than the "
                   "one requested — those rows are rejected rather than silently relabelled.")

# ---- Manual import ------------------------------------------------------
section_head("Import a bhavcopy CSV",
             "Same validators as the download path — nothing reaches data/raw unproven")
st.caption("Upload an MCX bhavcopy or any export carrying the nine required columns. "
           "Column names are matched case-insensitively and can be remapped below. "
           "Rows are validated before the file is written; rejections are reported, "
           "never repaired.")

uploaded = st.file_uploader("CSV file", type=["csv"], key="dq_upload",
                            help="The file stays in the browser until you press "
                                 "\"Validate\"; nothing is written to disk before "
                                 "that, and nothing at all without \"Save\".")

if uploaded is not None:
    try:
        imp_df = import_csv.read_csv(uploaded.getvalue())
    except Exception as exc:                      # unreadable upload
        st.error(f"Could not parse that CSV: {exc}")
        st.stop()

    mapping = import_csv.suggest_mapping(list(imp_df.columns))
    unmapped = [k for k, v in mapping.items() if v is None]

    with st.container(border=True):
        st.markdown("**Column mapping** — suggested from the headers; change any that "
                    "are wrong.")
        picks = {}
        cols = st.columns(3)
        for i, want in enumerate(import_csv.RAW_COLUMNS):
            options = ["— not mapped —"] + [str(c) for c in imp_df.columns]
            default = mapping[want] if mapping[want] is not None else "— not mapped —"
            picks[want] = cols[i % 3].selectbox(
                want, options, index=options.index(default), key=f"dq_map_{want}",
                help="Required by the schema check. Unmapped columns stop the import.")

    c1, c2 = st.columns([1, 2])
    requested = c1.date_input("Requested trade date", value=date.today(),
                              key="dq_req_date",
                              help="The session this file should contain. Rows whose "
                                   "Date differs are rejected as DATE_MISMATCH.")
    target_name = f"{requested.isoformat()}.csv"
    has_existing = (DATA / "raw" / target_name).exists()
    overwrite = c2.checkbox("Overwrite the existing file for that date",
                            value=False, key="dq_overwrite",
                            disabled=not has_existing,
                            help=("Raw files are evidence: an existing "
                                  f"{target_name} is never replaced silently."
                                  if has_existing else "No file exists for that date."))

    final_map = {k: (None if v == "— not mapped —" else v) for k, v in picks.items()}
    try:
        mapped = import_csv.apply_mapping(imp_df, final_map)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    b1, b2 = st.columns([1, 2])
    validate_clicked = b1.button("Validate", type="primary", width="stretch",
                                 key="dq_validate",
                                 help="Runs the schema, date, expiry and range checks "
                                      "in memory. Writes nothing.")
    b2.caption(f"{len(mapped):,} rows · {len(imp_df.columns)} source columns · "
               f"{sum(1 for v in final_map.values() if v is not None)}/9 mapped to "
               f"the canonical schema")

    if "dq_preview" not in st.session_state and not validate_clicked:
        st.caption("Press Validate to preview what would be accepted and rejected.")

    if validate_clicked or "dq_preview" in st.session_state:
        if validate_clicked:
            try:
                pclean, prejected = import_csv.validate_staged(mapped, requested)
            except Exception as exc:
                st.error(f"Validation could not run: {exc}")
                st.stop()
            st.session_state["dq_preview"] = {
                "clean": pclean, "rejected": prejected, "mapped": mapped.copy(),
                "requested": requested, "overwrite": overwrite,
            }
        prev = st.session_state["dq_preview"]
        pclean, prejected = prev["clean"], prev["rejected"]
        prev_target = f"{prev['requested'].isoformat()}.csv"
        prev_exists = (DATA / "raw" / prev_target).exists()
        kpi_row([
            {"label": "Rows accepted", "value": f"{len(pclean):,}",
             "help": "Rows that passed schema, date, expiry and range validation."},
            {"label": "Rows rejected", "value": f"{len(prejected):,}",
             "help": "Reported with a reason code; never repaired on import."},
            {"label": "Contracts present",
             "value": f"{pclean['Symbol'].nunique() if len(pclean) else 0}",
             "help": "Distinct gold contracts among the accepted rows."},
        ])
        if len(prejected):
            counts = (prejected["__reason__"].value_counts()
                      .rename_axis("reason").rename("rows").reset_index())
            # The table is a canvas grid, so the same facts are stated in text:
            # screen readers and the verification harness both read this line.
            st.caption("Would be rejected: " + ", ".join(
                f"{row.reason} × {row.rows}" for row in counts.itertuples()))
            st.dataframe(counts, width="stretch", hide_index=True)

        if st.button("Save to data/raw", key="dq_save",
                     disabled=bool(prev["overwrite"] and not prev_exists),
                     help="Writes the file, records its checksum in the manifest and "
                          "logs the import. Re-run the pipeline to rebuild analytics."):
            try:
                record = import_csv.commit_import(
                    prev["mapped"], prev["requested"],
                    overwrite=bool(prev["overwrite"]))
            except (FileExistsError, ValueError) as exc:
                st.error(str(exc))
            else:
                st.session_state.pop("dq_preview", None)
                st.cache_data.clear()
                st.success(
                    f"Saved {record['file']} — {record['rows_accepted']:,} accepted, "
                    f"{record['rows_rejected']:,} rejected, sha256 "
                    f"`{record['sha256'][:12]}…`. Rebuild the analytics with "
                    f"`python -X utf8 -m src.pipeline` so every downstream figure "
                    f"uses this file.")

# ---- Import history ------------------------------------------------------
imp_history = import_csv.load_history()
if imp_history:
    with st.expander("Import history — every manual import, with checksums"):
        st.dataframe(pd.DataFrame(imp_history), width="stretch", hide_index=True)

# ---- Data-quality report -------------------------------------------------
with st.container(border=True):
    st.markdown("**Export the data-quality report** — coverage, rejection reasons, "
                "source checksums and the validation rules in force, as Markdown.")
    _rules = load_config()["validation"]
    _manifest = (json.loads((DATA / "raw" / "manifest.json").read_text(encoding="utf-8"))
                 if (DATA / "raw" / "manifest.json").exists() else {})
    _report = build_quality_report(clean, rej, _manifest, _rules, imp_history)
    st.download_button("Download data-quality report", _report.encode("utf-8"),
                       file_name="data_quality_report.md", mime="text/markdown",
                       key="dq_report",
                       help="Regenerated from the files on disk at download time.")

# ---- Source integrity ----------------------------------------------------
section_head("Source file checksums", "SHA-256 of every ingested file, first 12 characters")
manifest_p = DATA / "raw" / "manifest.json"
if manifest_p.exists():
    manifest = json.loads(manifest_p.read_text(encoding="utf-8"))
    rows = [{"file": k, "sha256": v["sha256"][:12] + "…", "rows": v["row_count"],
             "downloaded (UTC)": v["download_time"][:19]}
            for k, v in manifest.items() if k != "_meta"]
    st.dataframe(pd.DataFrame(rows), width="stretch", height=260)
else:
    st.caption("No manifest yet — checksums are written on download.")

# ---- Validation rules ----------------------------------------------------
section_head("Validation rules in force", "Read from config/config.yaml")
v = load_config()["validation"]
st.dataframe(pd.DataFrame([
    {"Rule": "Requested date format", "Value": v["date_request_format"]},
    {"Rule": "Response date format", "Value": v["date_response_format"]},
    {"Rule": "Expiry date format", "Value": v["expiry_format"]},
    {"Rule": "Price-jump flag threshold", "Value": f"{v['max_price_jump_pct']}%"},
    {"Rule": "Request rate limit", "Value": f"{v['rate_limit_seconds']} s"},
]), width="stretch", hide_index=True)
caveat_box("Rejections are never repaired silently. A row that fails validation is "
           "excluded from analytics and logged with a reason, so any downstream "
           "conclusion can be traced back to the inputs it actually used.")

disclaimer_footer()
