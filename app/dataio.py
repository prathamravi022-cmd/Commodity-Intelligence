"""Dashboard data access. Reads data/analytics and data/results only - never MCX."""
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from src.utils.config import config_hash, load_config

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

#: Files that make a directory a *run*. ``pipeline.json`` is written by the whole
#: pipeline (``python -m src.pipeline``), ``run.json`` by a bare backtest. Both
#: carry ``started_utc``, and that field — not the directory name — is the
#: authoritative timestamp: ``run_2`` vs ``run_10`` sorts wrongly as a string.
RUN_RECORDS: tuple[str, ...] = ("pipeline.json", "run.json")

#: Where the pipeline records a failed attempt (a file, so it can never be
#: mistaken for a run directory). Read by ``last_pipeline_failure()``.
FAILURE_NAME = "_last_failure.json"


def failure_path() -> Path:
    """Path of the failed-attempt record (inside ``data/results``)."""
    return DATA / "results" / FAILURE_NAME


@st.cache_data(show_spinner=False)
def load_normalized() -> pd.DataFrame:
    p = DATA / "analytics" / "normalized.parquet"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_parquet(p)
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    return df


@st.cache_data(show_spinner=False)
def load_signals() -> pd.DataFrame:
    p = DATA / "analytics" / "signals.parquet"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_parquet(p)
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    return df


@st.cache_data(show_spinner=False)
def load_rejections() -> pd.DataFrame:
    p = DATA / "clean" / "rejections.csv"
    if not p.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(p)
    except pd.errors.EmptyDataError:
        # Zero rejected rows -> empty file; treat as "no rejections"
        return pd.DataFrame()


@st.cache_data(show_spinner=False)
def load_clean() -> pd.DataFrame:
    p = DATA / "clean" / "bhavcopy.parquet"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_parquet(p)
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    return df


@st.cache_data(ttl=30, show_spinner=False)
def latest_backtest_run() -> dict | None:
    """Newest run directory and the artifacts it holds (``None`` when none)."""
    run_dir = _latest_run_dir()
    if run_dir is None:
        return None
    trades_p = run_dir / "trades.csv"
    metrics_p = run_dir / "metrics.json"
    run_p = run_dir / "run.json"
    out = {"run_id": run_dir.name, "run_dir": run_dir}
    if trades_p.exists():
        out["trades"] = pd.read_csv(trades_p)
    if metrics_p.exists():
        out["metrics"] = json.loads(metrics_p.read_text(encoding="utf-8"))
    if run_p.exists():
        out["run"] = json.loads(run_p.read_text(encoding="utf-8"))
    return out


@st.cache_data(show_spinner=False)
def load_alerts() -> list[dict]:
    import json
    p = DATA / "alerts.json"
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def as_of() -> pd.Timestamp | None:
    df = load_normalized()
    return None if df.empty else df["trade_date"].max()


def _today() -> pd.Timestamp:
    """Today at local midnight — the one clock ``is_stale`` reads.

    Exposed as a function so the freshness tests can pin it instead of sleeping
    until the weekend.
    """
    return pd.Timestamp.today().normalize()


# ---- Run directories ----------------------------------------------------
def _run_record(run_dir: Path) -> dict:
    """Parsed metadata of a run directory (``{}`` when absent or unreadable)."""
    for name in RUN_RECORDS:
        path = run_dir / name
        if not path.is_file():
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            continue                      # try the next record
        if isinstance(record, dict):
            return record
    return {}


def _run_started(run_dir: Path) -> pd.Timestamp | None:
    """``started_utc`` from a run's record, as a naive UTC timestamp."""
    stamp = _run_record(run_dir).get("started_utc")
    if not stamp:
        return None
    try:
        parsed = pd.Timestamp(stamp)
    except (ValueError, TypeError):
        return None
    return parsed.tz_convert(None) if parsed.tzinfo is not None else parsed


