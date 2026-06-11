# Model fitting, the cost function, and goodness of fit

> Reference document for the fitting layer (`dielectric/fitting/`). Describes the candidate models,
> the exact objective minimised, and how to read R², reduced χ², and the residual diagnostics —
> including **why R² ≈ 0.9999 does not mean a good fit** for dielectric spectra. Last reviewed
> 2026-06-11.

## 1 — The candidate models

A model is a complex permittivity ε\*(ω) written in the internal **engineering `e^{jωt}`
convention** (so `Im(ε*) < 0` for lossy media and a DC-conductivity term enters as
`− jσ_dc/(ωε₀)`). ω = 2πf, ε₀ is the vacuum permittivity.

Models are named by a compositional grammar — `family [(N poles)] [+ DC σ]` (one pole implied when
no parenthetical). The grammar and the factory that turns a `(family, n_poles, dc_sigma)` triple
into a fitter live in `dielectric/fitting/fitters.py`
(`model_label` / `parse_model_label` / `compose_fitter`); the equations and plain-language
descriptions are derived from the same grammar in `dielectric/fitting/catalog.py`.

### Single-pole "classics" (no DC term)

| label | ε\*(ω) | free parameters | k |
|---|---|---|---|
| `Debye` | ε∞ + Δε/(1 + jωτ) | ε∞, Δε, τ | 3 |
| `Cole-Cole` | ε∞ + Δε/(1 + (jωτ)^(1−α)) | ε∞, Δε, τ, α | 4 |
| `Cole-Davidson` | ε∞ + Δε/(1 + jωτ)^β | ε∞, Δε, τ, β | 4 |
| `Havriliak-Negami` | ε∞ + Δε/(1 + (jωτ)^(1−α))^β | ε∞, Δε, τ, α, β | 5 |
| `Jonscher` | ε∞ + A·(jω/ω_ref)^(n−1) | ε∞, A, n (ω_ref = 2π·1 GHz, fixed) | 3 |

α is the symmetric (Cole-Cole) broadening; β the asymmetric (Cole-Davidson) broadening;
Havriliak-Negami carries both.

### Pole ladders with a DC-conductivity term

A sum of N relaxation poles plus ionic conduction:

  ε\*(ω) = ε∞ + Σₙ [pole]ₙ − jσ_dc/(ωε₀)

| family | per-pole term | params/pole | label examples |
|---|---|---|---|
| **Debye** (α ≡ 0) | Δεₙ/(1 + jωτₙ) | 2 (Δε, τ) | `Debye + DC σ`, `Debye (2 poles) + DC σ`, `Debye (3 poles) + DC σ` |
| **Cole-Cole** | Δεₙ/(1 + (jωτₙ)^(1−αₙ)) | 3 (Δε, τ, α) | `Cole-Cole + DC σ`, `Cole-Cole (2 poles) + DC σ`, `Cole-Cole (3 poles) + DC σ` |

Total parameter count is `1 (ε∞) + n_poles × params/pole + 1 (σ_dc)`. So `Debye (3 poles) + DC σ`
has k = 8; `Cole-Cole (3 poles) + DC σ` has k = 11.

The Debye ladder is realised by the same `MultiPoleRelaxation` engine with each pole's α **pinned to
0 and excluded from the fitted vector** (`fixed_alpha=True`) — not bounds-pinned, which would inflate
k and corrupt the information criteria.

### The default auto-selection panel (11 models)

`default_candidates(max_poles=3)` = the 5 single-pole classics **+** the Debye and Cole-Cole ladders
at 1–3 poles, each with a DC-σ term — 11 candidates. `max_poles = 3` is deliberate: over a ~2-decade
band (e.g. 0.2–20 GHz) only ~2–3 relaxation processes are resolvable; beyond that, AICc stops
improving and the extra poles migrate out of band / become unidentifiable.

## 2 — The cost function

