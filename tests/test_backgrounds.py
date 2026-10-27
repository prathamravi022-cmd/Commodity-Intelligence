"""UIX-BG-01: one canvas per page, and it resolves to a shipped scene.

These invariants keep the per-page backgrounds honest:

* every page in the navigation registry has exactly one background, and no
  background exists for a page that is not navigable;
* every scene file named in the registry is a real SVG on disk, and no scene is
  shipped that the registry does not use;
* the stylesheet carries one scoped rule per page, and every URL in it resolves;
* the scenes and the generated CSS stay inside the product palette;
* the marker div is emitted by ``page_header`` — that is what selects the canvas,
  so if it stopped rendering, every page would silently fall back to one picture.

The palette rule matters most for the scenes: they are generated art, so a
stray colour would never fail anybody's code review — it would just quietly put
a teal or purple wash behind a financial table.
"""
from __future__ import annotations

import pathlib
import re
import shutil
import textwrap
import xml.etree.ElementTree as ET

import pytest
from streamlit.testing.v1 import AppTest

from app import artwork, backgrounds
from app.components import NAV_PAGES

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCENES_DIR = ROOT / "app" / "static" / "backgrounds"

TITLES = [page["title"] for page in NAV_PAGES]


def test_every_navigable_page_has_a_background():
    assert list(backgrounds.PAGE_BACKGROUNDS) == TITLES, (
        "the registry must cover every page, in navigation order"
    )


def test_no_background_exists_for_a_page_that_is_not_navigable():
    extra = set(backgrounds.PAGE_BACKGROUNDS) - set(TITLES)
    assert not extra, f"backgrounds for unknown pages: {sorted(extra)}"


@pytest.mark.parametrize("title", TITLES)
def test_each_background_declares_a_complete_composition(title):
    cfg = backgrounds.config_for(title)
    assert cfg is not None
    for key in ("scene", "photo", "focal", "scene_position", "glow",
                "glow_alpha", "scrim", "role"):
        assert key in cfg, f"{title} is missing {key}"
    # the light source is aimed, not defaulted
    assert len(cfg["glow"]) == 2
    assert 0.0 < cfg["glow_alpha"] <= 0.30
    # a scene-only page needs a lighter wash or the art is invisible; a
    # photographic page needs a heavier one or figures lose contrast
    assert 0.45 <= cfg["scrim"] <= 0.95
    assert cfg["role"].strip()


@pytest.mark.parametrize("title", TITLES)
def test_each_page_gets_its_own_scene(title):
    scene = backgrounds.config_for(title)["scene"]
    assert scene.endswith(".svg")
    assert scene in {cfg["scene"] for cfg in backgrounds.PAGE_BACKGROUNDS.values()}

    used = [cfg["scene"] for cfg in backgrounds.PAGE_BACKGROUNDS.values()]
    assert len(used) == len(set(used)), "two pages share one scene"


def test_every_registered_scene_is_a_real_svg_with_a_viewbox():
    for cfg in backgrounds.PAGE_BACKGROUNDS.values():
        path = SCENES_DIR / cfg["scene"]
        assert path.is_file(), f"missing scene {path.name}"
        root = ET.parse(path).getroot()
        assert root.tag.endswith("svg"), path.name
        assert root.get("viewBox") == "0 0 1600 900", path.name


def test_no_scene_is_shipped_that_the_registry_does_not_use():
    registered = {cfg["scene"] for cfg in backgrounds.PAGE_BACKGROUNDS.values()}
    shipped = {p.name for p in SCENES_DIR.glob("*.svg")}
    assert shipped == registered, f"orphaned scenes: {sorted(shipped - registered)}"


def test_scenes_and_generated_css_stay_inside_the_palette():
    for path in sorted(SCENES_DIR.glob("*.svg")):
        violations = artwork.palette_violations(path.read_text(encoding="utf-8"))
        assert not violations, f"{path.name}: {violations}"
    css = backgrounds.scoped_css()
    assert not artwork.palette_violations(css), artwork.palette_violations(css)


