# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A dielectric spectroscopy analysis toolkit for **already-inverted** complex permittivity spectra
ε\*(f) (e.g. Agilent/Keysight 85070 probe exports). Raw VNA S11 calibration/inversion is **out of
scope** — the input *is* ε\*(f). Audience: incoming PhD students producing publication-ready results,
so the design bias is "correct for experts, hard to misuse for novices" (fail loud, cite sources,
make every output reproducible). Three layers, all on `main`:

- `dielectric/` — the permanent asset: a typed, tested Python library.
- `backend/app/` — a thin FastAPI orchestrator (no numerics; maps the library to JSON).
- `frontend/` — a React/TS/Vite/Tailwind/Plotly UI over the API.

## Commands

Use the project venv (`.venv/bin/...`). Install: `pip install -e ".[dev,report,hdf5,web]"`.

```bash
# Library gates (must all pass before committing)
.venv/bin/ruff check .                      # lints the WHOLE repo (see exclusions in pyproject)
.venv/bin/mypy dielectric                   # strict
.venv/bin/python -m pytest                  # 100 lib tests, coverage gate 85% (CI: --cov-fail-under=85)
.venv/bin/python -m pytest tests/test_fitting.py::test_conductivity_recovered   # single test

# Backend
.venv/bin/mypy backend/app
.venv/bin/pytest backend/tests              # NOTE: use the console script OR `python -m pytest`;
                                            # backend/pytest.ini sets pythonpath=.. so `import backend` works
uvicorn backend.app.main:app --port 8001    # 8000 is taken on this machine; use 8001

# Frontend (in frontend/)
npm install && npm run build                # tsc -b && vite build (the CI gate)
npm run dev                                 # http://localhost:5173, proxies /api -> :8001

# End-to-end (start backend on 8001 + frontend on 5173 first)
.venv/bin/python frontend/e2e/test_ui.py    # headless Playwright smoke test on the real h02 data

# Worked example / CLI on the bundled real data
.venv/bin/python examples/worked_example.py
.venv/bin/dielectric analyze --measure "data/h02s19m*.csv" --validate "data/h02v*.csv" --reference saline --out out/
```

CI (`.github/workflows/ci.yml`) has 3 jobs: **library** (3.10–3.12: ruff + mypy --strict + pytest),
**backend** (mypy + pytest), **frontend** (build). `ruff check .` includes the bundled
`.claude/skills/` scripts unless excluded — `pyproject` already excludes `.claude`, `out`, `matlab`,
`frontend`.

## Architecture (the parts that span files)

**Everything is written against the `DielectricModel` ABC** (`dielectric/models/base.py`), never
concrete classes. A model is an immutable frozen dataclass exposing `epsilon(f) -> complex`,
`param_names`, `params`, and `provenance`. Reference materials are *pre-configured model instances*,
so library materials compose with fitting/comparison/uncertainty exactly like a user-fitted model.
`MultiPoleRelaxation` is the configurable "number of poles" engine and overrides `param_names`/
`params`/`with_params` to expose a **flat** parameter vector for the generic fitter; with
`fixed_alpha=True` it is the **Debye ladder** (per-pole α pinned to 0 and dropped from the fitted
vector), which is how "Debye (N poles) + DC σ" is realised on the same machinery.

**`Spectrum` (`spectrum.py`) is the single value object every layer consumes.** By the time a
`Spectrum` exists it is guaranteed to be in the internal convention — sign detection happens *only*
at the I/O boundary, so nothing downstream re-checks it.

**The data pipeline:** `io/csv_loader.py` (Agilent 85070 + generic) → `io/campaign.py`
(`MeasurementSet`/`ValidationSet`/`Campaign`, load *any number* of sets via `from_glob`) →
`uncertainty/typea.py` `combine_repeats` (complex mean + per-component SEM, with a k·MAD/Hampel
repeat outlier screen) → `fitting/engine.py` (generic NLLS) → `fitting/selection.py` (auto-select) →
`verification/*` → `reporting/*`.

**Repeat exclusion is transparent + auditable.** `combine_repeats` always returns `repeat_zscores`
(original order) plus `outlier_k_used`/`manual_exclude`/`manual_keep`, and `TypeAResult.reason(i)`
explains each keep/drop. The screen is a deliberate, recorded choice: it's user-adjustable
(threshold, **keep-all-with-warning**, per-repeat manual override) via `POST /sets/{id}/screening`
(stored in `STORE.screening`, propagated through the pipeline by `services._screened_type_a`), the
Repeats step shows a per-repeat z-score/filename/reason table + a with/without **impact** readout
(reusing `comparison.compare_spectra`), and the exclusion is **disclosed** in
`methods_paragraph` + the `ReproducibilityManifest`. Never silently drop repeats — that non-disclosure
is the rigor failure, not the algorithm.

