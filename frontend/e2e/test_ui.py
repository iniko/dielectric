"""End-to-end UI smoke test (start backend on :8001 and frontend on :5173 first).

    uvicorn backend.app.main:app --port 8001 &
    (cd frontend && npm run dev) &
    python frontend/e2e/test_ui.py
"""

import glob
import os
import sys
from playwright.sync_api import sync_playwright

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
meas = sorted(glob.glob(f"{ROOT}/data/h02s19m*.csv"))[:12]
val = sorted(glob.glob(f"{ROOT}/data/h02v*.csv"))[:10]
obs = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1600})
    page.goto("http://localhost:5173")
    page.wait_for_load_state("networkidle")

    # (1) header + tabs
    obs.append(("header 'dielectric'", page.locator("h1", has_text="dielectric").count() == 1))
    obs.append(("tab Dielectric Analysis", page.get_by_role("button", name="Dielectric Analysis").count() == 1))
    obs.append(("tab Uncertainty Budget", page.get_by_role("button", name="Uncertainty Budget").count() == 1))

    # (2) Budget tab
    page.get_by_role("button", name="Uncertainty Budget").click()
    page.wait_for_timeout(1500)
    page.wait_for_selector("text=combined standard uncertainty", timeout=8000)
    obs.append(("budget table present", page.locator("text=combined standard uncertainty").count() >= 1))
    largest = page.locator("text=largest:").first.inner_text()
    obs.append((f"largest contributor badge = '{largest}'", "input/inversion" in largest))
    page.screenshot(path="/tmp/diel_budget.png", full_page=True)

    # (3) Analysis tab
    page.get_by_role("button", name="Dielectric Analysis").click()
    page.wait_for_timeout(500)
    file_inputs = page.locator('input[type="file"]')
    obs.append(("two file dropzones", file_inputs.count() == 2))
    file_inputs.nth(0).set_input_files(meas)
    page.wait_for_timeout(1200)
    file_inputs.nth(1).set_input_files(val)
    page.wait_for_timeout(1200)
    # set cards rendered?
    obs.append(("measurement set card shows repeats", page.locator("text=/\\d+\\/\\d+ repeats/").count() >= 1))
    page.screenshot(path="/tmp/diel_analysis_setup.png", full_page=True)

    page.get_by_role("button", name="Run analysis").click()
    # analysis runs the full pipeline; wait for the result panel
    page.wait_for_selector("text=Sample:", timeout=60000)
    page.wait_for_timeout(2500)  # let plots render

    obs.append(("chosen model Cole-Cole + DC sigma", page.locator("text=Cole-Cole + DC").count() >= 1))
    banner = page.locator("text=VALIDATED").first
    banner_text = banner.inner_text() if banner.count() else "(no banner)"
    obs.append((f"validation banner = '{banner_text[:60]}'", "VALIDATED" in banner_text and "NOT" not in banner_text))
    obs.append(("Bode label", page.locator("text=Bode").count() >= 1))
    obs.append(("Cole-Cole label", page.locator("text=Cole-Cole").count() >= 1))
    obs.append(("methods paragraph", page.locator("text=non-linear least squares").count() >= 1))
    obs.append(("plotly svg rendered", page.locator(".plot-container, .js-plotly-plot").count() >= 2))
    page.screenshot(path="/tmp/diel_analysis_results.png", full_page=True)

    browser.close()

print("\n=== E2E OBSERVATIONS ===")
ok = True
for label, passed in obs:
    print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
    ok = ok and passed
print("=== " + ("ALL PASSED" if ok else "SOME FAILED") + " ===")
sys.exit(0 if ok else 1)