def _run_started_ns(run_dir: Path) -> int:
    """Chronological sort key in nanoseconds (metadata first, mtime second)."""
    started = _run_started(run_dir)
    if started is not None:
        return int(started.value)
    try:
        return int(run_dir.stat().st_mtime_ns)
    except OSError:                       # vanished or unreadable: sort it first
        return 0


def _run_dirs() -> list[Path]:
    """Directories under ``data/results`` that are actually runs.

    A directory counts only when it carries a run record, so a stray folder —
    ``.ipynb_checkpoints``, a half-created directory from a crashed process — can
    never become "the latest run". Missing or unreadable results directory means
    no runs, not an exception.
    """
    results = DATA / "results"
    try:
        entries = list(results.iterdir())
    except (FileNotFoundError, NotADirectoryError, PermissionError):
        return []
    return [d for d in entries
            if d.is_dir() and any((d / name).is_file() for name in RUN_RECORDS)]


def _latest_run_dir() -> Path | None:
    """The genuinely most recent run directory, chosen by time."""
    runs = _run_dirs()
    return max(runs, key=_run_started_ns) if runs else None


@st.cache_data(ttl=30, show_spinner=False)
def last_pipeline_run() -> pd.Timestamp | None:
    """UTC start time of the most recent pipeline run (None when never run).

    The label says *pipeline* run, so ``pipeline.json`` wins over ``run.json``
    when both are present: the backtest stage starts seconds after the pipeline
    does, and showing the later of the two would misdate the whole run. A run
    with no usable record falls back to the directory's modification time.
    """
    run_dir = _latest_run_dir()
    if run_dir is None:
        return None
    started = _run_started(run_dir)
    if started is not None:
        return started
    try:
        return pd.Timestamp(run_dir.stat().st_mtime, unit="s")
    except OSError:
        return None