Each candidate is fit by non-linear least squares (`dielectric/fitting/engine.py`, `fit()`). The
residual vector handed to the optimiser **stacks the real and imaginary parts** of the complex
residual and **weights each point by its Type A standard error of the mean (SEM)**:

```python
r_i(θ) = [ Re(ε_model − ε_data)/σ'  ,  Im(ε_model − ε_data)/σ'' ]   # length 2·n_freq
```

SciPy's `least_squares` minimises

  C(θ) = ½ Σᵢ rᵢ(θ)²

and the toolkit reports **χ² = 2·C(θ)** — i.e. the objective *is* the weighted sum of squared
residuals:

  χ²(θ) = Σₖ [ (ε′_model − ε′_data)ₖ² / σ′ₖ²  +  (ε″_model − ε″_data)ₖ² / σ″ₖ² ]

Properties that matter:

- **Weighted by measurement uncertainty.** σ′ₖ, σ″ₖ are the per-frequency Type A SEMs (real/imag of
  `Spectrum.sem`), floored at 10 % of each component's median so a few coincidentally-tight points
  cannot dominate. **If no repeats/SEM are available the fit is unweighted** (σ = 1) and χ² becomes a
  plain sum of squared residuals.
- **Both quadratures fit jointly.** ε′ and ε″ are stacked into one residual of length N = 2·n_freq —
  the fit targets the full complex ε\*, never magnitude or phase alone.
- **τ (and any multi-decade parameter) is optimised in log₁₀ space.** Without this scipy's
  finite-difference Jacobian floor destroys the τ column and the fit silently diverges; the
  covariance is mapped back to natural units with the delta method (`dx/dz = ln(10)·x`).
- **Bounded** box constraints per parameter, e.g. α ∈ [0, 0.99], β ∈ [10⁻³, 1], τ ∈ [10⁻¹⁴, 10⁻⁶] s,
  Δε ∈ [0, 10⁷], σ_dc ∈ [0, 10³] S/m (`_DEFAULT_BOUNDS` in `engine.py`). With bounds the solver is
  scipy's Trust Region Reflective.
- **Multistart** (4 jittered restarts by default, lowest-cost kept) guards against local minima.

## 3 — Goodness of fit: read χ², not R²

The engine reports several quantities on `FitResult`. They answer **different questions** and must
not be conflated.

### Reduced χ² — "does it fit within the measurement uncertainty?"

  χ²_red = χ² / dof,    dof = N − k,    N = 2·n_freq

This is the metric to trust. Because χ² is weighted by the Type A SEM, **χ²_red ≈ 1 means the model
describes the data to within its measurement uncertainty**; χ²_red ≫ 1 means the model misfits
relative to that uncertainty. A weighted fit with χ²_red > 5 raises an explicit selection warning,
because the parameter covariance (which assumes model adequacy) is then optimistic by roughly
√χ²_red.

### Standardized residuals (pulls) — the diagnostic plot

  pull = (ε_model − ε_data) / σ      (per component)

Dimensionless, and `Σ(pull²) = χ²` exactly. The fit step plots these by default with ±1 / ±2 bands:
a good weighted fit scatters inside ±2; a point poking far outside is a localised misfit. This is
where a visible gap shows up as a number — e.g. a 6-unit miss in ε′ where σ ≈ 0.67 is a ~9σ pull,
unmissable in the plot even though R² barely moves.

### Mean squared pull per component — the honest split

  msp = mean(pull²)   for ε′ and ε″ separately

`msp_real` / `msp_imag`. ≈ 1 means that component fits within Type A uncertainty; their average is
χ² / N. This is the *honest* per-component goodness, preferred over the per-component R² below.

### R² — "does it capture the overall shape?" (and why it is ~1)

R² is the ordinary coefficient of determination on the **unweighted, stacked** residual vector
(`engine.py`):

  R² = 1 − SS_res / SS_tot
  SS_res = Σ [ (ε′_model − ε′_data)² + (ε″_model − ε″_data)² ]
  SS_tot = Σ (x − x̄)²,   x = [ε′, ε″] stacked,   x̄ = mean of the stacked vector

