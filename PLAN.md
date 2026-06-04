# Plan: Dielectric Spectroscopy Toolkit — core library (`dielectric`)

## Context

`STACK.md`, `WHAT-IT-DOES.md`, `data/`, and `.claude/` are all that remain on disk; the
Python package, backend, and frontend described in project memory no longer exist. This is a
**from-scratch recreation** of the core library, plus three new requirements you specified:

1. **Multi-set upload** — one "set" is a repeatability group (many repeat files of one sample).
   You can load *as many measurement sets as you want*, and *as many validation sets as you want*.
   Validation is optional; without it, results are labeled **"not validated."**
2. **Auto model-selection with override** — the toolkit examines which model (and **number of
   poles**) best fits, recommends it, but lets you override both.
3. **Literature / open-database reference library** — emphasis on **biological tissue**, for
   comparison.

**Decisions (confirmed with you):**
- **Scope this pass: core Python library only** (the permanent asset). Web UI (FastAPI/React or
  Streamlit) is deferred to a follow-up pass.
- **Validation = known-reference QC check**: a validation set is repeat measurements of a *known
  reference material* (the `h02v*` files look saline/water-like, ε'≈83, high loss). We confirm the
  probe/inversion is trustworthy by comparing the set's mean spectrum to that material's literature
  model. No validation set → campaign flagged "not validated."

**Environment caveat (important):** network access is blocked here, so the reference database is
shipped as an **embedded, citation-tagged snapshot** with a per-value confidence flag
(`HIGH` / `VERIFY`), plus a documented (not-run) `_updater` hook to refresh from IFAC Appendix C /
NPL MAT 23 when online. We will **not ship invented precision** — `VERIFY` values are flagged in
every report/comparison so a student never cites an unconfirmed number unknowingly.

**Intended outcome:** a typed, tested, CI-gated `dielectric` package where a PhD student can go
load → quality-check → (auto) fit → verify (literature + KK + reference QC) → uncertainty →
publication-ready export, reproducibly, from the `h02` data, via a CLI and a narrated worked example.

---

## Sign convention (replicate exactly — pervasive)

Engineering `e^{jωt}`: `ε* = ε' + j·Im(ε*)` with **Im(ε*) < 0 for lossy media**. Internally store
ε* with negative imaginary part. The Agilent 85070 exports store **positive** loss → the loader
**negates and WARNS** (never silently "fixes"). Downstream: `σ_eff = -ω·ε₀·Im(ε*)`; KK formulas
carry the flipped sign; Cole-Cole plots show `-Im(ε*)`. (Memory: `data-and-sign-convention`.)

---

## Package layout

```
pyproject.toml            # package metadata, deps, ruff/mypy/pytest config
.github/workflows/ci.yml  # lint + type + test gates
README.md                 # front door = narrated worked example (not API ref)
dielectric/
  __init__.py             # public API + __version__
  constants.py            # ε₀ and physical constants
  units.py                # typed units at I/O boundary (Hz/GHz, rel/abs permittivity) + conversions
  convention.py           # sign-convention detection + warnings
  spectrum.py             # Spectrum value object (f, eps_complex, band) + quality pass
  models/
    base.py               # DielectricModel ABC: epsilon(f)->complex, params, provenance, n_params
    provenance.py         # Citation/Provenance/Confidence value objects
    debye.py  cole_cole.py  cole_davidson.py  havriliak_negami.py  jonscher.py
    conductivity.py       # DC ionic conductivity term (composable)
    multipole.py          # MultiPoleRelaxation: sum of N Cole-Cole terms (+ optional DC σ) = "poles"
    mixing.py             # Maxwell-Garnett, Bruggeman, Looyenga (compose DielectricModel)
  fitting/
    engine.py             # generic NLLS on stacked re/im residuals; log_scale, SEM weighting, covariance
    result.py             # FitResult: params±u, residuals, GoF, AIC/BIC/AICc, provenance, manifest
    fitters.py            # fit_debye, fit_cole_cole, fit_cole_cole_conductivity, fit_multipole, ...
    selection.py          # auto model-selection + overparameterization guardrails + override API
  reference/
    materials.py          # ReferenceMaterial = preconfigured model instance + provenance + confidence
    tissues.py            # Gabriel/IT'IS 4-Cole-Cole tissues (microwave 2-term restriction)
    liquids.py            # water (Kaatze), saline (Stogryn/Peyman), seawater, methanol/ethanol
    database.py           # registry + query/search API (filter by class, e.g. "tissue")
    _updater.py           # network-gated refresh hook (documented, not run)
  verification/
    literature.py         # compare a fit/spectrum against reference materials (distance metrics)
    kramers_kronig.py     # KK consistency + residuals; warn on band-limited extrapolation
    validation.py         # known-reference QC: validation set vs literature -> validated/not-validated
  uncertainty/
    typea.py              # Type A repeat statistics across a set (mean spectrum + SEM)
    montecarlo.py         # MC propagation through an arbitrary user callable
    gum.py                # GUM/JCGM-100 budget engine + templates + input-uncertainty injection
  io/
    csv_loader.py         # Agilent 85070 loader + parameterized generic CSV (col idx/header/comment)
    touchstone.py         # .s1p
    hdf5.py               # optional (h5py)
    campaign.py           # MeasurementSet / ValidationSet / Campaign — multi-set loading + metadata schema
  dependence.py           # Arrhenius, VFT, concentration fits
  reporting/
    style.py              # one centralized publication plotting style
    formatting.py         # GUM significant-figure rounding (value ± uncertainty)
    tables.py             # paper-ready LaTeX + CSV tables
    figures.py            # captioned, provenance-stamped figures
    methods.py            # methods-paragraph generator
    bibliography.py       # BibTeX export of cited provenance
    manifest.py           # reproducibility manifest (input hash, version, settings, timestamp)
  cli.py                  # `dielectric analyze ...` end-to-end
examples/worked_example.py + .md   # narrated end-to-end on the h02 data
tests/                    # pytest mirror of modules
```

---

## Module design notes (the parts that carry risk)

**`models/base.py` — the one extension point.** `DielectricModel` ABC: `epsilon(f)->complex
ndarray`, immutable params (frozen dataclass), `provenance` (Citation), `param_names`,
`n_params`. Everything downstream (fitting, mixing, reference materials, verification, reporting)
is written against this ABC, never concrete classes. Reference materials are just pre-configured
instances, so library materials compose with fitting/comparison/uncertainty identically.

**`models/multipole.py` — the "number of poles" knob.** `MultiPoleRelaxation(eps_inf, terms=[(Δε,
τ, α), ...], sigma_dc=None)`. N = number of Cole-Cole terms. Reduces to Debye (one term, α=0),
Cole-Cole (one term), etc. This is what the auto-selector sweeps over and what your override sets.

**`fitting/engine.py`.** scipy `least_squares` on stacked `[Re(resid), Im(resid)]`. **τ optimized
in log10 space** (memory `fitting-log-scale-tau`: finite-difference Jacobian floor destroys the τ
column otherwise) — bounds transformed to log space, covariance mapped back via delta method
(`dx/dz = ln(10)·x`). Fits weighted by Type A SEM (`sigma=`) so reduced χ² is physical.

**`fitting/selection.py` — auto-selection + guardrails + override.**
- Candidate set: Debye, Cole-Cole, Cole-Davidson, Havriliak-Negami, Jonscher, and
  MultiPole(N=1,2,3) with/without DC conductivity.
- Rank by **AICc** (small-sample corrected) and **BIC**; expose the full ranking table.
- **Overparameterization guardrails (fail loud):** warn when `n_params` is large vs data points
  (e.g. HN/3-pole on too few points), or when added terms don't beat ΔAICc≳2. For the `h02` sample,
  expected winner is **Cole-Cole + DC conductivity** (memory notes ΔAIC≈700 vs pure relaxation).
- **Override API:** `select_model(spectrum, force_model=..., n_poles=...)` returns the chosen fit
  while still reporting where it ranks, so an override is informed, not blind.

**`reference/` — embedded snapshot, tissue emphasis, honest provenance.**
- `Confidence = {HIGH, VERIFY}` on every numeric value; `Provenance` carries authors/year/journal/DOI.
- **Tissues** (Gabriel 1996 / IT'IS, CC BY): blood, muscle, skin, fat, liver, brain grey/white,
  bone, kidney, lung, breast, heart — embedded as the **2-Cole-Cole microwave restriction**
  (ε∞ + dispersions 1–2 + σ_i), which is numerically exact for 200 MHz–20 GHz; µs/ms α-dispersion
  terms are documented-as-dropped rather than invented.
- **Liquids:** water (Kaatze 1989), saline (Stogryn 1971 / Peyman 2007), seawater (Klein–Swift),
  methanol/ethanol (NPL MAT 23). `HIGH` values shipped as trusted; `VERIFY` flagged in any output.
- `database.query(material_class="tissue")` etc. `_updater.py` documents refreshing from IFAC
  Appendix C / NPL MAT 23 when network is available (not executed in this pass).

**`io/campaign.py` — multi-set model (your new requirement).**
- `MeasurementSet`: a sample id + list of repeat spectra (the repeatability group) → Type A mean + SEM.
- `ValidationSet`: same, plus the **reference material id** it measures (for QC).
- `Campaign`: any number of measurement sets + any number of validation sets + typed/validated
  metadata schema. `campaign.validated` is True only if ≥1 validation set passes QC, else the
  campaign and all its exports are stamped **"NOT VALIDATED."**
- Glob loading: e.g. `MeasurementSet.from_glob("data/h02s19m*.csv")`,
  `ValidationSet.from_glob("data/h02v*.csv", reference="saline")`.

**`verification/validation.py` — known-reference QC.** Compare a `ValidationSet` mean spectrum to
its declared reference material's model over the measured band (relative RMS deviation in ε' and
ε''); pass/fail against a tolerance; produce a QC verdict the manifest and reports carry.

**`reporting/` — what makes it a *student publication* tool.**
- `formatting.py`: GUM rounding so uncertainty sets the digits (`ε∞ = 4.2 ± 0.3`); never a bare value.
- `methods.py`: publication-ready prose ("ε*(f) was fitted to a Havriliak-Negami model (eq. X,
  [cite]) by NLLS; KK residuals < Y%; validated against [material], max dev Z%"). Highest-leverage
  feature — prioritized.
- `manifest.py`: every FitResult + figure carries a reproducibility manifest (input file + content
  hash, model + all fit settings, full params, library version, timestamp) — automatic, so a figure
  regenerates 18 months later.
- `bibliography.py`: BibTeX for every cited provenance used in a report.
- `style.py`: one publication style applied everywhere; `figures.py` stamps captions with model, N,
  fit quality, and validation status.

---

## Skills usage (you asked to invoke the skills)

Invoked where they directly improve the deliverable, and I'll say so as I use them:
- **karpathy-guidelines** — coding discipline (surgical, no overcomplication) — applied throughout.
- **scientific-visualization** — `reporting/style.py` + `figures.py` (publication multi-panel,
  colorblind-safe, journal formatting).
- **citation-management** — validate the reference DB citations/DOIs and `bibliography.py` BibTeX.
- **scientific-writing** — `methods.py` prose generator (IMRAD-grade methods snippet).
- **statistical-analysis** / **statsmodels** — model-selection reporting (AIC/BIC), Type A stats.
- **scientific-critical-thinking** / **hypothesis-generation** — sanity-check the guardrail logic
  (what traps must fail loud).
- **scikit-learn**, **seaborn**, **matlab** — consulted only if a concrete need arises (e.g.
  metrics, quick EDA); not forced where not useful.
- **frontend-design / taste-skill / webapp-testing / docx / pdf** — belong to the deferred web-UI
  and document-export passes; **out of scope this pass** (noted rather than invoked pointlessly).

---

## Engineering standards / tooling

- `.venv` (Python 3.10) with numpy/scipy/pandas/matplotlib; pytest+pytest-cov; **mypy --strict**;
  **ruff**. h5py optional. (Matches `.claude/settings.local.json` allowlist.)
- CI (`.github/workflows/ci.yml`): ruff → mypy --strict → pytest --cov, all gated.
- Test target: ≥90% coverage; tests mirror modules; synthetic round-trip fit tests (Debye/Cole-Cole
  recovered to ~machine precision with log-scaled τ) plus real-data tests on `h02`.

---

## Verification (end-to-end)

1. `python -m venv .venv` and install deps + `pip install -e .`.
2. **Worked example** (`examples/worked_example.py`) on real data:
   - Load measurement set `data/h02s19m*.csv` (15 repeats) → Type A mean + SEM; sign-convention
     warning fires on positive loss.
   - Load validation set `data/h02v*.csv` as a known reference (saline/water) → QC verdict;
     campaign marked validated / not validated accordingly.
   - Pre-fit quality pass (noise, outliers, sampling adequacy).
   - **Auto model-selection** → expect Cole-Cole + DC conductivity to win (ΔAICc large); print the
     ranking table; demonstrate an **override** (force model + n_poles).
   - Verify: literature comparison vs tissue/liquid DB + KK residuals (band-limited warning).
   - Uncertainty: Type A + Monte-Carlo + a GUM budget *with the input-uncertainty injection*.
   - Export: GUM-rounded LaTeX + CSV table, captioned provenance-stamped figure, methods paragraph,
     BibTeX, reproducibility manifest.
3. `dielectric analyze data/h02s19m*.csv --validate data/h02v*.csv --reference saline` (CLI) produces
   the same artifacts.
4. Gates: `ruff check`, `mypy --strict dielectric`, `pytest --cov` (≥90%).

---

## Out of scope this pass (explicit)
- Web UI (FastAPI + React/Streamlit), PostgreSQL, Docker — deferred to the next pass.
- Raw VNA S11 calibration/inversion — out of project scope entirely (input is already-inverted ε*).
- Live network fetch of reference databases — embedded snapshot + documented updater hook instead.
```
