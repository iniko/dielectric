# dielectric

A publication-ready **dielectric spectroscopy** analysis toolkit for an already-inverted complex
permittivity spectrum ε\*(f) (e.g. a Keysight/Agilent 85070 probe-software export). Built so an
incoming PhD student can go from raw repeats to a paper-ready figure **without a supervisor
re-checking every number** — correct for experts, hard to misuse for novices.

```
ε*(f)  →  quality-check  →  (auto) fit  →  verify (literature + Kramers-Kronig + reference QC)
       →  uncertainty (Type A + Monte-Carlo + GUM)  →  publication-ready export
```

> **Scope.** The input *is* the inverted ε\*(f); raw VNA S11 calibration/inversion is out of scope —
> but the uncertainty budget lets you inject an explicit "trust the probe software ±X%" term so it is
> never silently optimistic.

---

## The 60-second tour (real data)

The repo bundles a real `h02` campaign: 15 repeats of a tissue-like sample (`data/h02s19m*.csv`) and
25 repeats of a saline validation standard (`data/h02v*.csv`). Run the narrated worked example:

```bash
python examples/worked_example.py
```

or the CLI:

```bash
dielectric analyze \
  --measure "data/h02s19m*.csv" \
  --validate "data/h02v*.csv" --reference saline --molarity 0.154 \
  --temperature 25 --out out/
```

On this data the toolkit automatically:

- averages the 15 repeats (Type A) and **drops one bad repeat** with a robust k·MAD screen;
- detects the **positive-loss** export and negates it to the internal `e^{jωt}` convention **with a
  warning** (never silently);
- **auto-selects Cole-Cole + DC σ** over 8 candidates (σ = 0.79 S/m, τ = 8 ps) — refusing to
  recommend lower-AICc fits whose parameters are unidentifiable;
- confirms **Kramers-Kronig** causal consistency (3.2% residual);
- finds the closest literature tissues (kidney, muscle);
- **validates the probe chain** against the saline standard (PASS: ε′ 1.5%, σ 1.64 vs 1.53 S/m);
- and writes a methods paragraph, LaTeX/CSV tables, captioned figures, BibTeX, a reproducibility
  manifest, and **Word + PDF** reports.

The generated methods paragraph is paste-ready:

> *ε\*(f) was fitted to a multi-pole Cole-Cole model with a DC-conductivity term (Cole et al.
> (1941)) by non-linear least squares … yielding τ₁ = (7.73 ± 0.20)e-12 …; σ_DC = 0.7925 ± 0.0025
> (R² = 0.9989). Kramers-Kronig analysis found the spectrum causally consistent (3.2%). The
> measurement chain was validated against a known saline reference …*

---

## Web app (FastAPI + React)

A thin UI over the library — two workflows: **Dielectric Analysis** (upload any number of
measurement and validation sets → fit → verify → report) and an **Uncertainty Budget** sandbox
(live GUM calculation, no upload). The web layer contains no science; it calls the same validated
library.

```bash
pip install -e ".[web,report]"
uvicorn backend.app.main:app --port 8001          # backend (8000 is taken on some machines)
cd frontend && npm install && npm run dev          # frontend on http://localhost:5173 (proxies /api)
```

Then open http://localhost:5173, drop the bundled `data/h02s19m*.csv` into *Measurement sets* and
`data/h02v*.csv` into *Validation sets* (reference: saline), and click **Run analysis**. An E2E
smoke test lives at `frontend/e2e/test_ui.py` (Playwright).

## Desktop app (offline — no Python or Node required)

The same UI ships as a self-contained desktop app for **macOS** and **Windows**. It bundles the
React frontend, the FastAPI backend, and the `dielectric` library (with its reference data) into one
installer — nothing else to install, and it runs **fully offline**. The app starts its own local
backend on launch and shuts it down on quit.

