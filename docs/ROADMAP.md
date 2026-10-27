# Product backlog — 150-feature roadmap

Status of every roadmap item in this repository, audited against the running
application, the pipeline in `src/`, and the test suite. An item is marked
**done** only when it is implemented *and* exercised (unit test, end-to-end
pipeline test, or browser verification); partial implementations are marked
**partial** with the gap stated. Nothing is marked done on intent.

Legend: `[x]` done and verified · `[~]` partial — gap stated · `[ ]` not built

---

## Phase 1 — Core financial research engine (P0)

### 1. Dashboard and market overview
| # | Feature | Status | Evidence / gap |
|---|---|---|---|
| 1 | Customizable analytics dashboard | [~] | Fixed layout; per-session display defaults in Settings. No widget picker. |
| 2 | Latest available data date | [x] | Overview KPI "Latest data date"; `dataio.as_of()`. |
| 3 | Supported-contract overview | [x] | Overview KPI + Gold Contracts spec cards. |
| 4 | Data freshness indicator | [x] | Rail/header status chips; `dataio.is_stale()` counts business days. |
| 5 | Market-data health status | [~] | Fresh/Stale only. No per-source or per-file health state. |
| 6 | Normalized gold price summary | [x] | Overview contract table, INR/g fine. |
| 7 | Daily price change indicators | [x] | "Day change %" column on Overview. |
| 8 | Spread opportunity overview | [x] | Overview relative-value section with strongest-z card. |
| 9 | Recent research signals | [x] | Overview signal badges; Signal Explorer. |
| 10 | Latest backtest summary | [x] | Overview trades KPI + Backtesting page. |

### 2. Gold contracts explorer
| # | Feature | Status | Evidence / gap |
|---|---|---|---|
| 11 | Dedicated page for each gold contract | [~] | One page with a contract selector, not four routes. |
| 12 | Four-contract comparison | [x] | Price Comparison page. |
| 13 | Contract size and purity reference cards | [x] | Gold Contracts spec grid. |
| 14 | Quoted-unit explanation | [x] | "Why raw prices cannot be compared" section. |
| 15 | Normalized price per fine-gold gram | [x] | `inr_per_g_fine` everywhere downstream. |
| 16 | Historical price explorer | [x] | Settlement curve with date slider. |
| 17 | Contract expiry metadata | [x] | Lifecycle table; expiry windows from config. |
| 18 | Expiry-specific series selection | [~] | Series keyed by (symbol, expiry); selector is symbol+date, not expiry-picking. |
| 19 | Contract availability and data coverage | [x] | Data Quality coverage bar + heatmap. |
| 20 | Side-by-side contract comparison | [x] | Price Comparison table view. |

### 3. Data ingestion and quality
| # | Feature | Status | Evidence / gap |
|---|---|---|---|
| 21 | MCX bhavcopy import | [x] | `src/ingest/download.py` — cached, rate-limited, retried. |
| 22 | CSV upload interface | [x] | Data Quality → Import a bhavcopy CSV (`src/ingest/import_csv.py`). |
| 23 | Column mapping for imported files | [x] | Auto-suggested mapping with per-column overrides. |
| 24 | Automatic date-format validation | [x] | `src/validate/dates.py`; DATE_MISMATCH / BAD_DATE_FORMAT. |
| 25 | Price and missing-value validation | [x] | PRICE_RANGE / MISSING_FIELD in `clean.py`. |
| 26 | Duplicate-row detection | [x] | `drop_duplicates(subset=[symbol, trade_date, expiry_date])`. |
| 27 | Contract expiry alignment checks | [x] | BAD_EXPIRY; no roll-date jumps by construction. |
| 28 | Rejected-row audit log | [x] | `data/clean/rejections.csv` + Data Quality page. |
| 29 | Import history and run IDs | [x] | `data/imports.json` (sha256, rows, clean/rejected, config hash). |
| 30 | Data-quality report export | [x] | Downloadable Markdown report on Data Quality. |

