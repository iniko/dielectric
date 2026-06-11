"""Prepackaged per-model fitters + the model-label grammar.

Good starting values matter: NLLS is non-convex, so each fitter derives a deterministic ``p0`` from
the data (σ from the low-frequency loss, ε∞ from the high-frequency plateau, τ from the loss-peak
frequency) before handing off to the generic :func:`dielectric.fitting.engine.fit`.

Models are named by a small **compositional grammar** — ``family [(N poles)] [+ DC σ]`` — so a label
always states which family and how many poles (no opaque "MultiPole(N=2)"). The pole-ladder families
are Debye (α pinned to 0) and Cole-Cole (α free); the others are single-pole shapes.
:func:`compose_fitter` turns a ``(family, n_poles, dc_sigma)`` triple into a ``(label, fitter)``
pair, and is the single source of truth for which combinations are valid.
"""

from __future__ import annotations

import re
from collections.abc import Callable

import numpy as np

from ..constants import EPSILON_0
from ..models.cole_cole import ColeCole
from ..models.cole_davidson import ColeDavidson
from ..models.debye import Debye
from ..models.havriliak_negami import HavriliakNegami
from ..models.jonscher import JonscherUniversal
from ..models.multipole import DEBYE_SUM, ColeColeTerm, MultiPoleRelaxation
from ..spectrum import Spectrum
from ..units import angular_frequency
from .engine import fit
from .result import FitResult

#: A single-argument fitter: spectrum -> fitted result.
FitFn = Callable[[Spectrum], FitResult]

#: All candidate families, in display order.
FAMILIES: tuple[str, ...] = (
    "Debye",
    "Cole-Cole",
    "Cole-Davidson",
    "Havriliak-Negami",
    "Jonscher",
)

#: Families that support a pole ladder (N ≥ 1) and a composable DC-conductivity term.
LADDER_FAMILIES: tuple[str, ...] = ("Debye", "Cole-Cole")


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


# -- the label grammar ----------------------------------------------------------------------------

_DC_SUFFIX = " + DC σ"
_POLES_RE = re.compile(r"^(?P<fam>.+?)(?: \((?P<n>\d+) poles?\))?$")


def model_label(family: str, n_poles: int = 1, dc_sigma: bool = False) -> str:
    """Canonical label — ``"Debye"`` or ``"Cole-Cole (2 poles) + DC σ"`` (1 pole implied)."""
    label = family
    if n_poles > 1:
        label += f" ({n_poles} poles)"
    if dc_sigma:
        label += _DC_SUFFIX
    return label


def parse_model_label(label: str) -> tuple[str, int, bool]:
    """Inverse of :func:`model_label` → ``(family, n_poles, dc_sigma)``. Raises on a bad label."""
    if label.startswith("MultiPole"):
        raise ValueError(
            f"'{label}' uses the old naming; say which family of poles, e.g. "
            f"'Cole-Cole (2 poles) + DC σ' or 'Debye (2 poles) + DC σ'"
        )
    rest = label
    dc = rest.endswith(_DC_SUFFIX)
    if dc:
        rest = rest[: -len(_DC_SUFFIX)]
    m = _POLES_RE.match(rest)
    if m is None:  # pragma: no cover - the regex matches any string
        raise ValueError(f"could not parse model label {label!r}")
    family = m.group("fam")
    n_poles = int(m.group("n")) if m.group("n") else 1
    if family not in FAMILIES:
        raise ValueError(
            f"unknown model family {family!r} in {label!r}; available: {', '.join(FAMILIES)}"
        )
    return family, n_poles, dc


