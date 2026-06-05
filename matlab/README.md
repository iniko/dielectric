# MATLAB / Octave reference port

A small MATLAB/Octave port of the core `dielectric` evaluator and fitter, for the research group's
existing MATLAB workflows (per `STACK.md`). The Python package remains the validated, tested,
permanent asset; this port mirrors the Cole-Cole + DC-conductivity core so MATLAB users can evaluate
and fit without leaving their environment.

## Files
- `cole_cole.m` — complex permittivity ε*(f) for a Cole-Cole + DC-conductivity model, in the
  engineering `e^{jωt}` convention (Im(ε*) < 0 for loss).
- `fit_cole_cole.m` — NLLS fit with **log10-τ** optimisation (the same multi-decade-parameter
  gotcha the Python engine handles) using `lsqnonlin` if available, else `fminsearch`.
- `run_tests.m` — cross-checks the port against reference values produced by the Python core, and
  runs a noise-free round-trip fit.

## Run (GNU Octave)
```sh
cd matlab
octave run_tests.m
```

## Convention
Pass measured data as `ε' - 1i·ε''` (internal convention, Im < 0). Agilent 85070 exports store
**positive** loss, so negate the loss column on load — exactly as the Python loader does (with a
warning), never silently.