### 4. Price normalization and analytics
| # | Feature | Status | Evidence / gap |
|---|---|---|---|
| 31 | Contract-specific normalization engine | [x] | `src/normalize/gold.py`; per-contract unit/purity. |
| 32 | Fine-gold INR/g conversion | [x] | Hand-calculated tests in `test_normalize.py`. |
| 33 | Normalization formula explainer | [x] | Methodology page. |
| 34 | Raw versus normalized price comparison | [x] | Raw on hover + table on Price Comparison. |
| 35 | Interactive multi-contract price chart | [x] | Overview and Price Comparison charts. |
| 36 | Custom date-range filters | [x] | Price Comparison date inputs; Overview range selector. |
| 37 | Pairwise spread calculator | [x] | `src/analytics/spreads.py`. |
| 38 | Historical spread chart | [x] | Spread Analytics. |
| 39 | Rolling z-score calculator | [x] | `src/analytics/zscore.py`; no look-ahead (`shift(1)`). |
| 40 | Configurable lookback window | [x] | Window slider, recomputes without a pipeline rerun. |

### 5. Signals and research monitoring
| # | Feature | Status | Evidence / gap |
|---|---|---|---|
| 41 | Configurable watch threshold | [x] | Watch slider on Signal Explorer; the ladder and zones follow it. |
| 42 | Configurable entry threshold | [x] | Entry slider + Settings default. |
| 43 | Configurable exit threshold | [x] | Exit slider drives episode closing and the exit band. |
| 44 | Long-spread/short-spread classification | [x] | Direction column on every signal view. |
| 45 | Signal history timeline | [x] | One bar per episode, entry→exit, coloured by direction. |
| 46 | Signal event detail view | [x] | Episode selector with duration, entry/max/exit z and a z-path chart. |
| 47 | Historical signal annotations | [x] | Entry triangles and exit circles marked on the z-chart. |
| 48 | Signal frequency analysis | [x] | Episodes opened per quarter, chart + table. |
| 49 | Time spent beyond thresholds | [x] | Share of sessions in each zone, plus median and max abs z. |
| 50 | Signal calculation audit trail | [x] | Per-session spread, rolling mean/std, inputs used and z, with config hash. |

## Phase 2 — Advanced quantitative research (P1)

### 6. Backtesting engine
| # | Feature | Status | Evidence / gap |
|---|---|---|---|
| 51 | Chronological train/test split | [x] | `run_walk_forward`; split marker on the equity chart. |
| 52 | 60/40 default research split | [x] | `backtest.train_fraction`. |
| 53 | Walk-forward evaluation | [x] | Expanding windows, 20-day step. |
| 54 | Frozen parameters during test periods | [x] | Config hash frozen in `run.json`. |
| 55 | Next-period execution simulation | [x] | Settlement-close entry/exit, stated as a bias caveat. |
| 56 | Entry and exit cost modelling | [x] | Charged both sides, both legs. |
| 57 | Two-leg transaction cost accounting | [x] | `cost_total` per trade. |
| 58 | Trade-by-trade history | [x] | `trades.csv` + Backtesting trade log. |
| 59 | Equity curve visualization | [x] | Gross + net curves. |
| 60 | Backtest run comparison | [ ] | Runs are stored per `run_id` but never compared. |

### 7. Performance and risk analytics
| # | Feature | Status | Evidence / gap |
|---|---|---|---|
| 61 | Gross P&L reporting | [x] | KPI + equity curve. |
| 62 | Net P&L after costs | [x] | All three scenarios. |
| 63 | Win rate calculation | [x] | KPI. |
| 64 | Maximum drawdown analysis | [x] | KPI from cumulative net curve. |
| 65 | Trade count and frequency | [x] | KPI (+ out-of-sample split). |
| 66 | Average trade outcome | [~] | Present in `metrics.json`, not surfaced as a KPI. |
| 67 | Profit factor | [ ] | Not computed. |
| 68 | Holding-period analysis | [~] | Sessions-held per signal episode only. |
| 69 | Transaction-cost sensitivity | [x] | Scenario bar + spread caption. |
| 70 | Performance by contract pair | [x] | Attribution waterfall + per-pair table. |