def compose_fitter(family: str, n_poles: int = 1, dc_sigma: bool = False) -> tuple[str, FitFn]:
    """Build the ``(label, fitter)`` for a model from its family / pole count / DC-σ term.

    The single source of truth for which combos are valid: pole counts > 1 and a DC-σ term are
    only available for the ladder families (Debye, Cole-Cole). Raises ``ValueError`` otherwise.
    """
    if family not in FAMILIES:
        raise ValueError(f"unknown model family {family!r}; available: {', '.join(FAMILIES)}")
    if n_poles < 1:
        raise ValueError(f"n_poles must be >= 1, got {n_poles}")
    if n_poles > 1 and family not in LADDER_FAMILIES:
        raise ValueError(
            f"more than one pole is only available for {', '.join(LADDER_FAMILIES)} "
            f"(got {n_poles} poles for {family!r})"
        )
    if dc_sigma and family not in LADDER_FAMILIES:
        raise ValueError(
            f"a DC-σ term composes only with {', '.join(LADDER_FAMILIES)} in this version "
            f"(requested for {family!r})"
        )

    label = model_label(family, n_poles, dc_sigma)

    if family in LADDER_FAMILIES and (n_poles > 1 or dc_sigma):
        is_debye = family == "Debye"

        def _ladder(s: Spectrum) -> FitResult:
            eps_inf, terms, sigma0 = _guess(s, n_poles, with_conductivity=dc_sigma)
            sigma = sigma0 if dc_sigma else None
            if is_debye:
                template = MultiPoleRelaxation(
                    eps_inf, tuple((de, tau, 0.0) for de, tau, _ in terms),
                    sigma_dc=sigma, fixed_alpha=True, provenance=DEBYE_SUM,
                )
            else:
                template = MultiPoleRelaxation(eps_inf, tuple(terms), sigma_dc=sigma)
            return fit(s, template)

        return label, _ladder

    # single-pole classic families
    classic: dict[str, FitFn] = {
        "Debye": fit_debye,
        "Cole-Cole": fit_cole_cole,
        "Cole-Davidson": fit_cole_davidson,
        "Havriliak-Negami": fit_havriliak_negami,
        "Jonscher": fit_jonscher,
    }
    return label, classic[family]


# -- single-pole fitters (used directly and by compose_fitter) ------------------------------------


def fit_debye(spectrum: Spectrum, *, n_poles: int = 1, dc_sigma: bool = False) -> FitResult:
    if n_poles > 1 or dc_sigma:
        _, fn = compose_fitter("Debye", n_poles, dc_sigma)
        return fn(spectrum)
    eps_inf, terms, _ = _guess(spectrum, 1, with_conductivity=False)
    delta, tau, _alpha = terms[0]
    return fit(spectrum, Debye(eps_inf, delta, tau))


def fit_cole_cole(spectrum: Spectrum, *, n_poles: int = 1, dc_sigma: bool = False) -> FitResult:
    if n_poles > 1 or dc_sigma:
        _, fn = compose_fitter("Cole-Cole", n_poles, dc_sigma)
        return fn(spectrum)
    eps_inf, terms, _ = _guess(spectrum, 1, with_conductivity=False)
    delta, tau, alpha = terms[0]
    return fit(spectrum, ColeCole(eps_inf, delta, tau, alpha))


def fit_cole_davidson(spectrum: Spectrum) -> FitResult:
    eps_inf, terms, _ = _guess(spectrum, 1, with_conductivity=False)
    delta, tau, _ = terms[0]
    return fit(spectrum, ColeDavidson(eps_inf, delta, tau, 0.7))


def fit_havriliak_negami(spectrum: Spectrum) -> FitResult:
    eps_inf, terms, _ = _guess(spectrum, 1, with_conductivity=False)
    delta, tau, _ = terms[0]
    return fit(spectrum, HavriliakNegami(eps_inf, delta, tau, 0.1, 0.8))


def fit_jonscher(spectrum: Spectrum) -> FitResult:
    eps_inf = max(float(spectrum.eps_real[-1]), 1.0)
    return fit(spectrum, JonscherUniversal(eps_inf, 1.0, 0.6))


# -- back-compat aliases --------------------------------------------------------------------------


def fit_cole_cole_conductivity(spectrum: Spectrum, **kw: object) -> FitResult:
    """A single Cole-Cole pole plus a DC-conductivity term (= ``Cole-Cole + DC σ``)."""
    eps_inf, terms, sigma0 = _guess(spectrum, 1, with_conductivity=True)
    return fit(spectrum, MultiPoleRelaxation(eps_inf, tuple(terms), sigma_dc=sigma0))


def fit_multipole(
    spectrum: Spectrum, n_poles: int, *, with_conductivity: bool = True, **kw: object
) -> FitResult:
    """Fit an N-pole Cole-Cole model (kept for callers; prefer :func:`compose_fitter`)."""
    eps_inf, terms, sigma0 = _guess(spectrum, n_poles, with_conductivity)
    sigma = sigma0 if with_conductivity else None
    return fit(spectrum, MultiPoleRelaxation(eps_inf, tuple(terms), sigma_dc=sigma))
