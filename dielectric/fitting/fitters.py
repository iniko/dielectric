"""Prepackaged per-model fitters with data-driven initial guesses.

Good starting values matter: NLLS is non-convex, so each fitter derives a deterministic ``p0`` from
the data (σ from the low-frequency loss, ε∞ from the high-frequency plateau, τ from the loss-peak
frequency) before handing off to the generic :func:`dielectric.fitting.engine.fit`.
"""

from __future__ import annotations

import numpy as np

from ..constants import EPSILON_0
from ..models.cole_cole import ColeCole
from ..models.debye import Debye
from ..models.multipole import ColeColeTerm, MultiPoleRelaxation
from ..spectrum import Spectrum
from ..units import angular_frequency
from .engine import fit
from .result import FitResult


def _guess(
    spectrum: Spectrum, n_poles: int, with_conductivity: bool
) -> tuple[float, list[ColeColeTerm], float | None]:
    """Deterministic initial parameters for an ``n_poles`` Cole-Cole (+σ) model."""
    f = spectrum.frequency_hz
    omega = angular_frequency(f)
    eps = spectrum.epsilon
    loss = spectrum.loss  # positive ε''

    eps_inf = max(float(np.real(eps[-1])), 1.0)
    eps_s = float(np.real(eps[0]))

    sigma0: float | None = None
    relax_loss = loss.copy()
    if with_conductivity:
        # σ ≈ ω ε₀ ε'' at the lowest frequency, where conduction dominates the loss.
        sigma0 = max(float(loss[0] * omega[0] * EPSILON_0), 0.0)
        conduction_loss = sigma0 / (omega * EPSILON_0)
        relax_loss = np.clip(loss - conduction_loss, 0.0, None)

    total_delta = max(eps_s - eps_inf, 1.0)
    ipeak = int(np.argmax(relax_loss))
    f_peak = f[ipeak] if relax_loss[ipeak] > 0 else f[-1]
    tau0 = 1.0 / (2.0 * np.pi * f_peak)

    # Spread poles over decades (fast water-like first, slower dispersions after), split strength.
    terms: list[ColeColeTerm] = [
        (total_delta / n_poles, tau0 * (10.0**i), 0.1) for i in range(n_poles)
    ]
    return eps_inf, terms, sigma0


def fit_debye(spectrum: Spectrum, **kw: object) -> FitResult:
    eps_inf, terms, _ = _guess(spectrum, 1, with_conductivity=False)
    delta, tau, _alpha = terms[0]
    template = Debye(eps_inf, delta, tau)
    return fit(spectrum, template, **kw)  # type: ignore[arg-type]


def fit_cole_cole(spectrum: Spectrum, **kw: object) -> FitResult:
    eps_inf, terms, _ = _guess(spectrum, 1, with_conductivity=False)
    delta, tau, alpha = terms[0]
    template = ColeCole(eps_inf, delta, tau, alpha)
    return fit(spectrum, template, **kw)  # type: ignore[arg-type]


def fit_cole_cole_conductivity(spectrum: Spectrum, **kw: object) -> FitResult:
    eps_inf, terms, sigma0 = _guess(spectrum, 1, with_conductivity=True)
    template = MultiPoleRelaxation(eps_inf, tuple(terms), sigma_dc=sigma0)
    return fit(spectrum, template, **kw)  # type: ignore[arg-type]


def fit_multipole(
    spectrum: Spectrum,
    n_poles: int,
    *,
    with_conductivity: bool = True,
    **kw: object,
) -> FitResult:
    """Fit an N-pole Cole-Cole model (the user's 'number of poles' override)."""
    eps_inf, terms, sigma0 = _guess(spectrum, n_poles, with_conductivity)
    template = MultiPoleRelaxation(eps_inf, tuple(terms), sigma_dc=sigma0)
    return fit(spectrum, template, **kw)  # type: ignore[arg-type]