**Fitting (`fitting/`):** `engine.fit` minimises stacked `[Re(resid), Im(resid)]`, optimises τ in
**log10 space** (mapping covariance back via the delta method) — see the sign/log notes below —
weights by the Type A SEM, and runs a small multistart. It stores the per-point σ it weighted by on
`FitResult.sigma_used`, so `FitResult.standardized_residuals` (raw ÷ σ) are dimensionless "pulls" with
`Σ(pull²) == χ²` — the fit step plots these (with ±1σ/±2σ bands) by default, with a toggle to the raw
dual-axis (Δε′ / Δε″|Δσ) view. The engine also stores **per-component** goodness on `FitResult`
(`msp_real`/`msp_imag` = mean squared pull per ε′/ε″ — the honest "fits within Type A uncertainty"
metric; `r_squared_real`/`imag` secondary, may be negative). **Models use a compositional label
grammar** (`fitting/fitters.py`): `family [(N poles)] [+ DC σ]` — `compose_fitter`/`model_label`/
`parse_model_label` are the single source of truth, and `fitting/catalog.py` `model_info(label)`
derives the equation + plain-language description from it (no parallel hand-map). The default panel
is **11 candidates**: the 5 classics (Debye, Cole-Cole, Cole-Davidson, Havriliak-Negami, Jonscher;
single-pole, no DC) + the Debye and Cole-Cole ladders at 1–3 poles + DC σ. `selection.select_model`
ranks by **AICc/BIC on N = 2·n_freq**, recommends the most parsimonious model that (a) fits comparably
well (R² within tol) and (b) is *identifiable* (flags `degenerate`/`overparam`), records a
machine-readable `RankedFit.excluded_reason` per candidate + a `ModelSelectionResult.rationale`
sentence, and warns on χ²ᵣ ≫ 1 misfit and on poles peaking outside the measured band. `force_model=`
(a family or full label), `n_poles=`, and `dc_sigma=` **compose** into one forced model (a conflict
raises); given alone, `n_poles`/`dc_sigma` constrain the panel and auto-select (not an override).
Old `MultiPole(N=k)` labels are rejected with a grammar-help error. The candidate models, the exact
cost function, and the R²-vs-reduced-χ² distinction are documented in `docs/model-fitting.md`.

**Backend** (`backend/app/`): `services.py` is the ONLY place that touches the library; `main.py`
is HTTP plumbing; `store.py` is an in-memory dict. Schemas (`schemas.py`) mirror library outputs and
contain no numerics. `services._finite()` clamps inf/nan (AICc, dof) for JSON. Besides the one-shot
`POST /campaigns/{id}/analyze`, the API is decomposed into **per-step endpoints** for the stepwise
UI: `GET /sets/{id}/repeats` (Type A band + distribution), `POST /campaigns/{id}/fit` (re-fittable;
caches the fit in `STORE.fits`), `GET /campaigns/{id}/kk` (predicted-vs-measured ε′ arrays),
`POST /sets/{id}/reference-match`, `POST /sets/{id}/saline-sweep`,
`POST /campaigns/{id}/compare` (batch-vs-batch), `POST /sets/{id}/screening` (set the repeat
outlier-screening choice → invalidates dependent fit/analysis caches),
`GET`/`POST /sets/{id}/validation` (a validation set's **editable** reference config — saline by
molarity or mass %, seawater salinity, any standard — linked to measurement batch ids; recomputes the
verdict+overlay+sweep and invalidates caches so the banner/report update live), and
`GET /campaigns/{id}/compare/report` (batch-comparison report, pdf|docx|html). Numerics for these
live in the library
(`uncertainty.typea.confidence_band`/`repeat_distribution`, `verification.reference_overlay`,
`comparison.compare_spectra`/`compare_parameters`) — services stays a thin mapper. NB: analysis
results/verdicts and compare batches are keyed by sample **name** (`SetSummary.name`), not the upload
UUID (`SetSummary.id`).