@pytest.mark.parametrize("title", TITLES)
def test_a_background_photograph_is_registered_and_licensed(title):
    photo = backgrounds.config_for(title)["photo"]
    if not photo:
        return
    assert photo in artwork.PHOTOS, photo
    assert photo in artwork.BACKGROUNDS, photo
    url = artwork.background_url(photo)
    rel = pathlib.Path(url.split("/app/static/", 1)[1])
    assert (ROOT / "app" / "static" / rel).is_file(), url


def test_stylesheet_carries_one_scoped_rule_per_page_in_navigation_order():
    css = backgrounds.scoped_css()
    keys = re.findall(r'\.stApp:has\(\.page-scope\[data-bg="([a-z0-9-]+)"\]\)', css)
    assert keys == [backgrounds.slug_for(title) for title in TITLES]


def test_every_scene_url_in_the_stylesheet_resolves():
    urls = set(re.findall(r"url\((/app/static/backgrounds/[^)\s]+)\)",
                          backgrounds.scoped_css()))
    assert len(urls) == len(TITLES)
    for url in urls:
        rel = pathlib.Path(url.split("/app/static/", 1)[1])
        assert (ROOT / "app" / "static" / rel).is_file(), f"404: {url}"


def test_each_canvas_layers_a_wash_between_the_picture_and_the_page():
    for title in TITLES:
        images, sizes, positions = backgrounds.layers(title)
        assert len(images) == len(sizes) == len(positions)
        # the scene is above the navy wash, and the wash is above any photograph
        scene_index = next(i for i, layer in enumerate(images) if layer.startswith("url("))
        photo_indices = [i for i, layer in enumerate(images)
                         if layer.startswith("url(") and i != scene_index]
        scrim_index = next(i for i, layer in enumerate(images)
                           if layer.startswith("linear-gradient"))
        assert scene_index < scrim_index, f"{title}: wash covers the scene"
        for index in photo_indices:
            assert scrim_index < index, f"{title}: photograph sits above the wash"
        # the canvas is pinned, so panels glide over a still picture
        assert set(sizes) == {"cover"}


def test_base_canvas_survives_as_the_fallback():
    # Without :has() support the page keeps the default photographic canvas, so
    # the base rule must stay complete and must stay before the page rules.
    from app.theme import rendered_css

    css = rendered_css()
    base = css.split(".stApp {", 1)[1].split("}", 1)[0]
    assert "backdrop-hero-1600.webp" in base
    assert "background-attachment: fixed" in base
    assert '.page-scope { display: none; }' in css
    assert css.index(".stApp {") < css.index(".stApp:has(")


def test_unknown_pages_degrade_to_the_default_canvas():
    assert backgrounds.config_for("Not A Page") is None
    assert backgrounds.layers("Not A Page") == ([], [], [])
    assert backgrounds.canvas_css("Not A Page") == ""
    assert backgrounds.marker("Not A Page") == ""


def test_marker_keys_are_url_safe():
    for title in TITLES:
        key = backgrounds.slug_for(title)
        assert re.fullmatch(r"[a-z0-9-]+", key), key
    assert backgrounds.slug_for("Spread Analytics") == "spread-analytics"


def _run_script(tmp_path: pathlib.Path, body: str) -> AppTest:
    tree = tmp_path / "app"
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


def test_page_header_selects_its_own_canvas(tmp_path):
    at = _run_script(tmp_path, '''
        from app.components import page_header
        page_header("Spread Analytics", "Pairwise spreads")
    ''')
    assert not at.exception, at.exception
    markup = "\n".join(m.value for m in at.markdown)
    assert 'class="page-scope" data-bg="spread-analytics"' in markup


def test_two_pages_render_two_different_markers(tmp_path):
    at = _run_script(tmp_path, '''
        from app.components import page_header
        page_header("Signal Explorer", "Signals")
    ''')
    assert not at.exception, at.exception
    markup = "\n".join(m.value for m in at.markdown)
    assert 'data-bg="signal-explorer"' in markup
    assert 'data-bg="overview"' not in markup