**Download:** grab the latest installer from the
[**Releases page**](https://github.com/iniko/dielectric/releases/latest):

- macOS — Apple Silicon (M-series): `Dielectric Spectroscopy-<version>-arm64.dmg`
- macOS — Intel: `Dielectric Spectroscopy-<version>-x64.dmg`
- Windows (x64): `Dielectric Spectroscopy Setup <version>.exe`

> Not sure which Mac you have? Apple menu → **About This Mac**: "Chip: Apple M…" → arm64;
> "Processor: Intel…" → x64.

### Install on macOS

1. Open the `.dmg` and drag **Dielectric Spectroscopy** into your **Applications** folder.
2. The app is **not yet code-signed**, so the first launch needs a one-time bypass: right-click (or
   Control-click) the app → **Open** → **Open** in the dialog. After that it opens normally.
   - If macOS says the app "is damaged or can't be opened" (Gatekeeper quarantine on a downloaded
     file), clear the flag once in Terminal:
     ```bash
     xattr -dr com.apple.quarantine "/Applications/Dielectric Spectroscopy.app"
     ```
3. Launch it — the window appears once the bundled backend is ready (a few seconds on first run
   while it warms up).


### Install on Windows

1. Run `Dielectric Spectroscopy Setup <version>.exe`.
2. The app is **not yet code-signed**, so SmartScreen may warn "Windows protected your PC": click
   **More info** → **Run anyway**.
3. The installer lets you choose the install location; finish the wizard and launch from the Start
   menu or desktop shortcut.

### Using it

It's the same two workflows as the web app. Drag the bundled `data/h02s19m*.csv` into *Measurement
sets* and `data/h02v*.csv` into *Validation sets* (reference: saline), then step through Load → fit →
verify → report. Reports (PDF/DOCX/HTML) export through a native save dialog.

> Developers building the installers themselves (and the release CI) — see `desktop/README.md`.

## Library quickstart

```python
import dielectric as d

sample = d.MeasurementSet.from_glob("data/h02s19m*.csv", temperature_c=25.0)
spectrum = sample.type_a().mean                 # complex mean + per-point SEM (the fit weight)

selection = d.select_model(spectrum)            # auto-select; or force_model=..., n_poles=...
fit = selection.chosen.result
print(fit.summary())                            # params ± uncertainty, R², AICc

kk = d.kramers_kronig_check(spectrum, model=fit.model)
blood = d.get_material("blood")                 # Gabriel/IT'IS tissue (VERIFY-confidence)
saline = d.get_material("saline", molarity=0.05)  # any molarity
```

---

## What's inside

- **Models** (`DielectricModel` interface): Debye, Cole-Cole, Cole-Davidson, Havriliak-Negami,
  Jonscher, a configurable **multi-pole** model (the "number of poles" knob), mixing rules
  (Maxwell-Garnett, Bruggeman, Looyenga), and a composable DC-conductivity term.
- **Fitting**: generic NLLS on stacked real/imag residuals, log-τ optimisation, SEM weighting,
  multistart; `FitResult` with AIC/AICc/BIC; **auto model-selection** with parsimony +
  identifiability guardrails and a model/pole **override**.
- **Reference database** (biological-tissue emphasis): Gabriel/IT'IS tissues + water/saline/
  seawater/alcohols, each a pre-configured model with provenance and a **HIGH/VERIFY** confidence
  flag (unconfirmed values are never cited bare).
- **Verification**: model-tail Kramers-Kronig, literature comparison, **known-reference QC**.
- **Uncertainty**: Type A, seeded Monte-Carlo, **GUM/JCGM-100 budget** with input-uncertainty
  injection.
- **Reporting**: GUM significant-figure formatting, LaTeX/CSV tables, captioned provenance-stamped
  figures, **methods-paragraph generator**, BibTeX, reproducibility manifest, **docx + pdf** reports.
- **I/O**: Agilent 85070 + parameterized generic CSV, Touchstone, optional HDF5; the multi-set
  `MeasurementSet` / `ValidationSet` / `Campaign` model.
- **MATLAB/Octave** reference port of the core evaluator + fitter (`matlab/`).

## Sign convention (replicated exactly)

Engineering `e^{jωt}`: ε\* = ε′ + j·Im(ε\*) with **Im(ε\*) < 0 for lossy media**. So σ_eff =
−ω·ε₀·Im(ε\*); Kramers-Kronig carries a flipped sign; Cole-Cole plots show −Im(ε\*). Positive-loss
vendor exports are negated **with a warning** on load — the toolkit never silently "fixes" a sign.

## Reference-data honesty

This build was assembled offline, so the embedded tissue parameters are flagged `VERIFY` (usable for
guidance/comparison, confirm against the authoritative IFAC Appendix C / IT'IS CC-BY database before
citing). `dielectric/reference/_updater.py` documents the network-gated refresh that promotes them to
`HIGH`.

## Install & develop

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,report,hdf5]"
pytest                 # ~80 tests
mypy dielectric        # strict
ruff check .
```

Optional extras: `report` (docx/pdf), `hdf5`. The core needs only numpy/scipy/pandas/matplotlib.
