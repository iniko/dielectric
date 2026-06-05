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
.venv/bin/python -m pytest                  # 86 lib tests, coverage gate 85% (CI: --cov-fail-under=85)
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
`MultiPoleRelaxation` is the configurable "number of poles" model and overrides `param_names`/
`params`/`with_params` to expose a **flat** parameter vector for the generic fitter.

**`Spectrum` (`spectrum.py`) is the single value object every layer consumes.** By the time a
`Spectrum` exists it is guaranteed to be in the internal convention — sign detection happens *only*
at the I/O boundary, so nothing downstream re-checks it.

**The data pipeline:** `io/csv_loader.py` (Agilent 85070 + generic) → `io/campaign.py`
(`MeasurementSet`/`ValidationSet`/`Campaign`, load *any number* of sets via `from_glob`) →
`uncertainty/typea.py` `combine_repeats` (complex mean + per-component SEM, with a k·MAD repeat
outlier screen) → `fitting/engine.py` (generic NLLS) → `fitting/selection.py` (auto-select) →
`verification/*` → `reporting/*`.

**Fitting (`fitting/`):** `engine.fit` minimises stacked `[Re(resid), Im(resid)]`, optimises τ in
**log10 space** (mapping covariance back via the delta method) — see the sign/log notes below —
weights by the Type A SEM, and runs a small multistart. `selection.select_model` ranks candidates by
**AICc/BIC on N = 2·n_freq**, then recommends the most parsimonious model that (a) fits comparably
well (R² within tol) and (b) is *identifiable* — it flags `degenerate` fits (a parameter with huge
relative uncertainty, e.g. a slow pole absorbing the DC-conduction tail) and `overparam` fits, and
never trades a good-but-underdetermined fit for a qualitatively worse one. `force_model=`/`n_poles=`
override while still reporting where the choice ranks.

**Backend** (`backend/app/`): `services.py` is the ONLY place that touches the library; `main.py`
is HTTP plumbing; `store.py` is an in-memory dict. Schemas (`schemas.py`) mirror library outputs and
contain no numerics. `services._finite()` clamps inf/nan (AICc, dof) for JSON. Besides the one-shot
`POST /campaigns/{id}/analyze`, the API is decomposed into **per-step endpoints** for the stepwise
UI: `GET /sets/{id}/repeats` (Type A band + distribution), `POST /campaigns/{id}/fit` (re-fittable;
caches the fit in `STORE.fits`), `GET /campaigns/{id}/kk` (predicted-vs-measured ε′ arrays),
`POST /sets/{id}/reference-match`, `POST /sets/{id}/saline-sweep`. Numerics for these live in the
library (`uncertainty.typea.confidence_band`/`repeat_distribution`, `verification.reference_overlay`)
— services stays a thin mapper. NB: analysis results/verdicts are keyed by sample **name**
(`SetSummary.name`), not the upload UUID (`SetSummary.id`).

**Frontend** (`frontend/src/`): two top-level workflows in `workflows/`. AnalysisWorkflow is a
**free-navigation stepper** (`components/Stepper.tsx`) over Load → Repeats → Model fit →
Kramers-Kronig → Validation → Reference match → Report, with shared state in `AnalysisContext.tsx`
(`ensureCampaign`/`ensureFit`/`ensureAnalysis` memoize backend calls by a signature of set-ids +
fit request). Each step lives in `workflows/steps/`. BudgetWorkflow = live GUM sandbox. Plotly via
`react-plotly.js/factory` + `plotly.js-dist-min` (types declared in `shims.d.ts`); plot components in
`components/Plots.tsx`. The Load step stages files client-side (per-file × unload) and only uploads a
set on "Load". Model customization is **constrained** (family + poles + DC-σ toggle); fixing
individual parameters is deliberately rejected backend-side. `types.ts` mirrors the backend schemas —
keep them in sync when changing the API.

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
  figures, no deps); `services.generate_report` + the `/report?fmt=` route expose all three.
- **scikit-learn / seaborn / statsmodels are intentionally NOT dependencies** — numpy (k·MAD),
  matplotlib, and direct AIC/BIC are the right, simpler tools. Don't add them.
- **mypy --strict + numpy**: model `epsilon()` returns are wrapped in `np.asarray(..., dtype=
  np.complex128)` because arithmetic widens to `complexfloating[Any]`. Use the `FloatArray`/
  `ComplexArray`/`BoolArray` aliases from `units.py`.
- Few-repeat data is genuinely underdetermined — selection stays in the conductive family and flags
  it; this is intended, not a bug (≥~8 repeats give the stable Cole-Cole + DC σ result).
