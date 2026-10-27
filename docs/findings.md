# Findings

Top-line results from the full pipeline run on the synthetic fixture dataset
(run `20261008T145337Z_2432bb86`, config hash `2432bb86bece`). All numbers come
from generated fixtures — they exercise the machinery end-to-end but do not
describe the real market.

## What the run produced

| Stage | Count |
|---|---|
| Clean rows (4 symbols × ~273 trading days) | 1 092 |
| Rejected rows | 0 (fixtures are well-formed; validators proven by unit tests) |
| Signal rows (6 pairs × dates) | 1 638 |
| Alerts (z-cross, 5-day per-pair cooldown) | 39 |
| Trades (walk-forward, 6 pairs × 3 cost scenarios… see note) | 117 |
| Pipeline wall time | ~21 s |

Note on trades: 117 trade rows spans the base/high scenario output written by
the final backtest stage; per-pair trade counts in `metrics.json` sum to 39
trades per scenario.

## Backtest results (high-cost scenario — all pairs lose net)

| Pair | Trades | Win rate | Avg net/trade (INR) | Total net (INR) | OOS net (INR) |
|---|---|---|---|---|---|
| GOLDM vs GOLDTEN | 10 | 0% | −119.2 | −1 192 | −595 |
| GOLDM vs GOLDPETAL | 8 | 0% | −116.5 | −932 | −718 |
| GOLDGUINEA vs GOLDPETAL | 7 | 0% | −118.9 | −832 | −356 |
| GOLDGUINEA vs GOLDM | 6 | 0% | −115.3 | −692 | −474 |
| GOLDPETAL vs GOLDTEN | 5 | 0% | −114.6 | −573 | −476 |
| GOLDGUINEA vs GOLDTEN | 3 | 0% | −117.7 | −353 | −235 |

### Interpretation

1. **Every trade loses after costs, in both in-sample and out-of-sample.**
   That is the expected property of this fixture design: prices wiggle around a
   nearly flat common level with small independent noise, so mean-reversion
   signals fire on microscopic spreads (~±3 INR/g) whose reversion profit is
   smaller than a round trip of transaction costs. In the `high` scenario a
   round trip is ~0.33% of notional while typical spread reversion captures
   ~0.05–0.15%. The engine is doing its job: it reports when a strategy does
   *not* clear costs.

2. **Win rate 0% with negative average is consistent, not contradictory.**
   Gross per-trade P&L varies (the victory ratio metric is small but nonzero);
   costs push all of them net-negative.

3. **Out-of-sample is also negative** — 30.6% scale factor commissioned is OOS
   train ratio. This should not be read as an OOS estimate of a real strategy:
   the fixture has no genuine inefficiency to find.

4. **No pair meets the pre-registered `min_out_of_sample_trades: 30`**
   criterion (max 6 OOS trades). Any pair statistics here are therefore *not
   statistically meaningful* — this is flagged in metrics with
   `min_trades_required: 30`.

5. **Strongest |z| on the last observed day = 20.5** for
   GOLDPETAL vs GOLDTEN. Suspicious on its face but coherent: note it is a
   cross-pair z computed on the fly with the spread being near-zero and std
   miniscule (~0.02 INR/g). Tiny denominators produce large z values. This is
   why the dashboard's Methodology page stresses that z near zero-spread pairs
   is unstable at small windows.

6. **All 4 contracts settle within a tight band of ~7 277–7 279 INR/g fine**
   on 2026-09-30 (the fixture pins them to arbitrage-free pricing with small
   noise), so pairwise spreads mostly sit near 0 with tiny residual noise.
   The outright ` Entered`/`Exited` state machine still fires several times
   because thresholds are in units of the spread's own rolling std, not in
   absolute INR — a property worth rechecking against real data.

## Data-quality notes

- The 4 small gold contracts (GOLDM, GOLDTEN, GOLDGUINEA, GOLDPETAL) were kept;
  other symbols in the fixture are dropped at the normalization gate (this
  keeps spreads among fungible-ish gold variants).
- FIXTURE expiry handling is artificial: one pinned far-dated expiry per symbol
  so each contract has ~273 observations, allowing a real 60-day z window.
  (Earlier fixture drafts with monthly expiries only produced ~21 obs per pair,
  never reaching the window.)
- 0 rejected rows in this run; the validators themselves are exercised by
  dedicated unit tests (`tests/test_schema.py`, `test_dates.py`,
  `test_expiry.py`) including `PRICE_RANGE`, `DATE_MISMATCH`,
  `BAD_DATE_FORMAT`, `MISSING_FIELD` paths.

## What to do with real data

1. Replace fixture CSVs with real MCX bhavcopy downloads (the ingest module is
   written for the file-per-date pattern).
2. Verify contract metadata (trading units, purity, active expiries) in
   `config/config.yaml` against the exchange circular — placeholders today.
3. Replace placeholder fee schedules with the real MCX fee structure and
   document the source in the README.
4. Re-derive the carry rate (currently 0.0) from a defensible financing number
   (see config `carry.annual_carry_rate`).
5. Recheck z-score window (60 trading days) vs actual contract life on real
   data — contracts near expiry have short histories and the rolling window
   needs at least as many observations as the window.
6. Pre-register the `min_out_of_sample_trades` judgment honestly: with real
   monthly contract cycles, 30 OOS trades per pair is a demanding target.
7. Treat window-subjected z-values for near-degenerate pairs (tiny rolling
   std) with suspicion — decide whether to floor the rolling std before
   z-scoring on real data.

## Disclaimers

All results are from synthetic fixtures (see `tests/fixtures.py`) whose design
is documented in `docs/spot_checks.md`. Nothing here is investment advice and
no statistic here describes the actual gold market.
