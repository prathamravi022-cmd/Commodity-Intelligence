"""Optional sign-in gate — Streamlit's native OIDC, Clerk as the provider.

The product is a public research prototype by default: with no ``[auth]`` block
in ``.streamlit/secrets.toml`` every page renders and this module does nothing at
all. Adding that block turns the gate on for the whole application at once,
because the check lives in the router (``app/Home.py``) rather than being copied
into ten page files where one omission would leave a hole.

Why native OIDC rather than a Clerk SDK: Streamlit performs the whole
authorisation-code flow itself (``st.login``) and keeps the resulting tokens in
a signed cookie. No Clerk package is involved, no publishable key is embedded in
the page, and nothing in this project ever reads, stores or prints a client
secret. Clerk supplies the OIDC discovery document; that is the entire
integration surface.

Setup
-----
1. In the Clerk dashboard enable OIDC/SSO and copy the discovery URL, which
   looks like ``https://<instance>.clerk.accounts.dev/.well-known/openid-configuration``.
2. Register the redirect URI. Streamlit appends ``/oauth2callback`` to the app
   origin, so local development needs ``http://localhost:8601/oauth2callback``
   and production needs ``https://<your-domain>/oauth2callback``. Both must be
   listed in Clerk, and the deployed one must match exactly — a trailing slash
   or a different port is a different URI.
3. Copy ``.streamlit/secrets.toml.example`` to ``.streamlit/secrets.toml`` and
   fill in the values. ``cookie_secret`` is a string you generate yourself
   (``python -c "import secrets; print(secrets.token_urlsafe(32))"``); it signs
   the session cookie and is not a Clerk value. Never commit that file.

Nothing here trusts the browser for identity: the name and email shown in the
rail come from the ID token Streamlit has already verified.
"""
import logging

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

logger = logging.getLogger(__name__)

#: The secrets section this module reads. A deployment with no ``[auth]`` block
#: is a public instance; the block is the only switch.
SECTION = "auth"

#: The two values the flow cannot run without.
REQUIRED_KEYS: tuple[str, ...] = ("client_id", "server_metadata_url")

#: What ``auth_state()`` can answer.
DISABLED = "disabled"      # no [auth] block at all: the documented public instance
OK = "ok"                  # complete configuration
INCOMPLETE = "incomplete"  # a block exists but a required value is missing
INVALID = "invalid"        # the block exists but cannot be read as keys/values

#: Warnings are logged once per process, not once per rerun.
_warned: set[str] = set()


def _warn_once(key: str, message: str, *args) -> None:
    if key in _warned:
        return
    _warned.add(key)
    logger.warning(message, *args)


def _read_section() -> tuple[str, dict]:
    """``(state, config)`` for the ``[auth]`` secrets section.

    The absence of the secrets file is answered rather than propagated — that is
    the ordinary state of a fresh checkout and of CI. What is *not* swallowed is
    a configuration that exists but is wrong: it comes back as ``INVALID`` (or
    ``INCOMPLETE`` from ``auth_state``) so the rail can say so out loud instead
    of presenting a public app as if sign-in were running.

    Only the expected failures are caught by type; an unexpected error is logged
    with its traceback and also surfaces as ``INVALID``, because silently
    treating a programming error as "no configuration" is how a gate ends up off
    without anyone noticing. No secret value is ever logged.
    """
    try:
        section = st.secrets[SECTION]
    except (StreamlitSecretNotFoundError, FileNotFoundError, KeyError):
        return DISABLED, {}
    except Exception:
        logger.exception("could not read [auth] from .streamlit/secrets.toml")
        return INVALID, {}
    try:
        return OK, {key: section[key] for key in section}
    except (TypeError, AttributeError, KeyError):
        _warn_once("malformed",
                   "[auth] must be a table of keys; got %s — sign-in stays off",
                   type(section).__name__)
        return INVALID, {}


