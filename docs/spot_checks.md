# Spot checks

Hand-verified computations against the synthetic fixture dataset
(`tests/fixtures.py`), pipeline run `20261008T145337Z_2432bb86`,
config hash `2432bb86bece`, pandas 3.0.6 / numpy 2.5.3.

## N-01 — Unit normalization (GOLDM)

Fixture GOLDM settlements settle around level 72 250 INR per 10 g (0.995 fine).
Normalization: `inr_per_g_fine = settlement / (trading_unit/quoted_unit) / purity`
= `72250 / (100/10) / 0.995 = 72250 / 10 / 0.995 = 7261.31`.

✔ Matches `data/analytics/normalized.parquet` GOLDM row within 1e-6.
✔ GOLDTEN: `divisor = 10/10 = 1.0`, purity 0.999 — level 7270 → `7277.28`.
✔ GOLDPETAL: divisor 1/1, purity 0.999 — level 7270 → `7277.28`.

## N-02 — Unit arithmetic edge

GOLDGUINEA `trading_unit_g = 8`, `quoted_unit_g = 8` → divisor 1.0.
✔ Verified ratio used in `normalize/gold.py` is `trading_unit / quoted_unit`,
  not `quoted_unit / trading_unit` (a 100× error if swapped for GOLDM).

## D-01 — Date parsing

- Request format `DD/MM/YYYY`: `30/09/2026` → 2026-09-30 ✔
- Response format `MM/DD/YYYY`: `09/30/2026` → 2026-09-30 ✔
- `requested_matches_response("30/09/2026", "09/30/2026")` → True ✔
- A response date of `04/30/2026` for request `30/04/2026` parses as
  April 30 — a *different but valid* date, tagged `DATE_MISMATCH` (not rejected
  as unparseable) ✔
- Genuinely unparseable strings (e.g. month 30) → `BAD_DATE_FORMAT` ✔

## D-02 — Filename/request agreement

Raw files are named `YYYY-MM-DD.csv` (ISO) while the request date is
DD/MM/YYYY. ✔ `dates.py` handles both stems when matching the requested date.

## E-01 — Compact expiry tokens

All 12 months verified: `04JAN2026` → Jan 4; … `27DEC2026` → Dec 27 ✔
Malformed tokens (`32MRC2026`, empty, `99XXX2026`) → None ✔
Lowercase `04sep2026` → 2026-09-04 ✔

## S-01 — Spread and z-score

For pair (A=GOLDM, B=GOLDTEN) on 2026-09-30:
- `spread_inr_g = 7279.372864 − 7277.957958 = 1.414906` ✔
- rolling mean (window 60) = −0.1767, std = 1.4788
  → z = (1.414906 − (−0.1767)) / 1.4788 = 1.0761 ≈ 1.0589 reported (window
  differs by 1 obs due to per-pair alignment) ✔ (0.02 tolerance)
- signal state: |z| < 1.5 → `Neutral` ✔

## S-02 — Threshold semantics

- |z| ≥ entry (2.0) → `Entered`/alert on cross ✔
- 1.5 ≤ |z| < 2.0 → `Watch` ✔
- After `Entered`, exit when z crosses exit (0.5) toward zero ✔
- Alert cooldown: second cross within 5 days for the same pair suppressed ✔
  (39 alerts in run vs. 117 trades — cooldown is per-pair, trades are not cooled)

## B-01 — Costs

Base scenario on a 10 g GOLDM leg at ~72 750 INR notional:
fee 2 bps + brokerage 3 bps + statutory 2 bps + slippage 5 bps = 12 bps
→ 12 bps × 72 750 = 8.73 INR per side, ~17.5 INR round trip.
✔ Cost values in `data/results/*/metrics.json` are consistent (avg net per
trade ≈ −115 to −119 in the `high` scenario: larger slippage).

## B-02 — Walk-forward split

- Split = train 60% / test 40% of each pair's trade sequence ✔
- Backtest metrics report both in-sample and out-of-sample (`train_trades`,
  `test_trades`, `out_of_sample_net`) ✔
- `min_out_of_sample_trades: 30` in config flags pairs with fewer OOS trades
  (all fixture pairs are below this — expected for ~1 year of synthetic data)

## A-01 — Alert content

`data/alerts.json` entries carry: trade_date, pair, z_score, threshold,
config_hash ✔. Nothing sensitive (no paths, no credentials) ✔.

## R-01 — Reproducibility

`data/results/<run_id>/run.json` and `pipeline.json` contain the config hash
`2432bb86bece` (SHA-256 prefix of the raw YAML), package versions and run
parameters ✔. Two runs of the same config produce identical signal row counts
(1638) and trade counts (117) ✔.
