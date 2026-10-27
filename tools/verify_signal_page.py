"""Browser check for the Signal Explorer research panel (41-50, 80).

Widget-to-output wiring is covered deterministically by
`tests/test_signal_explorer_page.py`; this script proves the parts only a
browser can: the page renders its sections, the charts actually draw, the audit
table opens, and nothing throws.
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
URL = "http://localhost:8601/signal-explorer"


def main() -> int:
    fails: list[str] = []
    console_errors: list[str] = []
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        page = b.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda e: console_errors.append(str(e)[:200]))
        page.on("console", lambda m: console_errors.append(m.text[:200])
                if m.type == "error" and "404" not in m.text else None)

        page.goto(URL, wait_until="networkidle")
        page.get_by_text("Episode timeline").wait_for(timeout=45000)
        page.wait_for_timeout(1500)
        body = page.inner_text("body")

        for needle in ["Threshold ladder", "Current state per pair", "Episode timeline",
                       "Episode detail", "How often, and how long",
                       "Calculation audit", "Alert log"]:
            if needle not in body:
                fails.append(f"missing section: {needle}")
        if "Traceback" in body or "StreamlitAPIException" in body:
            fails.append("exception rendered on the page")
        if "Sessions held" not in body:
            fails.append("episode detail metrics missing")

        charts = page.locator(".js-plotly-plot").count()
        if charts < 4:
            fails.append(f"expected at least 4 charts (z, timeline, spark, frequency), found {charts}")

        page.mouse.move(5, 5)
        page.get_by_text(
            "Calculation audit — the inputs behind the last z-values").click(force=True)
        page.wait_for_timeout(900)
        if "inputs used" not in page.inner_text("body"):
            fails.append("audit table did not open with its columns")

        page.screenshot(path=str(ROOT / "qa" / "screenshots" / "signal-research.png"))
        b.close()

    if console_errors:
        fails.append(f"browser errors: {console_errors[:3]}")
    if fails:
        print("FAILURES:")
        for f in fails:
            print(" -", f)
        return 1
    print("signal page verified: sections, 4+ charts drawn, audit table, no browser errors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
