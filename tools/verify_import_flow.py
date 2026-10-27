"""Browser verification of the manual import flow (roadmap 22/23/29/30).

Uploads a deliberately awkward CSV (renamed columns, mixed casing, an extra
column, one bad row), checks the mapping suggestions, validates, saves,
confirms the file / manifest / import history, checks that a second save is
refused, then restores data/ so the run leaves the repository as it found it.

The target date sits *outside* the fixture range so this can never delete a
generated fixture file, and restore() only removes the target if this script
wrote it.
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
URL = "http://localhost:8601/data-quality"
STAGED = ROOT / "tools" / "_upload_sample.csv"
REQUESTED = "2026-11-02"                  # Monday, outside the fixture range
TARGET = RAW / f"{REQUESTED}.csv"

assert not TARGET.exists(), f"{TARGET} already exists — refusing to touch it"

# Renamed, re-cased and reordered headers plus one out-of-range row.
CSV = (
    "scrip,Trade Date,expiry,Open,High,Low,Settlement Price,qty,Open Interest,Notes\n"
    "GOLDM,11/02/2026,01DEC2026,7299,7310,7295,7300,1000,5000,ok\n"
    "GOLDTEN,11/02/2026,28NOV2026,7280,7290,7275,7285,900,4200,ok\n"
    "GOLDPETAL,11/02/2026,30NOV2026,7280,7270,7275,7278,500,3000,high<low\n"
)

backups = {}
for rel in ("raw/manifest.json", "imports.json"):
    src = DATA / rel
    backups[rel] = src.read_bytes() if src.exists() else None


def restore():
    if TARGET.exists() and TARGET.read_text(encoding="utf-8").startswith("Symbol,Date"):
        TARGET.unlink()
    for rel, blob in backups.items():
        dst = DATA / rel
        if blob is None:
            dst.unlink(missing_ok=True)
        else:
            dst.write_bytes(blob)


def check(failures, cond, msg):
    if not cond:
        failures.append(msg)


def press(page, name):
    """Click a button after parking the pointer away from its help tooltip.

    Streamlit renders help tooltips in a portal that stays open over the
    button; a pointer sitting on the button intercepts the next click.
    """
    page.mouse.move(5, 5)
    page.wait_for_timeout(120)
    try:
        page.get_by_role("button", name=name, exact=True).click(timeout=8000)
    except Exception:
        dlg = page.locator('[data-testid="stDialog"]')
        print(f"CLICK BLOCKED on {name!r}; dialogs={dlg.count()}")
        for i in range(dlg.count()):
            print("  DIALOG", i, ":", dlg.nth(i).inner_text()[:300].replace("\n", " | "))
        page.screenshot(path=str(ROOT / "qa" / "screenshots" / "_blocked.png"))
        raise


def main() -> int:
    STAGED.write_text(CSV, encoding="utf-8")
    failures: list[str] = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(URL, wait_until="networkidle")
            page.get_by_text("Import a bhavcopy CSV").wait_for(timeout=30000)

            page.set_input_files("input[type=file]", str(STAGED))
            page.get_by_text("Column mapping").wait_for(timeout=20000)
            # Wait for the selects themselves, not just the heading above them.
            page.locator('div[data-testid="stSelectbox"]').first.wait_for(timeout=20000)
            page.wait_for_timeout(500)
            cbs = page.locator('div[data-testid="stSelectbox"] [role="combobox"]')
            check(failures, cbs.count() == 9,
                  f"expected 9 mapping selectors, found {cbs.count()}")
            mapped = {cbs.nth(i).get_attribute("aria-label"):
                      cbs.nth(i).get_attribute("value") for i in range(cbs.count())}
            for want, got in [("Symbol", "scrip"), ("Date", "Trade Date"),
                              ("ExpiryDate", "expiry"), ("Close", "Settlement Price"),
                              ("Volume", "qty"), ("OpenInterest", "Open Interest")]:
                check(failures, mapped.get(want) == got,
                      f"mapping wrong for {want}: {mapped.get(want)!r} (want {got!r})")
            body = page.inner_text("body")
            check(failures, "10 source columns" in body,
                  "extra uploaded column not counted in the summary")
            check(failures, "9/9 mapped" in body, "upload summary line wrong")

            # Set the requested date to the file's own session before validating.
            date_box = page.locator('div[data-testid="stDateInput"] input').first
            date_box.fill(REQUESTED)
            date_box.press("Enter")

            press(page, "Validate")
            page.get_by_text("Rows accepted").wait_for(timeout=20000)
            body = page.inner_text("body")
            check(failures, "PRICE_RANGE" in body,
                  "rejection reason PRICE_RANGE not surfaced in text")
            check(failures, "2" in body and "Rows rejected" in body,
                  "rejected-row KPI missing")
            check(failures, not TARGET.exists(), "Validate wrote to data/raw")

            press(page, "Save to data/raw")
            page.get_by_text(f"Saved {REQUESTED}.csv").wait_for(timeout=20000)
            check(failures, TARGET.exists(), "raw file was not written")

            if TARGET.exists():
                head = TARGET.read_text(encoding="utf-8").splitlines()[0]
                check(failures, head.split(",")[:3] == ["Symbol", "Date", "ExpiryDate"],
                      f"written file not canonical: {head}")
                check(failures, "Notes" not in head,
                      "non-canonical column survived into data/raw")
                sys.path.insert(0, str(ROOT))
                from src.validate.clean import validate_file
                clean, rejected, _ = validate_file(TARGET,
                                                   expected_date_str=REQUESTED)
                check(failures, len(clean) == 2
                      and list(rejected["__reason__"]) == ["PRICE_RANGE"],
                      "re-validation of the imported file disagrees")

            hist = json.loads((DATA / "imports.json").read_text(encoding="utf-8"))
            check(failures, hist and hist[-1].get("source") == "manual-upload",
                  "import history missing the record")
            manifest = json.loads((RAW / "manifest.json").read_text(encoding="utf-8"))
            check(failures, f"{REQUESTED}.csv" in manifest,
                  "manifest missing checksum for imported file")
            page.get_by_text("Import history — every manual import").click()
            page.wait_for_timeout(800)
            check(failures, f"{REQUESTED}.csv" in page.inner_text("body"),
                  "import history not rendered on the page")

            # The data-quality report must download with the facts in it.
            with page.expect_download(timeout=20000) as dl:
                press(page, "Download data-quality report")
            report = Path(dl.value.path()).read_text(encoding="utf-8")
            check(failures, "# Data quality report" in report,
                  "report export produced the wrong document")
            check(failures, "Coverage per contract" in report and "GOLDM" in report,
                  "report is missing coverage")
            check(failures, f"{REQUESTED}.csv" in report,
                  "report is missing the imported file's checksum row")

            # A second save of the same date must be refused without the checkbox.
            page.set_input_files("input[type=file]", str(STAGED))
            page.get_by_text("Column mapping").wait_for(timeout=20000)
            date_box = page.locator('div[data-testid="stDateInput"] input').first
            date_box.fill(REQUESTED)
            date_box.press("Enter")
            press(page, "Validate")
            page.get_by_text("Rows accepted").wait_for(timeout=20000)
            press(page, "Save to data/raw")
            page.get_by_text("already exists").wait_for(timeout=20000)
            check(failures, "already exists" in page.inner_text("body"),
                  "overwrite was not refused")

            page.screenshot(path=str(ROOT / "qa" / "screenshots" / "import-flow.png"))
            browser.close()
    finally:
        STAGED.unlink(missing_ok=True)
        restore()
    if failures:
        print("FAILURES:")
        for f in failures:
            print(" -", f)
        return 1
    print("import flow verified: map -> validate -> save -> history -> refuse-overwrite")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
