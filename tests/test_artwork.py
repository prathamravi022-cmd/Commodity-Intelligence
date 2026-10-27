"""UIX-ART-01: the artwork set. Every page owns a distinct motif and every reference resolves.

These are the invariants behind the dashboard's imagery: a page whose icon file
is missing, duplicated, or not a real SVG would render a blank tile, and the
browser would only reveal it visually. ``tools/make_artwork.py --check`` runs the
same audit from the command line; this keeps it in the ordinary test run.

The last two tests render the real components through Streamlit's app-test
harness, so the markup path (data URI in, <img> out) is exercised, not just the
file on disk.
"""
import struct
import textwrap
import xml.etree.ElementTree as ET
from pathlib import Path

from app import artwork
from app.components import NAV_PAGES

ROOT = Path(__file__).resolve().parents[1]


def test_every_nav_page_has_its_own_artwork():
    seen: dict[str, str] = {}
    for page in NAV_PAGES:
        assert page["art"] == artwork.PAGE_ART.get(page["title"]), page["title"]
        path = artwork.ASSETS / page["art"]
        assert path.is_file(), f"{page['title']} references missing {path.name}"
        assert path.name not in seen, (
            f"{page['title']} reuses {path.name}, already used by {seen[path.name]}"
        )
        seen[path.name] = page["title"]
    assert len(seen) == len(NAV_PAGES)


def test_art_map_matches_the_nav_registry():
    # A stale key here would leave a page without a header motif.
    assert set(artwork.PAGE_ART) == {p["title"] for p in NAV_PAGES}


def test_shared_illustrations_exist():
    for name in (artwork.LOGO, artwork.HERO, artwork.EMPTY):
        assert (artwork.ASSETS / name).is_file(), name


def test_svgs_parse_and_carry_a_viewbox():
    svgs = sorted(artwork.ASSETS.glob("*.svg"))
    assert len(svgs) >= 13, f"expected the full artwork set, found {len(svgs)}"
    for path in svgs:
        root = ET.parse(path).getroot()  # raises on malformed XML
        assert root.tag.endswith("svg"), path.name
        assert root.get("viewBox"), f"{path.name} has no viewBox to scale from"
        assert path.stat().st_size > 200, f"{path.name} looks empty"


def test_artwork_stays_inside_the_product_palette():
    # Four hue families and nothing else: gold (brand), red/green (signed
    # movement), navy (navigation rail). A stray purple or cyan literal in the
    # artwork would be invisible in review but obvious on screen.
    offenders: list[str] = []
    for path in sorted(artwork.ASSETS.glob("*.svg")):
        for bad in artwork.palette_violations(path.read_text(encoding="utf-8")):
            offenders.append(f"{path.name}: {bad}")
    assert not offenders, "palette breaks:\n" + "\n".join(offenders)


def test_palette_checker_actually_rejects_off_palette_colours():
    assert artwork.palette_violations("fill='#A855F7'")          # purple
    assert artwork.palette_violations("color: #06B6D4;")          # cyan
    assert not artwork.palette_violations("fill='#A67C00'")       # brand gold
    assert not artwork.palette_violations("stroke='#B42318'")     # red (down)
    assert not artwork.palette_violations("fill='#0E7C57'")       # green (up)
    assert not artwork.palette_violations("fill='#23406B'")       # navy (rail)
    assert not artwork.palette_violations("fill='#F6F7F9'")       # canvas neutral
    assert not artwork.palette_violations("rgba(0,0,0,0)")        # transparent


def test_favicon_is_a_square_png():
    path = artwork.ASSETS / artwork.FAVICON
    assert path.is_file(), "run: python tools/make_artwork.py"
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    width, height = struct.unpack(">II", data[16:24])  # IHDR
    assert (width, height) == (64, 64)


def _run_script(tmp_path: Path, body: str):
    """Run a snippet against the real Streamlit API via the app-test harness.

    The snippet replaces ``Home.py`` in a copy of ``app/``: ``st.page_link`` only
    accepts the entrypoint file itself or a file under ``pages/``, so the probe has
    to *be* the entrypoint for the tab bar to build. The components it imports come
    from the real package (``sys.path`` points at the project root).
    """
    import shutil

    from streamlit.testing.v1 import AppTest

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


def test_page_header_renders_breadcrumb_title_and_data_status(tmp_path):
    at = _run_script(tmp_path, '''
        from app.components import page_header
        page_header("Spread Analytics", "Pairwise spreads")
    ''')
    assert not at.exception, at.exception
    markup = "\n".join(m.value for m in at.markdown)
    # semantic breadcrumb: a <nav> landmark, not a bare div
    assert '<nav class="crumb" aria-label="Breadcrumb">' in markup
    assert "<h1>Spread Analytics</h1>" in markup
    assert "status-chip" in markup                   # current / stale data indicator
    assert "Data as of" in markup and "MCX · Gold" in markup
    assert "ph-mark" in markup and "data:image/svg+xml;base64," in markup


def test_light_header_renders_page_actions_as_links(tmp_path):
    at = _run_script(tmp_path, '''
        from app.components import page_header
        page_header("Data Quality", "Rows", actions=[("Methodology", "methodology"),
                                                     ("Overview", "")])
    ''')
    assert not at.exception, at.exception
    markup = "\n".join(m.value for m in at.markdown)
    assert 'class="ph-cta" href="/methodology"' in markup
    assert 'class="ph-cta" href="/"' in markup          # empty slug is the root page
    assert "hero-band" not in markup     # light header stays light even with actions


def test_every_nav_page_script_exists():
    # A registry entry pointing at a deleted file would fail only at click time.
    for page in NAV_PAGES:
        assert (ROOT / "app" / page["path"]).is_file(), page["path"]


def test_nav_slugs_and_titles_are_unique():
    slugs = [p["slug"] for p in NAV_PAGES]
    titles = [p["title"] for p in NAV_PAGES]
    assert len(set(slugs)) == len(slugs)
    assert len(set(titles)) == len(titles)
    assert all(p["section"] in {"Workspace", "Research", "Preferences"}
               for p in NAV_PAGES)


def test_empty_state_renders_the_vault_artwork(tmp_path):
    at = _run_script(tmp_path, '''
        from app.components import empty_state
        empty_state("No data yet", "Run the pipeline first.")
    ''')
    assert not at.exception, at.exception
    markup = "\n".join(m.value for m in at.markdown)
    assert "empty-art" in markup and "data:image/svg+xml;base64," in markup
    assert "No data yet" in markup


def test_data_uri_helper_round_trips_and_degrades():
    uri = artwork.data_uri(artwork.LOGO)
    assert uri.startswith("data:image/svg+xml;base64,")
    assert artwork.data_uri("no-such-file.svg") == ""
    # Missing artwork must not leave a broken <img> in the markup.
    assert artwork.img("no-such-file.svg") == ""
    assert 'src="data:image/svg+xml;base64,' in artwork.img(artwork.HERO)