@st.cache_data(ttl=30, show_spinner=False)
def last_pipeline_failure() -> dict | None:
    """The failed attempt recorded by ``src.pipeline``, or ``None``.

    Written by the pipeline before it re-raises, so a crash leaves evidence the
    dashboard can show instead of silently presenting the previous run as if it
    were the latest word.
    """
    try:
        record = json.loads(failure_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return record if isinstance(record, dict) else None


def failure_outranks(failure: dict | None, last_run: pd.Timestamp | None) -> bool:
    """True when the last attempt failed after the last good run.

    An undateable failure counts: the pipeline only writes the record after a
    stage raised, so it is always news.
    """
    if not failure:
        return False
    stamp = failure.get("failed_utc")
    if not stamp:
        return True
    try:
        failed = pd.Timestamp(stamp)
    except (ValueError, TypeError):
        return True
    if failed.tzinfo is not None:
        failed = failed.tz_convert(None)
    if last_run is None:
        return True
    # both sides are normalised: a caller may hold a tz-aware run timestamp
    # (tests, or a future metadata change) and comparing naive with aware
    # raises rather than answering
    if last_run.tzinfo is not None:
        last_run = last_run.tz_convert(None)
    return failed > last_run


# ---- Freshness model ----------------------------------------------------
# Six states, not two. The old boolean could only say "current" or "stale", so
# a file two sessions behind and a file six sessions behind looked identical,
# and "the pipeline has never run" looked the same as "the pipeline died"
#
# Sessions are counted in weekdays with ``numpy.busday_count``, which counts
# from the data date up to but *excluding* today:
#
#     data today            → 0  FRESH
#     Friday data, Monday   → 1  CURRENT   (the weekend is not a gap)
#     Thursday data, Monday → 2  RECENT
#     four or more          →    STALE
#
# Known limit: MCX market holidays are not modelled, so the first session after
# a holiday can read as one session older than it is. That needs an exchange
# calendar this project has no authoritative source for; the error direction is
# a later STALE, never a false FRESH.
FRESH = "FRESH"
CURRENT = "CURRENT"
RECENT = "RECENT"
STALE = "STALE"
NO_DATA = "NO_DATA"
ERROR = "ERROR"

#: Sessions behind before the data is called STALE rather than RECENT.
RECENT_LIMIT = 3

#: States that warrant a warning banner and muted figures.
WARNING_STATES = frozenset({RECENT, STALE, NO_DATA, ERROR})


@dataclass(frozen=True)
class Freshness:
    """One truthful answer to "how much can I trust these numbers?".

    ``state`` is one of the six constants above; ``sessions_behind`` is ``None``
    when it cannot be computed (no data, or a failure that outranks the data).
    ``headline`` is the sentence the UI shows — always present, so a status is
    never conveyed by colour alone.
    """

    state: str
    headline: str
    data_date: pd.Timestamp | None = None
    sessions_behind: int | None = None
    last_run: pd.Timestamp | None = None
    failure: dict | None = None

    @property
    def tone(self) -> str:
        """CSS suffix for the state (``no_data`` → ``no-data``)."""
        return self.state.lower().replace("_", "-")

    @property
    def warns(self) -> bool:
        """True when the state deserves the banner and muted figures."""
        return self.state in WARNING_STATES


def data_status() -> Freshness:
    """Freshness of the figures on screen, as one of six states.

    Precedence is deliberate: a failed attempt outranks age, because a run that
    died may have left analytics newer than the run record — the figures are
    then not merely old, they are unverified. Future-dated data is an error for
    the same reason: a session that has not happened cannot be trusted.
    """
    a = as_of()
    run = last_pipeline_run()
    failure = last_pipeline_failure()
    stale_failure = failure if failure_outranks(failure, run) else None

    if stale_failure is not None:
        stage = str(stale_failure.get("stage") or "an unknown stage")
        since = (run.strftime("%d %b %Y %H:%M") if run is not None
                 else "no successful run yet")
        return Freshness(
            state=ERROR,
            headline=(f"The last pipeline attempt failed at {stage}. Figures "
                      f"shown are from the last successful run ({since})."),
            data_date=a, last_run=run, failure=stale_failure,
        )

    if a is None:
        return Freshness(
            state=NO_DATA,
            headline=("No validated market data is loaded. Run the pipeline or "
                      "import a bhavcopy to populate data/raw."),
            last_run=run,
        )

    behind = int(np.busday_count(a.normalize().date(), _today().date()))
    if behind < 0:
        return Freshness(
            state=ERROR,
            headline=(f"The data is dated {a:%d %b %Y}, later than today — the "
                      f"freshness of these figures cannot be established."),
            data_date=a, last_run=run,
        )

    if behind == 0:
        return Freshness(FRESH, "The figures are from today's session.",
                         data_date=a, sessions_behind=0, last_run=run)
    if behind == 1:
        return Freshness(CURRENT,
                         "One trading session behind — the normal state before "
                         "the next settlement.",
                         data_date=a, sessions_behind=1, last_run=run)
    if behind <= RECENT_LIMIT:
        return Freshness(RECENT,
                         f"{behind} trading sessions behind the latest expected "
                         f"session — still inside the tolerance window, but no "
                         f"longer current.",
                         data_date=a, sessions_behind=behind, last_run=run)
    return Freshness(STALE,
                     f"{behind} trading sessions behind the latest expected "
                     f"session — these figures are historical.",
                     data_date=a, sessions_behind=behind, last_run=run)


def is_stale() -> bool:
    """True when the freshness state warrants the warning banner.

    Kept as the boolean the pages already call: RECENT is a warning (the data is
    behind), just a less severe one than STALE. Use ``data_status()`` when the
    difference between the six states matters.
    """
    return data_status().warns


def cost_scenarios() -> dict:
    """Cost scenario name -> its per-leg, per-side cost assumptions (bps)."""
    return load_config()["costs"]["scenarios"]


def cfg_hash_chip() -> str:
    return config_hash(load_config())