### 8. Statistical research tools
| # | Feature | Status | Evidence / gap |
|---|---|---|---|
| 71 | Rolling spread mean and std | [x] | KPI strip on Spread Analytics. |
| 72 | Spread distribution histogram | [ ] | Not built. |
| 73 | Spread percentile analysis | [ ] | Not built. |
| 74 | Correlation matrix | [ ] | Not built. |
| 75 | Rolling correlation chart | [ ] | Not built. |
| 76 | Volatility regime analysis | [ ] | Not built. |
| 77 | Stationarity test tools | [ ] | Not built. |
| 78 | Mean-reversion diagnostics | [ ] | Not built (half-life, ACF). |
| 79 | Parameter sensitivity heatmap | [ ] | Not built (SIG-007). |
| 80 | Statistical confidence and sample-size warnings | [x] | Episode-count warning (and the existing trade-count caveat). |

### 9. Expiry, carry and execution research
| # | Feature | Status | Evidence / gap |
|---|---|---|---|
| 81 | Expiry calendar | [x] | Lifecycle status table. |
| 82 | Days-to-expiry indicators | [x] | Signed days-to-expiry throughout. |
| 83 | Expiry-specific price comparisons | [x] | Settlement curve vs days-to-expiry per date. |
| 84 | Contract rollover research view | [ ] | Not built. |
| 85 | Expiry discontinuity detection | [ ] | Not built. |
| 86 | Carry-assumption configuration | [x] | `carry.annual_carry_rate` in config. |
| 87 | Low/base/high transaction-cost scenarios | [x] | Three scenarios in config. |
| 88 | Fee assumption source documentation | [x] | README states they are placeholders. |
| 89 | Execution slippage scenarios | [x] | `slippage_bps` per scenario. |
| 90 | Same-close execution bias detection | [ ] | Not built. |

### 10. Research workspace and reproducibility
| # | Feature | Status | Evidence / gap |
|---|---|---|---|
| 91 | Save research configurations | [ ] | Not built. |
| 92 | Versioned parameter presets | [ ] | Not built. |
| 93 | YAML configuration editor | [~] | Read-only viewer + download; edits belong on disk. |
| 94 | Immutable backtest run snapshots | [x] | `data/results/<run_id>/`. |
| 95 | Reproducible run metadata | [x] | `run.json`, `pipeline.json`, config hash. |
| 96 | Compare experiment versions | [ ] | Not built. |
| 97 | Research notes attached to runs | [ ] | Not built. |
| 98 | Export results to CSV | [~] | Prices CSV only; trades/metrics not exported. |
| 99 | Export charts and reports | [~] | Plotly modebar PNG/SVG only. |
| 100 | One-click research report generation | [ ] | Not built. |

## Phase 3 — Premium product experience (P1/P2)

### 11. World-class frontend and visualization
| # | Feature | Status | Evidence / gap |
|---|---|---|---|
| 101 | Cinematic gold-bullion hero background | [x] | Licensed photograph, navy scrim, responsive reframing. |
| 102 | Premium dark/light theme | [~] | One tested light workspace; toggle deliberately absent (documented). |
| 103 | Collapsible sidebar | [x] | Rail collapses at every width; styled reopen pill. |
| 104 | Responsive mobile navigation | [x] | Drawer; QA captures at 390px. |
| 105 | Customizable dashboard widgets | [ ] | Not built. |
| 106 | Interactive chart crosshairs | [x] | Plotly unified hover. |
| 107 | Zoomable time-series charts | [x] | Plotly zoom + range selector. |
| 108 | Chart annotation tools | [ ] | Not built. |
| 109 | Consistent financial chart colour system | [x] | Single `mcx_light` template; contract colours fixed. |
| 110 | Accessible loading and empty states | [x] | `empty_state`, table views for every chart. |