def _config() -> dict:
    """The ``[auth]`` secrets section, or an empty dict when unusable."""
    return _read_section()[1]


def missing_keys() -> list[str]:
    """Required values that are absent or blank (``[]`` when the block is absent)."""
    state, cfg = _read_section()
    if state != OK:
        return []
    return [key for key in REQUIRED_KEYS if not str(cfg.get(key) or "").strip()]


def auth_state() -> str:
    """``DISABLED`` | ``OK`` | ``INCOMPLETE`` | ``INVALID``."""
    state, _ = _read_section()
    if state != OK:
        return state
    missing = missing_keys()
    if missing:
        _warn_once("incomplete",
                   "[auth] is missing %s; the instance stays public until both "
                   "values are set", ", ".join(missing))
        return INCOMPLETE
    return OK


def auth_enabled() -> bool:
    """True only when a complete provider configuration is present.

    Both values are required: without ``client_id`` there is nothing to
    authenticate against, and without ``server_metadata_url`` Streamlit cannot
    discover the endpoints. A half-filled block therefore leaves the app open
    rather than locking every reader out of a working prototype — but
    ``auth_warning()`` makes that state visible instead of silent.
    """
    return auth_state() == OK


def auth_warning() -> str:
    """Visible explanation when a sign-in block exists but cannot run.

    Empty for ``DISABLED`` (nothing was promised) and for ``OK``. Never contains
    a secret — only the names of the missing keys.
    """
    state = auth_state()
    if state == INCOMPLETE:
        return (f"Sign-in is half configured ({', '.join(missing_keys())} missing). "
                f"This instance is public until both Clerk values are set in "
                f".streamlit/secrets.toml.")
    if state == INVALID:
        return ("The [auth] block in .streamlit/secrets.toml could not be read as "
                "key/value pairs. This instance is public until it is fixed.")
    return ""


def _claim(name: str) -> str:
    """One ID-token claim, tolerating both access styles across versions."""
    try:
        value = getattr(st.user, name)
    except Exception:
        try:
            value = st.user[name]
        except Exception:
            return ""
    return str(value) if value else ""


def is_signed_in() -> bool:
    """Whether this browser session carries a verified identity."""
    if not auth_enabled():
        return False
    try:
        return bool(st.user.is_logged_in)
    except Exception:
        return False


def user() -> dict:
    """The signed-in reader, or ``{}``.

    ``name`` falls back to the email because a Clerk user may not have set a
    full name, and an empty rail card would look like a bug. ``subject`` is the
    stable user id — the only field safe to key per-user state on.
    """
    if not is_signed_in():
        return {}
    return {
        "name": _claim("name") or _claim("email") or "Signed in",
        "email": _claim("email"),
        "subject": _claim("sub"),
    }


def sign_in() -> None:
    """Start the provider's authorisation flow (redirects the browser)."""
    st.login()


def sign_out() -> None:
    """Clear the session cookie and the cached identity."""
    st.logout()


def require_auth() -> None:
    """Stop the page behind a glass sign-in card when nobody is signed in.

    A no-op on a public instance, which is what keeps every existing test and
    the QA harness working unchanged. The copy states what signing in gives
    access to and what the product is, so the gate is an invitation rather than
    a blank wall; the disclaimer is repeated here because this is the first
    screen an unauthenticated visitor sees.
    """
    if not auth_enabled() or is_signed_in():
        return

    st.markdown(
        """
<div class="panel signin-gate">
  <div class="empty-state">
    <div class="empty-title">Sign in to open the workspace</div>
    <div class="empty-body">
      Commodity Intelligence is a research prototype over MCX gold settlement
      data — four contracts on one scale, spreads, z-scores and a backtest.
      Sign-in keeps saved views and export history tied to the right analyst.
      Signals are research outputs, not trade recommendations.
    </div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )
    if st.button("Sign in", type="primary", width="stretch", key="signin_button"):
        sign_in()
    st.stop()
