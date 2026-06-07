"""End-to-end UI smoke test (start backend on :8001 and frontend on :5173 first).

    uvicorn backend.app.main:app --port 8001 &
    (cd frontend && npm run dev) &
    python frontend/e2e/test_ui.py

Walks the stepwise Analysis workflow: load → repeats → fit → KK → validation → reference → report.
"""

import glob
import os
import sys
from playwright.sync_api import sync_playwright

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
meas = sorted(glob.glob(f"{ROOT}/data/h02s19m*.csv"))[:12]
val = sorted(glob.glob(f"{ROOT}/data/h02v*.csv"))[:10]
obs = []


def step(page, name, wait_selector=None, timeout=60000):
    """Click a stepper pill (accessible name includes its number, e.g. '2 Repeats')."""
    page.get_by_role("button", name=name).first.click()
    if wait_selector:
        page.wait_for_selector(wait_selector, timeout=timeout)
    page.wait_for_timeout(2000)  # let plots paint


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1800})
    page.goto("http://localhost:5173")
    page.wait_for_load_state("networkidle")

    # (1) header + tabs
    obs.append(("header 'dielectric'", page.locator("h1", has_text="dielectric").count() == 1))
    obs.append(("tab Dielectric Analysis",
                page.get_by_role("button", name="Dielectric Analysis").count() == 1))

    # (2) Budget tab (unchanged sandbox)
    page.get_by_role("button", name="Uncertainty Budget").click()
    page.wait_for_selector("text=combined standard uncertainty", timeout=8000)
    obs.append(("budget table present",
                page.locator("text=combined standard uncertainty").count() >= 1))

    # (3) Analysis tab — step 1: Load (batch-centric)
    page.get_by_role("button", name="Dielectric Analysis").click()
    page.wait_for_timeout(500)

    # batch A
    page.locator('input[type="file"]').first.set_input_files(meas)
    page.wait_for_timeout(500)
    obs.append(("staged → Load batch button",
                page.get_by_role("button", name="Load batch").count() >= 1))
    page.get_by_role("button", name="Load batch").click()
    page.wait_for_selector("text=/\\d+\\/\\d+ repeats/", timeout=15000)
    obs.append(("batch A card", page.locator("text=/\\d+\\/\\d+ repeats/").count() >= 1))

    # batch B (second batch → enables Compare)
    page.locator('input[type="file"]').first.set_input_files(val)
    page.wait_for_timeout(500)
    page.get_by_role("button", name="Load batch").click()
    page.wait_for_timeout(2000)
    obs.append(("two batch cards", page.locator("text=/\\d+\\/\\d+ repeats/").count() >= 2))

    # attach a validation set to batch A
    page.get_by_role("button", name="Attach validation (optional)").first.click()
    page.wait_for_timeout(400)
    page.locator('input[type="file"]').last.set_input_files(val)
    page.wait_for_timeout(400)
    page.get_by_role("button", name="Attach validation", exact=True).click()
    page.wait_for_selector("text=Attached validation", timeout=15000)
    obs.append(("validation attached to batch", page.locator("text=Attached validation").count() >= 1))
    page.screenshot(path="/tmp/diel_step1_load.png", full_page=True)

    # (4) step 2: Repeat statistics — transparent screening table + controls
    step(page, "Repeats")
    obs.append(("repeats band plot", page.locator(".js-plotly-plot").count() >= 2))
    obs.append(("distribution inspector", page.locator("text=Distribution inspector").count() >= 1))
    obs.append(("per-repeat z-score table", page.locator("text=threshold k").count() >= 1))
    obs.append(("screening method cited (Hampel)", page.locator("text=Hampel").count() >= 1))
    # flip 'keep all repeats' (the screening checkbox) and confirm the warning appears
    keep_all = page.locator('input[type="checkbox"]').first
    keep_all.click()
    page.wait_for_selector("text=Outlier screening is OFF", timeout=15000)
    obs.append(("keep-all warning", page.locator("text=Outlier screening is OFF").count() >= 1))
    # re-enable screening so downstream steps use the default
    keep_all.click()
    page.wait_for_timeout(1800)
    page.screenshot(path="/tmp/diel_step2_repeats.png", full_page=True)

    # (5) step 3: Model fit (waits for the ranking table, which only renders once the fit returns)
    step(page, "Model fit", wait_selector="text=ΔAICc")
    obs.append(("ranking table", page.locator("text=ΔAICc").count() >= 1))
    obs.append(("residuals normalized by default",
                page.locator("text=Standardized residuals").count() >= 1))
    obs.append(("residual view toggle", page.get_by_role("button", name="normalized").count() >= 1))
    page.get_by_role("button", name="raw", exact=True).first.click()  # switch to raw dual-axis
    page.wait_for_timeout(800)
    obs.append(("raw residual view selectable", page.locator(".js-plotly-plot").count() >= 1))
    obs.append(("chosen model badge Cole-Cole + DC",
                page.locator("span", has_text="Cole-Cole + DC").count() >= 1))
    page.screenshot(path="/tmp/diel_step3_fit.png", full_page=True)

    # (6) step 4: Kramers-Kronig
    step(page, "Kramers-Kronig", wait_selector="text=KK-predicted vs measured")
    obs.append(("KK predicted vs measured", page.locator("text=KK-predicted vs measured").count() >= 1))
    obs.append(("KK consistent badge", page.locator("text=KK consistent").count() >= 1))
    page.screenshot(path="/tmp/diel_step4_kk.png", full_page=True)

    # (7) step 5: Validation — per-batch verdict + editable reference card
    step(page, "Validation", wait_selector="text=QC set(s) passed")
    banner_text = page.locator("text=QC set(s) passed").first.inner_text()
    obs.append((f"validation banner = '{banner_text[:50]}'",
                "VALIDATED" in banner_text and "NOT VALIDATED" not in banner_text))
    obs.append(("per-batch PASS verdict", page.locator("text=PASS").count() >= 1))
    obs.append(("saline sweep in card", page.locator("text=Saline best-match sweep").count() >= 1))
    obs.append(("editable saline input", page.locator("text=molarity (mol/L)").count() >= 1))
    # flip the saline molarity ↔ mass-% toggle and confirm the field re-labels
    page.get_by_role("button", name="M", exact=True).first.click()
    page.wait_for_timeout(2000)
    obs.append(("saline %/M toggle", page.locator("text=NaCl (% w/w)").count() >= 1))
    page.screenshot(path="/tmp/diel_step5_validation.png", full_page=True)

    # (8) step 6: Reference match
    step(page, "Reference match", wait_selector="text=Per-frequency relative error")
    obs.append(("closest materials", page.locator("text=Closest materials").count() >= 1))
    obs.append(("per-frequency error plot",
                page.locator("text=Per-frequency relative error").count() >= 1))
    page.screenshot(path="/tmp/diel_step6_reference.png", full_page=True)

    # (9) step 7: Compare batches
    step(page, "Compare", wait_selector="text=Parameter differences")
    obs.append(("compare overlay", page.locator("text=Real permittivity ε′").count() >= 1))
    obs.append(("difference plot", page.locator("text=/Δε′/").count() >= 1))
    obs.append(("parameter-diff table", page.locator("text=Parameter differences").count() >= 1))
    obs.append(("conductivity panel by default (σ pref)",
                page.locator("text=Conductivity σ").count() >= 1))
    obs.append(("comparison report download buttons",
                page.get_by_role("button", name="HTML").count() >= 1))
    # flip the global loss-axis toggle to ε″ and confirm the lossy panel re-labels
    page.get_by_role("button", name="ε″", exact=True).click()
    page.wait_for_timeout(1500)
    obs.append(("toggle switches lossy panel to ε″", page.locator("text=Loss ε″").count() >= 1))
    page.screenshot(path="/tmp/diel_step7_compare.png", full_page=True)

    # (10) step 8: Report
    step(page, "Report", wait_selector="text=Download HTML report")
    obs.append(("methods paragraph", page.locator("text=non-linear least squares").count() >= 1))
    obs.append(("HTML report download",
                page.get_by_role("button", name="Download HTML report").count() >= 1))
    page.screenshot(path="/tmp/diel_step7_report.png", full_page=True)

    browser.close()

print("\n=== E2E OBSERVATIONS ===")
ok = True
for label, passed in obs:
    print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
    ok = ok and passed
print("=== " + ("ALL PASSED" if ok else "SOME FAILED") + " ===")
sys.exit(0 if ok else 1)