### 12. Navigation and productivity
| # | Feature | Status | Evidence / gap |
|---|---|---|---|
| 111 | Global search | [ ] | Not built. |
| 112 | Command palette | [ ] | Not built. |
| 113 | Keyboard shortcuts | [ ] | Not built. |
| 114 | Recently viewed research pages | [ ] | Not built. |
| 115 | Pinned charts | [ ] | Not built. |
| 116 | Saved filters | [ ] | Not built. |
| 117 | Custom dashboard layouts | [ ] | Not built. |
| 118 | Persistent user preferences | [~] | Session defaults only; not persisted across sessions. |
| 119 | Contextual financial glossary | [~] | Inline explanations + Methodology; no hover glossary. |
| 120 | Guided first-use walkthrough | [ ] | Not built. |

### 13. Reports and communication
| # | Feature | Status | Evidence / gap |
|---|---|---|---|
| 121 | Scheduled report generation | [ ] | Not built. |
| 122 | PDF report export | [ ] | Not built. |
| 123 | Downloadable chart images | [x] | Plotly modebar download on every chart. |
| 124 | Shareable research snapshots | [ ] | Not built. |
| 125 | Report templates | [ ] | Not built. |
| 126 | Data coverage summary reports | [x] | Data Quality report export (#30). |
| 127 | Backtest comparison reports | [ ] | Blocked on #60. |
| 128 | Signal event annotations in reports | [ ] | Not built. |
| 129 | Report methodology footnotes | [x] | Caveat boxes + config hash on every page. |
| 130 | Email report delivery | [ ] | Not built; no mail transport configured. |

## Phase 4 — Reliability, security and future expansion (P2)

### 14. Security and operational reliability
| # | Feature | Status | Evidence / gap |
|---|---|---|---|
| 131 | Authentication | [ ] | Local single-user prototype; none needed yet. |
| 132 | Role-based permissions | [ ] | Not built. |
| 133 | Secure session handling | [ ] | Not built. |
| 134 | Server-side input validation | [x] | Upload path validates before any write (schema/date/range). |
| 135 | Secrets outside frontend code | [x] | `.env` only; never committed, never rendered. |
| 136 | Rate limiting for protected endpoints | [ ] | No endpoints; download path rate-limited at 1 s. |
| 137 | Audit logs for configuration changes | [~] | Config hash recorded per run; no change log. |
| 138 | Automated data-pipeline health checks | [~] | Staleness check + validators; no scheduled health run. |
| 139 | Backup and recovery procedures | [ ] | Not built. |
| 140 | Performance and error monitoring | [~] | `data/pipeline.log` + Streamlit log only. |

### 15. Advanced research and extensibility
| # | Feature | Status | Evidence / gap |
|---|---|---|---|
| 141 | Pluggable data-source adapters | [ ] | Single MCX source. |
| 142 | External market-data integration | [ ] | Not built. |
| 143 | Automated coverage gap detection | [~] | Coverage shown; nothing raises an alert. |
| 144 | Research plugin architecture | [ ] | Not built. |
| 145 | Additional commodity support | [ ] | Gold only, by design. |
| 146 | Configurable contract metadata | [x] | All four contracts defined in `config/config.yaml`. |
| 147 | Alternative spread-construction methods | [~] | Raw and carry-adjusted only. |
| 148 | Research experiment tagging | [ ] | Not built. |
| 149 | Optional model-assisted summaries | [ ] | Not built. |
| 150 | Documented API for authorized integrations | [ ] | Not built. |

---

## Prioritized implementation plan

Ordering follows the roadmap's own warning: the data pipeline and backtest must
be trustworthy before statistical tooling, reports or integrations are added.
Each milestone is small, shippable and verified before the next starts.

### M1 — Import, provenance and data-quality reporting (P0) — **shipped**
Covers 22, 23, 29, 30, 134, 126. Verified by `tests/test_import.py` (16 tests)
and `tools/verify_import_flow.py` (uploads a renamed-column CSV in a real
browser, validates, saves, checks the manifest and history, downloads the
report, and confirms that an overwrite is refused).
- **Why first:** it is the only P0 gap left. The rest of the ingestion →
  validation → normalization → spread/z-score → dashboard slice already exists
  and is covered by 78 tests.
- **Dependencies:** `src/validate/*`, `src/ingest/manifest.py` (both exist).
- **Effort:** ~4 h. **Risk:** writing to `data/raw` from the UI — mitigated by
  validating *before* any write and refusing to overwrite without confirmation.
- **Acceptance:** upload any CSV with the nine MCX columns in any order or
  casing; mapping is suggested and overridable; rows failing validation are
  rejected with reasons, never repaired; the saved file is checksummed into the
  manifest and listed in import history; a Markdown data-quality report exports
  coverage, rejection reasons and checksums; unit tests cover mapping,
  validation and commit.

### M2a — Signal research depth (P1) — **shipped**
Covers 41, 43, 45–50, 80. Verified by `tests/test_signal_research.py` (14),
`tests/test_signal_explorer_page.py` (5, which drive the widgets and assert the
recomputed output) and `tools/verify_signal_page.py` (renders, charts, audit).
- All three thresholds and the rolling window are page controls; the watch
  threshold is validated against the entry threshold rather than silently
  reordered.
- Episodes are drawn as a timeline, annotated on the z-chart, and selectable
  with duration / max |z| / exit detail.
- Frequency by quarter and dwell share per zone are stated as description, with
  an explicit warning when there are too few episodes to mean anything.
- Every z-value is traceable to the window that produced it (`inputs used`).

### M2b — Statistical research tools (P1)
Covers 71–79 (histogram, percentiles, correlation, rolling correlation,
volatility regimes, stationarity, mean-reversion diagnostics, sensitivity
heatmap).
- **Depends on:** M2a (episode/z infrastructure).
- **Effort:** ~10 h. **Risk:** presenting inference as fact — every statistic
  needs its window, sample size and no-look-ahead statement beside it, and the
  sensitivity grid must be computed out-of-sample only.
- **Acceptance:** spread distribution with percentile markers; correlation
  matrix and rolling correlation across contracts; ADF stationarity and
  half-life with the test statistic shown; a window × threshold heatmap of
  out-of-sample net P&L that marks unstable regions.

### M3 — Backtest rigor and run comparison (P1)
Covers 60, 67, 68, 84, 85, 90, 94–100, 98.
- **Depends on:** M2 for the sensitivity grid to compare against.
- **Effort:** ~10 h. **Risk:** comparing runs with different data windows —
  must show coverage overlap or refuse the comparison.
- **Acceptance:** two runs compared on trades, net P&L and OOS window; profit
  factor and holding-period metrics; CSV export of trades and metrics;
  run metadata shown beside every comparison.

### M4 — Reports and productivity (P1/P2)
Covers 111–117, 120–125, 127, 128, 130.
- **Depends on:** M3 (comparison reports need comparable runs).
- **Effort:** ~12 h. **Risk:** decorative controls — every shortcut, pin and
  template must act or it does not ship.
- **Acceptance:** keyboard shortcuts work from any page; saved layouts persist;
  a report regenerates from a stored run with methodology footnotes; PNG/PDF
  export of the standard report.

### M5 — Operations and extensibility (P2, gated)
Covers 131–143, 146–150.
- **Gate:** only on request. Authentication and roles for a single-user local
  research tool would be ceremony, not security.
- **Acceptance:** whatever is built here must not change any formula, assumption
  or result already verified.

### Explicitly out of scope
Automated order placement and any execution path. The product is read-only with
respect to markets, per the PRD's non-goals; nothing in this backlog changes
that.
