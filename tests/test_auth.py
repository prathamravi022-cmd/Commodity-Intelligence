"""AUTH-001: the sign-in gate must stay inert until a provider is configured.

The gate is a switch, and the dangerous failure mode is the switch flipping on
by itself — a fresh checkout, or CI, would then serve a sign-in wall to every
test and every page. These tests pin the default: with no ``[auth]`` block the
whole module answers "public instance" and ``require_auth()`` lets the script
run straight through.
"""
import textwrap
from pathlib import Path

from app import auth

ROOT = Path(__file__).resolve().parents[1]


def test_no_provider_configuration_means_public_instance():
    # no .streamlit/secrets.toml in a fresh checkout, so the section is absent
    assert auth._config() == {}
    assert auth.auth_enabled() is False
    assert auth.is_signed_in() is False
    assert auth.user() == {}


def test_partial_configuration_does_not_lock_the_app():
    # both values are required for the flow; a half-filled block must not gate
    assert auth.auth_enabled() is False


def _run(tmp_path: Path, body: str):
    from streamlit.testing.v1 import AppTest

    tree = tmp_path / "apptree"
    import shutil

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


def test_require_auth_is_a_no_op_on_a_public_instance(tmp_path):
    at = _run(tmp_path, '''
        from app.auth import require_auth
        require_auth()
        st.markdown("AFTER-THE-GATE")
    ''')
    assert not at.exception, at.exception
    body = "\\n".join(m.value for m in at.markdown)
    # the script ran past the gate: no sign-in card, no st.stop()
    assert "AFTER-THE-GATE" in body
    assert "signin-gate" not in body
    assert not at.button, [b.label for b in at.button]


def test_router_calls_the_gate_before_running_a_page():
    # one choke point: the gate lives in the router, not in ten page files that
    # could each forget it
    home = (ROOT / "app" / "Home.py").read_text(encoding="utf-8")
    assert "require_auth()" in home
    assert home.index("require_auth()") < home.index("current.run()")
    pages = list((ROOT / "app" / "pages").glob("*.py"))
    assert not any("require_auth" in p.read_text(encoding="utf-8") for p in pages)


# ---------------------------------------------------------------------------
# Configuration states
# ---------------------------------------------------------------------------
# The gate must never look *off* when somebody thought they had turned it on.
# These pin the four answers and the wording the rail shows for each.
import logging

import pytest
import streamlit

from app import auth

COMPLETE = {"auth": {"client_id": "cid-123",
                     "server_metadata_url": "https://example/.well-known/openid-configuration"}}


class _FakeSecrets:
    """Minimal stand-in for ``st.secrets`` (mapping access only)."""

    def __init__(self, data):
        self._data = data

    def __getitem__(self, key):
        return self._data[key]


def _patch_secrets(monkeypatch, data):
    monkeypatch.setattr(streamlit, "secrets", _FakeSecrets(data))
    monkeypatch.setattr(auth, "_warned", set())


def test_a_complete_block_enables_the_gate(monkeypatch):
    _patch_secrets(monkeypatch, COMPLETE)
    assert auth.auth_state() == auth.OK
    assert auth.auth_enabled() is True
    assert auth.auth_warning() == ""


def test_a_half_filled_block_is_reported_but_does_not_lock_the_app(monkeypatch):
    _patch_secrets(monkeypatch, {"auth": {"client_id": "cid-123"}})
    assert auth.auth_state() == auth.INCOMPLETE
    assert auth.auth_enabled() is False
    warning = auth.auth_warning()
    assert "server_metadata_url" in warning
    assert ".streamlit/secrets.toml" in warning
    # names only, never the configured value
    assert "cid-123" not in warning


def test_blank_values_count_as_missing(monkeypatch):
    _patch_secrets(monkeypatch, {"auth": {"client_id": "   ",
                                          "server_metadata_url": ""}})
    assert auth.auth_state() == auth.INCOMPLETE
    assert set(auth.missing_keys()) == {"client_id", "server_metadata_url"}


def test_an_absent_section_is_a_public_instance(monkeypatch):
    _patch_secrets(monkeypatch, {})
    assert auth.auth_state() == auth.DISABLED
    assert auth.auth_warning() == ""


def test_a_malformed_block_is_invalid_and_says_so(monkeypatch):
    _patch_secrets(monkeypatch, {"auth": "oops"})
    assert auth.auth_state() == auth.INVALID
    assert auth.auth_enabled() is False
    warning = auth.auth_warning()
    assert ".streamlit/secrets.toml" in warning
    assert "oops" not in warning


def test_an_unexpected_read_error_is_logged_and_does_not_look_configured(monkeypatch, caplog):
    class Broken:
        def __getitem__(self, key):
            raise RuntimeError("boom")

    monkeypatch.setattr(streamlit, "secrets", Broken())
    monkeypatch.setattr(auth, "_warned", set())
    with caplog.at_level(logging.ERROR, logger="app.auth"):
        assert auth.auth_state() == auth.INVALID
    assert any("could not read [auth]" in r.message for r in caplog.records)
