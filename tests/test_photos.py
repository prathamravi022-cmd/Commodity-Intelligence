"""UIX-PHOTO-01: the licensed photo set, its credits and its markup.

Photography is the only third-party material in the product, so it carries the
strictest invariants: every registered file exists at the size the registry
claims, every one is credited where it is used, nothing is shipped that the
registry does not know about, and the page markup offers a smaller variant
before the browser downloads the large one.

``tools/build_photos.py --check`` runs the file half of this audit from the
command line; these tests keep it in the ordinary test run, and add the markup
and attribution checks the tool cannot see.
"""
import io
import pathlib
import re
import struct
import textwrap
import xml.etree.ElementTree as ET

import pytest
from PIL import Image

from app import artwork
from app.theme import GOLD_BRIGHT, rendered_css

ROOT = pathlib.Path(__file__).resolve().parents[1]
PHOTOS_DIR = ROOT / "app" / "static" / "photos"
MIN_ALT = 40
MAX_BYTES = 260_000


def test_static_serving_is_enabled_next_to_the_entrypoint():
    # app/artwork.photo_url() points at /app/static/..., which Streamlit only
    # serves when server.enableStaticServing is on and the folder sits beside
    # app/Home.py. Without this the pages load with broken images.
    config = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert "enableStaticServing = true" in config
    assert PHOTOS_DIR.parent == ROOT / "app" / "static"
    assert artwork.PHOTO_PREFIX == "/app/static/photos"


@pytest.mark.parametrize("stem", sorted(artwork.PHOTOS))
def test_every_registered_photo_is_a_webp_at_the_registered_size(stem):
    meta = artwork.PHOTOS[stem]
    expected_height = int(round(meta["widths"][0] * meta["ratio"][1] / meta["ratio"][0]))
    for width in meta["widths"]:
        path = PHOTOS_DIR / f"{stem}-{width}.webp"
        assert path.is_file(), f"missing {path.name} — run: python tools/build_photos.py"
        data = path.read_bytes()
        assert data[:4] == b"RIFF" and data[8:12] == b"WEBP", f"{path.name} is not WebP"
        with Image.open(io.BytesIO(data)) as im:
            assert im.size[0] == width, f"{path.name} is {im.size}"
            assert im.size[1] == int(round(width * meta["ratio"][1] / meta["ratio"][0]))
        assert len(data) <= MAX_BYTES, f"{path.name} is {len(data) // 1024} KB"
    assert expected_height > 0


def test_every_registered_photo_declares_its_licence_and_source():
    for stem, meta in artwork.PHOTOS.items():
        assert meta["author"], stem
        assert "CC" in meta["licence"] or "Public domain" in meta["licence"], stem
        assert meta["licence_url"].startswith("http"), stem
        assert meta["page"].startswith("https://commons.wikimedia.org/"), stem
        assert len(meta["alt"]) >= MIN_ALT, f"{stem} alt text is too thin to be useful"
        assert meta["role"], stem


def test_no_photo_file_is_shipped_without_a_registry_entry():
    registered = {f"{stem}-{w}.webp" for stem, meta in artwork.PHOTOS.items()
                  for w in meta["widths"]}
    shipped = {p.name for p in PHOTOS_DIR.glob("*.webp")}
    assert shipped == registered, f"unregistered: {sorted(shipped - registered)}"


def test_photographs_are_never_placed_as_inline_images():
    """The design contract: imagery is a background layer, never content.

    A photograph sitting in the flow competes with the figures and invites a
    reader to treat a stock image as evidence. The registry therefore offers no
    ``<img>`` helper at all, and no page source may reference the photo folder in
    markup — only the stylesheet may, through ``url(...)``.
    """
    assert not hasattr(artwork, "photo")
    assert not hasattr(artwork, "photo_figure")
    for script in sorted((ROOT / "app").rglob("*.py")):
        for no, line in enumerate(script.read_text(encoding="utf-8").splitlines(), 1):
            where = f"{script.name}:{no}"
            assert "artwork.photo(" not in line, where
            assert 'class="photo-img' not in line, where
            # The SVG icons use a generic <img> helper; a photograph may never
            # reach one. A photo URL is only ever written into a style rule.
            if "<img" in line:
                assert "/app/static/photos" not in line, where
                assert "photo_url(" not in line, where
                assert "background_url(" not in line, where