**Frontend** (`frontend/src/`): two top-level workflows in `workflows/`. AnalysisWorkflow is a
**free-navigation stepper** (`components/Stepper.tsx`) over Load → Repeats → Model fit →
Kramers-Kronig → Validation → Reference match → Compare → Report (the **Compare** step is enabled
only with ≥2 measurement batches; it overlays them and z-scores/per-frequency-tests the differences),
with shared state in `AnalysisContext.tsx`
(`ensureCampaign`/`ensureFit`/`ensureAnalysis` memoize backend calls by a signature of set-ids +
fit request). Each step lives in `workflows/steps/`. BudgetWorkflow = live GUM sandbox. Plotly via
`react-plotly.js/factory` + `plotly.js-dist-min` (types declared in `shims.d.ts`); plot components in
`components/Plots.tsx`. The Load step is **batch-centric**: it stages files client-side (per-file ×
unload) and each measurement *batch* card can have a validation set **attached** to it (its reference
config) — so it's explicit which batch a validation QC belongs to, and the Validation step lets you
**edit** that reference live. NB: measurement batch names are auto-disambiguated server-side
(`make_measurement_set`), because the fits cache is keyed by sample name — same-named batches would
otherwise collapse and break the comparison. Model customization is **constrained** (family + poles + DC-σ toggle); fixing
individual parameters is deliberately rejected backend-side. A global, persisted display preference
(`preferences.tsx`, `localStorage`) toggles the lossy quantity between **effective conductivity σ
(default)** and dielectric loss ε″; it's a pure client-side conversion (`σ = 2π·f·ε₀·ε″`) threaded as
a `mode` prop into the loss-axis plots (Bode, overlays, residuals, repeat/compare bands). The
Cole-Cole/Argand plot stays −Im(ε*) by definition. `types.ts` mirrors the backend schemas — keep them
in sync when changing the API.

## Domain conventions you must respect

- **Sign convention is engineering `e^{jωt}`**: internally store ε\* with **Im(ε\*) < 0 for lossy
  media**. So `σ_eff = -ω·ε₀·Im(ε*)`, Kramers-Kronig carries a flipped sign, and Cole-Cole plots
  show `-Im(ε*)`. Vendor exports store **positive** loss; `convention.py` is the *only* place sign is
  flipped — it negates on a positive median and emits a `ConventionWarning` (never silently fixes).
  The reporting layer displays the conventional positive `ε'' = -Im(ε*)`.
- **τ (and any multi-decade parameter) must be fit in log10 space** or the scipy finite-difference
  Jacobian floor destroys its column and the fit silently diverges. The prepackaged fitters already
  pass `log_scale=("tau",)`.
- **Reference data is confidence-flagged.** `Provenance.confidence` is `HIGH` or `VERIFY`. The
  embedded tissue parameters (Gabriel/IT'IS) are `VERIFY` (assembled offline) — reports flag them so
  a student never cites an unconfirmed value bare. `reference/_updater.py` documents the network-gated
  refresh that would promote them to `HIGH`. Do not silently treat VERIFY values as confirmed.
- Greek/symbolic identifiers (`eps_inf`, `tau`, `alpha`, `sigma_dc`) are deliberate to match the
  physics; ruff's `N`/`RUF001-003` naming rules are intentionally relaxed in `pyproject`.

## Gotchas

- **Reports**: the `report` extra uses **fpdf2** (not WeasyPrint). fpdf2 core fonts are latin-1, so
  `report_pdf.py` has an `_ascii()` map for ε/ω/τ/± etc., and `multi_cell` needs
  `new_x="LMARGIN", new_y="NEXT"`. There are three renderers off the one `ReportData`
  (`assemble_report`): `render_pdf`, `render_docx`, and `render_html` (self-contained, base64-embedded
  figures, no deps); `services.generate_report` + the `/report?fmt=` route expose all three. Each
  renderer also exposes a **section-writer** (`write_report_*` / `write_comparison_*` /
  `report_body_html` / `comparison_body_html`) so `campaign_report.py` stitches every batch's report
  **and** the comparison into one **combined campaign report** (`render_campaign_{pdf,docx,html}`,
  served at `GET /campaigns/{id}/campaign-report`).
- **Backend test isolation**: `backend/tests/conftest.py` clears the process-global `STORE` before
  every test — required because the in-memory store would otherwise leak sets/campaigns across tests
  (and the batch-name disambiguation would change names a test expects).
- **scikit-learn / seaborn / statsmodels are intentionally NOT dependencies** — numpy (k·MAD),
  matplotlib, and direct AIC/BIC are the right, simpler tools. Don't add them.
- **mypy --strict + numpy**: model `epsilon()` returns are wrapped in `np.asarray(..., dtype=
  np.complex128)` because arithmetic widens to `complexfloating[Any]`. Use the `FloatArray`/
  `ComplexArray`/`BoolArray` aliases from `units.py`.
- Few-repeat data is genuinely underdetermined — the free-α Cole-Cole ladders go `degenerate` fast
  (α aliases the conduction tail), so selection often lands on a **Debye-ladder** model (pinned α,
  fewer params, identifiable) rather than Cole-Cole. This is intended, not a bug: with the 11-model
  panel the recommendation is the most parsimonious *identifiable* fit, which on the bundled h02 data
  is `Debye (3 poles) + DC σ` (the `rationale` explains why lower-AICc Cole-Cole candidates were
  excluded).
