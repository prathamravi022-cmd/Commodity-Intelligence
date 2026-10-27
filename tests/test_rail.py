"""UIX-STATE-01: rail and toast state that used to be invisible or mistimed.

Three behaviours are pinned here, all of which fail *silently* in production:

* a cache reload raises its confirmation toast exactly once (a flag left in
  session state would show it again on every rerun, and showing it before the
  reload finished would be a lie);
* a half-configured sign-in block says so in the rail instead of quietly
  serving a public app;
* a pipeline that died shows up as a failed attempt, not as an old timestamp.
"""
from __future__ import annotations

import json
import shutil
import textwrap
from pathlib import Path

import pytest
import streamlit
from streamlit.testing.v1 import AppTest

from app import auth, dataio

ROOT = Path(__file__).resolve().parents[1]

#: Every cached reader in ``app.dataio``. Tests that point ``DATA`` somewhere
#: else must drop all of them: ``load_normalized`` caches an empty frame for the
#: temporary directory, and the next test would then read "no data" as if that
#: were the repository's real state.
CACHED_READERS = ("load_normalized", "load_signals", "load_rejections", "load_clean",
                  "latest_backtest_run", "last_pipeline_run", "last_pipeline_failure")


def _clear_data_caches() -> None:
    for name in CACHED_READERS:
        getattr(dataio, name).clear()


def _run(tmp_path: Path, body: str) -> AppTest:
    tree = tmp_path / "apptree"
    shutil.copytree(ROOT / "app", tree, ignore=shutil.ignore_patterns("__pycache__"))
    script = tree / "Home.py"
    script.write_text(
        textwrap.dedent(f'''\
            import sys
            sys.path.insert(0, r"{ROOT}")
            import streamlit as st
            st.set_page_config(page_title="probe")
        ''') + textwrap.dedent(body),
        encoding="utf-8",
    )
    return AppTest.from_file(str(script), default_timeout=60).run()


# ---- Reload notice ------------------------------------------------------
def test_reload_notice_fires_once_and_clears_the_flag(tmp_path):
    at = _run(tmp_path, '''
        import streamlit as st
        from app.components import flash_reload_notice
        st.session_state["data_reloaded"] = True
        flash_reload_notice()
        flash_reload_notice()
    ''')
    assert not at.exception, at.exception
    assert len(at.toast) == 1
    assert "data_reloaded" not in at.session_state


def test_reload_notice_is_silent_without_a_reload(tmp_path):
    at = _run(tmp_path, '''
        from app.components import flash_reload_notice
        flash_reload_notice()
    ''')
    assert not at.exception, at.exception
    assert not at.toast


def test_router_raises_the_notice_before_the_page_body():
    # Popped after current.run() the flag belonged to a rerun the reader never
    # saw; the router must consume it first, and only the router does.
    home = (ROOT / "app" / "Home.py").read_text(encoding="utf-8")
    assert "flash_reload_notice()" in home
    assert home.index("flash_reload_notice()") < home.index("current.run()")


# ---- Sign-in configuration warning --------------------------------------
class _FakeSecrets:
    def __init__(self, data):
        self._data = data

    def __getitem__(self, key):
        return self._data[key]


def test_rail_reports_a_half_configured_sign_in(tmp_path, monkeypatch):
    monkeypatch.setattr(streamlit, "secrets",
                        _FakeSecrets({"auth": {"client_id": "cid-secret-value"}}))
    monkeypatch.setattr(auth, "_warned", set())
    at = _run(tmp_path, '''
        from app.components import rail_user
        rail_user()
    ''')
    assert not at.exception, at.exception
    markup = "\n".join(m.value for m in at.markdown)
    assert "rail-warn" in markup
    assert "Not running" in markup
    assert "server_metadata_url" in markup
    assert "cid-secret-value" not in markup


def test_rail_is_quiet_on_a_deliberately_public_instance(tmp_path, monkeypatch):
    monkeypatch.setattr(streamlit, "secrets", _FakeSecrets({}))
    at = _run(tmp_path, '''
        from app.components import rail_user
        rail_user()
    ''')
    assert not at.exception, at.exception
    markup = "\n".join(m.value for m in at.markdown)
    assert "rail-warn" not in markup


# ---- Failed pipeline attempt -------------------------------------------
@pytest.fixture
def empty_results(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "results").mkdir(parents=True)
    monkeypatch.setattr(dataio, "DATA", data)
    _clear_data_caches()
    yield data / "results"
    _clear_data_caches()


def test_rail_shows_a_failed_attempt_that_is_newer_than_the_last_run(tmp_path, empty_results):
    run_dir = empty_results / "20261020T060000Z_aaaaaaaa"
    run_dir.mkdir()
    (run_dir / "pipeline.json").write_text(
        json.dumps({"started_utc": "2026-10-20T06:00:00+00:00"}), encoding="utf-8")
    (empty_results / dataio.FAILURE_NAME).write_text(json.dumps({
        "failed_utc": "2026-10-26T07:00:00+00:00",
        "stage": "validation",
        "error_type": "ValidationError",
        "reason": "no_raw_files",
    }), encoding="utf-8")
    dataio.last_pipeline_run.clear()
    dataio.last_pipeline_failure.clear()

    at = _run(tmp_path, '''
        from app.components import rail_status
        rail_status()
    ''')
    assert not at.exception, at.exception
    markup = "\n".join(m.value for m in at.markdown)
    assert "Failed at validation" in markup
    # the card names the freshness state and repeats it as a sentence
    assert ">ERROR<" in markup
    assert "failed at validation" in markup


def test_rail_stays_quiet_when_the_failed_attempt_was_superseded(tmp_path, empty_results):
    run_dir = empty_results / "20261026T060000Z_bbbbbbbb"
    run_dir.mkdir()
    (run_dir / "pipeline.json").write_text(
        json.dumps({"started_utc": "2026-10-26T06:00:00+00:00"}), encoding="utf-8")
    (empty_results / dataio.FAILURE_NAME).write_text(json.dumps({
        "failed_utc": "2026-10-25T07:00:00+00:00", "stage": "validation",
    }), encoding="utf-8")
    dataio.last_pipeline_run.clear()
    dataio.last_pipeline_failure.clear()

    at = _run(tmp_path, '''
        from app.components import rail_status
        rail_status()
    ''')
    assert not at.exception, at.exception
    markup = "\n".join(m.value for m in at.markdown)
    assert "Failed at" not in markup
    assert ">ERROR<" not in markup