def test_contract_cards_use_their_frame_as_a_background():
    assert artwork.contract_background("GOLDM") == \
        "/app/static/photos/contract-goldm-640.webp"
    assert artwork.contract_background("NOPE") == ""
    page = (ROOT / "app" / "pages" / "2_Gold_Contracts.py").read_text(encoding="utf-8")
    assert "--shot:url(" in page.replace(" ", "")
    assert "class=\"spec-media\"" not in page


def test_unknown_photo_names_degrade_to_nothing():
    # A typo must not leave a broken background or an empty credit on the page.
    assert artwork.photo_credit("nope") == ""
    assert artwork.photo_url("nope") == ""
    assert artwork.background_url("nope") == ""


def test_every_registered_photo_carries_its_credit():
    for stem in artwork.PHOTOS:
        credit = artwork.photo_credit(stem)
        assert artwork.PHOTOS[stem]["author"] in credit, stem
        assert artwork.PHOTOS[stem]["licence"] in credit, stem
        assert "creativecommons.org" in credit or "commons.wikimedia.org" in credit, stem


def test_every_photograph_is_a_background_layer():
    # Backgrounds are applied from CSS, so nothing in the markup would break if
    # one were dropped; the registry is what keeps them licensed and built.
    assert artwork.BACKGROUNDS == set(artwork.PHOTOS)
    for stem in artwork.BACKGROUNDS:
        assert artwork.background_url(stem).startswith("/app/static/photos/")
        role = artwork.PHOTOS[stem]["role"].lower()
        assert any(word in role for word in ("background", "texture", "behind")), stem


def test_every_stylesheet_background_resolves_to_a_shipped_file():
    css = rendered_css()
    urls = set(re.findall(r"url\((/app/static/[^)\s]+)\)", css))
    assert urls, "the stylesheet should reference the photo set"
    for url in urls:
        rel = pathlib.Path(url.split("/app/static/", 1)[1])
        assert (ROOT / "app" / "static" / rel).is_file(), f"CSS points at missing {url}"
    # the two SVG textures are inlined, not fetched
    assert "data:image/svg+xml;base64," in css


def test_hero_band_layers_navy_washes_over_the_photograph():
    css = rendered_css()
    block = css.split(".hero-band {", 1)[1].split("}", 1)[0]
    assert "background-image:" in block
    # navy first, photo last: the photograph must never sit above the text wash
    assert block.index("linear-gradient") < block.index("backdrop-hero-1600.webp")
    assert "backdrop-hero-960.webp" in css     # smaller file for phones
    assert "cover" in block
    # the headline sits on its own frosted pane inside the band
    assert ".hero-glass" in css and "backdrop-filter" in css
    assert ".hero-band h1 { color: #FFFFFF !important;" in css
    assert ".hero-sub" in css and "#CFD9E8" in css


def test_canvas_is_a_fixed_photographic_layer_under_the_glass():
    css = rendered_css()
    app_block = css.split(".stApp {", 1)[1].split("}", 1)[0]
    # the photograph and the grid texture are the bottom two layers of the canvas
    assert "url(/app/static/photos/backdrop-hero-1600.webp)" in app_block
    assert "data:image/svg+xml;base64," in app_block
    assert "background-attachment: fixed" in app_block
    assert "background-size: cover, cover, 520px 520px, cover, cover" in app_block
    # every data surface is glass, with a near-opaque pane under the grid
    assert "backdrop-filter: $BLUR" in css or "backdrop-filter: blur" in css
    assert "rgba(12,20,34,0.90)" in css        # dataframe pane


def test_closing_band_matches_the_hero_material():
    css = rendered_css()
    block = css.split(".disclaimer {", 1)[1].split("}", 1)[0]
    assert "tile-gold-512.webp" in block
    assert GOLD_BRIGHT in block


