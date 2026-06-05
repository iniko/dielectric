"""Compare two measured batches (spectrum-vs-spectrum and fit-vs-fit).

Where :mod:`dielectric.verification.literature` compares one spectrum to a *reference material*,
this module compares two **measured** batches — the "is normal tissue different from diseased?"
question. Two complementary, model-independent-where-possible views:

* :func:`compare_spectra` — per-frequency Δε′ and Δσ of the two Type A means, each with the standard
  error of the difference (√(seA²+seB²)) and a 95%-CI significance mask. Model-free. Mismatched
  frequency grids are reduced to the band overlap and the second batch is interpolated (in log-f)
  onto it — a deliberate, *surfaced* resampling (unlike ``combine_repeats``, which forbids it).
* :func:`compare_parameters` — robust derived scalars (static permittivity ε_s, ε∞, the dominant
  relaxation time, and σ_DC when both carry it) with a z-score ``|Δ|/√(uA²+uB²)`` so two batches fit
  with *different* model families remain comparable.

Both are **descriptive**: a per-frequency mask flags many points, so treat the significance as a
guide, not a multiple-comparison-corrected test.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

from .constants import EPSILON_0
from .fitting.result import FitResult
from .models.base import DielectricModel
from .spectrum import Spectrum
from .units import BoolArray, ComplexArray, FloatArray, angular_frequency

_DELTA_EPS = re.compile(r"^delta_eps(_\d+)?$")


def _is_delta_eps(name: str) -> bool:
    return bool(_DELTA_EPS.match(name))


def static_permittivity(model: DielectricModel) -> float:
    """Static (low-frequency) permittivity ε_s = ε∞ + Σ Δε over all relaxation poles."""
    p = model.params
    return float(p["eps_inf"] + sum(v for n, v in p.items() if _is_delta_eps(n)))


def static_permittivity_uncertainty(fit: FitResult) -> float:
    """1σ uncertainty of ε_s, summing the covariance block over {ε∞, Δε…} (keeps correlations)."""
    names = list(fit.model.param_names)
    idx = [i for i, n in enumerate(names) if n == "eps_inf" or _is_delta_eps(n)]
    cov = np.asarray(fit.covariance, dtype=np.float64)
    var = float(np.sum(cov[np.ix_(idx, idx)]))
    return float(np.sqrt(max(var, 0.0)))


def dominant_relaxation(fit: FitResult) -> tuple[float, float]:
    """The relaxation time τ of the strongest pole (largest Δε), with its 1σ uncertainty."""
    p = fit.model.params
    pairs: list[tuple[float, str]] = []
    for n, v in p.items():
        if n == "delta_eps":
            pairs.append((v, "tau"))
        elif n.startswith("delta_eps_"):
            pairs.append((v, f"tau_{n[len('delta_eps_'):]}"))
    if not pairs:
        return (float("nan"), float("nan"))
    _, tau_name = max(pairs, key=lambda t: t[0])
    return (float(p[tau_name]), float(fit.param_uncertainties.get(tau_name, float("nan"))))


@dataclass(frozen=True)
class SpectrumDifference:
    """Per-frequency difference of two Type A mean spectra (batch A − batch B)."""

    frequency_hz: FloatArray
    delta_eps_real: FloatArray
    se_eps_real: FloatArray
    significant_eps: BoolArray  # |Δε′| > k·se
    delta_sigma: FloatArray  # σ_eff difference [S/m]
    se_sigma: FloatArray
    significant_sigma: BoolArray
    coverage_k: float
    notes: tuple[str, ...]


def _interp_on(
    f_target: FloatArray, f_src: FloatArray, eps: ComplexArray, sem: ComplexArray
) -> tuple[ComplexArray, ComplexArray]:
    """Interpolate a complex spectrum and its (complex) SEM onto ``f_target`` in log-frequency."""
    lt, ls = np.log10(f_target), np.log10(f_src)
    eps_i = np.interp(lt, ls, np.real(eps)) + 1j * np.interp(lt, ls, np.imag(eps))
    sem_i = np.interp(lt, ls, np.real(sem)) + 1j * np.interp(lt, ls, np.imag(sem))
    return eps_i.astype(np.complex128), sem_i.astype(np.complex128)


def compare_spectra(a: Spectrum, b: Spectrum, *, coverage_k: float = 1.96) -> SpectrumDifference:
    """Per-frequency Δε′ and Δσ of two Type A means, with the SE of the difference + 95% masks."""
    if a.sem is None or b.sem is None:
        raise ValueError("compare_spectra needs Type A mean spectra carrying SEM (combine repeats)")
    fa, fb = a.frequency_hz, b.frequency_hz
    notes: list[str] = []

    same_grid = fa.shape == fb.shape and bool(np.allclose(fa, fb, rtol=1e-6))
    if same_grid:
        f = fa
        eps_a, sem_a, eps_b, sem_b = a.epsilon, a.sem, b.epsilon, b.sem
    else:
        lo, hi = max(fa[0], fb[0]), min(fa[-1], fb[-1])
        if hi <= lo:
            raise ValueError("the two batches have no overlapping frequency band to compare")
        mask: BoolArray = (fa >= lo) & (fa <= hi)
        f = fa[mask]
        eps_a, sem_a = a.epsilon[mask], a.sem[mask]
        eps_b, sem_b = _interp_on(f, fb, b.epsilon, b.sem)
        notes.append(
            f"batches are on different grids; batch B was interpolated (log-f) onto the "
            f"{f.size}-point overlap {lo:.3g}-{hi:.3g} Hz."
        )

    d_eps = np.real(eps_a) - np.real(eps_b)
    se_eps = np.sqrt(np.real(sem_a) ** 2 + np.real(sem_b) ** 2)
    sig_eps: BoolArray = np.abs(d_eps) > coverage_k * se_eps

    # σ_eff = -ω·ε₀·Im(ε*); SEM(Im) is the imaginary part of `sem`.
    omega_eps0 = angular_frequency(f) * EPSILON_0
    d_sigma = -omega_eps0 * (np.imag(eps_a) - np.imag(eps_b))
    se_sigma = omega_eps0 * np.sqrt(np.imag(sem_a) ** 2 + np.imag(sem_b) ** 2)
    sig_sigma: BoolArray = np.abs(d_sigma) > coverage_k * se_sigma

    return SpectrumDifference(
        frequency_hz=f,
        delta_eps_real=d_eps,
        se_eps_real=se_eps,
        significant_eps=sig_eps,
        delta_sigma=d_sigma,
        se_sigma=se_sigma,
        significant_sigma=sig_sigma,
        coverage_k=coverage_k,
        notes=tuple(notes),
    )


@dataclass(frozen=True)
class ParameterDifference:
    """Difference of one derived scalar between two fitted batches (A − B)."""

    name: str
    a: float
    ua: float
    b: float
    ub: float
    delta: float
    z: float  # |Δ| / √(uA²+uB²)
    significant: bool


def _diff(
    name: str, a: float, ua: float, b: float, ub: float, z_threshold: float
) -> ParameterDifference:
    delta = a - b
    denom = float(np.hypot(ua, ub))
    z = abs(delta) / denom if denom > 0 else float("nan")
    return ParameterDifference(name, a, ua, b, ub, delta, z, bool(z >= z_threshold))


def compare_parameters(
    fit_a: FitResult, fit_b: FitResult, *, z_threshold: float = 1.96
) -> list[ParameterDifference]:
    """Compare robust derived scalars (ε_s, ε∞, dominant τ, σ_DC) with a z-score per scalar."""
    pa, pb = fit_a.params, fit_b.params
    ua, ub = fit_a.param_uncertainties, fit_b.param_uncertainties
    out: list[ParameterDifference] = [
        _diff(
            "eps_static",
            static_permittivity(fit_a.model), static_permittivity_uncertainty(fit_a),
            static_permittivity(fit_b.model), static_permittivity_uncertainty(fit_b),
            z_threshold,
        ),
        _diff(
            "eps_inf",
            pa["eps_inf"], ua.get("eps_inf", float("nan")),
            pb["eps_inf"], ub.get("eps_inf", float("nan")),
            z_threshold,
        ),
    ]
    ta, uta = dominant_relaxation(fit_a)
    tb, utb = dominant_relaxation(fit_b)
    out.append(_diff("tau_dominant", ta, uta, tb, utb, z_threshold))
    if "sigma_dc" in pa and "sigma_dc" in pb:
        out.append(
            _diff(
                "sigma_dc",
                pa["sigma_dc"], ua.get("sigma_dc", float("nan")),
                pb["sigma_dc"], ub.get("sigma_dc", float("nan")),
                z_threshold,
            )
        )
    return out