Two consequences specific to dielectric spectra:

1. **It is unweighted.** R² ignores the Type A σ entirely — that information lives in χ², not R².
2. **It is dominated by the ε′ dynamic range and the conduction tail.** SS_tot is enormous (ε′ runs
   from ε∞ to ε_s; ε″ runs up the 1/f conduction tail), so SS_res/SS_tot is minuscule for *any*
   plausible model and R² pins near 1.

**Worked illustration** (real `h02s19m` data, the 1-pole `Cole-Cole + DC σ` fit that visibly misses
the low-frequency end):

| quantity | value |
|---|---|
| ε′ at 0.2 GHz: data vs model | 58.2 vs 52.1 → **Δ = −6.1** |
| SS_res | 314 |
| SS_tot | 273,425 |
| **R²** | 1 − 314/273,425 = **0.9989** |
| χ²_red | **3.66** (Type A σ(ε′) ≈ 0.67, so the 6-unit miss is ~9σ) |

A genuine 6-unit error in ε′ is invisible to R² (it drowns in a 273,000 sum-of-squares) but obvious
in χ²_red and the pull plot. **R² ≈ 0.999 is normal here and is a poor quality gate — judge the fit
from χ²_red and the standardized residuals.** The UI displays R² with the per-component split and a
caption to this effect; the value can read as `1.0000` purely from 4-decimal rounding of ~0.99995.

`r_squared_real` / `r_squared_imag` (each component baselined against its own mean) are secondary and
**may be negative** when a forced model fits a component worse than a flat line.

## 4 — Model selection

`select_model` (`dielectric/fitting/selection.py`) fits the panel, ranks by **AICc and BIC on the
weighted-χ² basis** with N = 2·n_freq:

  AIC = χ² + 2k    AICc = AIC + 2k(k+1)/(N−k−1)    BIC = χ² + k·ln(N)

then recommends — not the lowest AICc, but **the most parsimonious model that (a) fits comparably
well** (R² within `R2_RECOMMEND_TOL = 0.01` of the best non-over-parameterised fit) **and (b) is
identifiable.** A fit is flagged:

- `overparam` when N ≤ k + 1 (AICc undefined / unreliable);
- `degenerate` when its largest regularised relative parameter uncertainty exceeds
  `DEGENERACY_THRESHOLD = 1.0` — e.g. a slow pole absorbing the DC-conduction tail and collapsing
  σ_dc to ~0 with a huge error bar.

Among comparably-good identifiable candidates the most parsimonious within
`PARSIMONY_DELTA_AICC = 2.0` of the best AICc wins. The result carries a machine-readable
`excluded_reason` per candidate and a one-sentence `rationale` for the recommendation, and warns when
a chosen pole peaks **outside the measured band** (constrained only by the dispersion tail —
extrapolation). The user can override by family, pole count, and/or DC-σ term, which **compose** into
one model; given alone, a pole count ladders Debye/Cole-Cole and a DC-σ choice filters the panel
(a constraint, not an override).

> On the bundled `h02` data this is why auto lands on the identifiable `Debye (3 poles) + DC σ`
> (χ²_red ≈ 0.6) rather than a lower-AICc but `degenerate` Cole-Cole multipole: the free α per pole
> aliases the conduction tail and becomes unidentifiable, while pinning α makes the same pole count
> falsifiable.

## 5 — Where this lives in the code

| concern | file |
|---|---|
| NLLS engine, cost function, R²/χ²/msp, covariance | `dielectric/fitting/engine.py` |
| `FitResult` (AICc/BIC/χ²_red/pulls properties) | `dielectric/fitting/result.py` |
| model classes (ε\* forms) | `dielectric/models/*.py` (`multipole.py` carries the ladders) |
| label grammar + per-model fitters | `dielectric/fitting/fitters.py` |
| equations + plain-language descriptions | `dielectric/fitting/catalog.py` |
| ranking, recommendation, rationale, warnings | `dielectric/fitting/selection.py` |