def test_glass_system_is_tokenised_and_has_a_fallback():
    css = rendered_css()
    # one blur token, used by the panels; nesting it would grey out the surface
    assert "--blur: blur(22px) saturate(140%)" in css
    assert "@supports not ((backdrop-filter" in css
    assert "prefers-reduced-motion" in css
    # charts stay crisp: the plot itself is never blurred
    chart = css.split('div[data-testid="stPlotlyChart"] {', 1)[1].split("}", 1)[0]
    assert "backdrop-filter" not in chart


def test_rail_is_collapsible_with_both_controls_visible():
    # The rail may not be pinned open at any width: Streamlit remembers a
    # collapsed state per browser, and a wide screen must still be able to
    # reopen it, so the chevron inside the rail and the pill over the canvas
    # are both styled as real controls rather than hidden.
    css = rendered_css()
    assert '[data-testid="stSidebarCollapseButton"] button' in css
    assert 'button[data-testid="stExpandSidebarButton"]' in css
    # the old rule matched [aria-expanded="false"] and forced the rail open;
    # with both controls styled it must not come back
    assert 'aria-expanded' not in css


def test_methodology_credit_list_covers_every_photograph():
    lines = artwork.credit_lines()
    assert len(lines) == len(artwork.PHOTOS)
    joined = "\n".join(lines)
    for stem, meta in artwork.PHOTOS.items():
        assert meta["author"] in joined, stem
        assert meta["licence"] in joined, stem


def test_generated_credit_document_matches_the_registry():
    doc = (ROOT / "docs" / "photo-credits.md").read_text(encoding="utf-8")
    for stem, meta in artwork.PHOTOS.items():
        assert stem in doc, stem
        assert meta["author"] in doc and meta["licence"] in doc, stem
    # Share-alike sources must be marked as such in the generated notes.
    for stem, meta in artwork.PHOTOS.items():
        if "sa" in meta["licence"].lower():
            assert "same licence" in doc, stem


def test_pipeline_names_every_stage_in_markup():
    page = (ROOT / "app" / "pages" / "8_Methodology.py").read_text(encoding="utf-8")
    for stage in ("Fetch", "Validate", "Normalize", "Spread", "Signals", "Backtest"):
        assert f'"name": "{stage}"' in page, stage
    assert "config/config.yaml" in page
    # it is drawn, not shipped as a picture: the old SVG must not come back
    assert "diagram-pipeline.svg" not in page


def _run_script(tmp_path: pathlib.Path, body: str):
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


def test_overview_band_renders_headline_status_and_real_actions(tmp_path):
    at = _run_script(tmp_path, '''
        from app.components import page_header
        page_header("Overview", "Four contracts on one scale", band="backdrop-hero",
                    actions=[("Open gold contracts", "gold-contracts"),
                             ("Methodology", "methodology")])
    ''')
    assert not at.exception, at.exception
    markup = "\n".join(m.value for m in at.markdown)
    assert '<section class="hero-band"' in markup
    # the headline sits on glass inside the band, not straight on the photograph
    assert 'class="hero-glass"' in markup and 'class="hero-inner"' in markup
    assert "<h1>Overview</h1>" in markup
    assert "hero-sub" in markup and "hero-meta" in markup
    assert "hero-chip" in markup and ("Current" in markup or "Stale" in markup)
    # the buttons are links to real routes, not decoration
    assert 'class="hero-cta" href="/gold-contracts"' in markup
    assert 'class="hero-cta ghost" href="/methodology"' in markup
    # the photograph is applied by the stylesheet, so the credit is the only
    # place the licence reaches the page
    assert "hero-credit" in markup and "Stevebidmead" in markup
    assert "CC0 1.0" in markup
    # and no photograph is placed in the flow
    assert "photo-img" not in markup and "/app/static/photos" not in markup


def test_page_header_without_a_band_is_a_compact_glass_strip(tmp_path):
    at = _run_script(tmp_path, '''
        from app.components import page_header
        page_header("Settings")
    ''')
    assert not at.exception, at.exception
    markup = "\n".join(m.value for m in at.markdown)
    assert 'class="pagehead"' in markup
    assert "hero-band" not in markup and "hero-credit" not in markup
    assert "status-chip" in markup
