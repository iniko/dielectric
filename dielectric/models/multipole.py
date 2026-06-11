"""Configurable multi-pole relaxation: a sum of N Cole-Cole terms (+ optional DC conductivity).

``N`` = the **number of poles** — the knob the auto-selector sweeps and the user overrides. With
``N=1, alpha=0`` it is Debye; ``N=1`` is Cole-Cole; ``N=2 (+ sigma_dc)`` is the expected winner for
the saline/tissue ``h02`` data (water relaxation + a β-dispersion + ionic conduction).

This model exposes a **flat** parameter vector (``eps_inf, delta_eps_1, tau_1, alpha_1, ...,
[sigma_dc]``) so the generic NLLS engine can fit it without knowing its internal term structure.
With ``fixed_alpha=True`` it becomes the **Debye ladder**: the α of every pole is pinned (held at
its construction value, normally 0) and dropped from the fitted vector, so each pole is an ideal
unbroadened relaxation. This is how "Debye (N poles) + DC σ" is realised.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from ..constants import EPSILON_0
from ..units import ComplexArray, FloatArray, angular_frequency
from .base import DielectricModel
from .provenance import Provenance

_MULTIPOLE = Provenance(
    authors="Cole, K. S., Cole, R. H.",
    year=1941,
    title="Sum of N Cole-Cole dispersions with an optional DC-conductivity term",
    source="generalised multi-term form after Cole & Cole, J. Chem. Phys. 9, 341",
    doi="10.1063/1.1750906",
)

#: Provenance for the Debye-ladder mode (``fixed_alpha=True``): α pinned at 0, so each pole is an
#: ideal Debye relaxation rather than a broadened Cole-Cole one.
DEBYE_SUM = Provenance(
    authors="Debye, P.",
    year=1929,
    title="Sum of N Debye relaxations with an optional DC-conductivity term",
    source="multi-term form after Debye, Polar Molecules (Chemical Catalog Co.)",
)

#: A single Cole-Cole pole: (Δε, τ [s], α).
ColeColeTerm = tuple[float, float, float]


@dataclass(frozen=True)
class MultiPoleRelaxation(DielectricModel):
    r"""Sum of ``len(terms)`` Cole-Cole poles plus an optional DC conductivity.

    :math:`\varepsilon^* = \varepsilon_\infty
    + \sum_n \Delta\varepsilon_n/(1+(j\omega\tau_n)^{1-\alpha_n})
    - j\,\sigma/(\omega\varepsilon_0)`.
    """

    eps_inf: float
    terms: tuple[ColeColeTerm, ...]
    sigma_dc: float | None = None
    # When True this is the **Debye ladder**: every pole's α is pinned (held at its construction
    # value, normally 0) and excluded from the fitted parameter vector — ideal relaxations, no
    # broadening. The shape of ``epsilon`` is unchanged; only which params the fitter sees differs.
    fixed_alpha: bool = False
    provenance: Provenance = field(default=_MULTIPOLE)

    def __post_init__(self) -> None:
        if len(self.terms) < 1:
            raise ValueError("MultiPoleRelaxation needs at least one pole")

    @property
    def n_poles(self) -> int:
        return len(self.terms)

    # -- flat parameter interface (overrides the base) ------------------------------------------

    # param_names is dynamic here (depends on the pole count and whether sigma_dc is present), so
    # it is a property rather than the base class's ClassVar tuple.
    @property
    def param_names(self) -> tuple[str, ...]:  # type: ignore[override]
        names: list[str] = ["eps_inf"]
        for i in range(1, self.n_poles + 1):
            names += [f"delta_eps_{i}", f"tau_{i}"]
            if not self.fixed_alpha:
                names.append(f"alpha_{i}")
        if self.sigma_dc is not None:
            names.append("sigma_dc")
        return tuple(names)

    @property
    def params(self) -> dict[str, float]:
        out: dict[str, float] = {"eps_inf": float(self.eps_inf)}
        for i, (de, tau, alpha) in enumerate(self.terms, start=1):
            out[f"delta_eps_{i}"] = float(de)
            out[f"tau_{i}"] = float(tau)
            if not self.fixed_alpha:
                out[f"alpha_{i}"] = float(alpha)
        if self.sigma_dc is not None:
            out["sigma_dc"] = float(self.sigma_dc)
        return out

    def with_params(self, values: dict[str, float]) -> MultiPoleRelaxation:
        p = self.params | values
        terms = tuple(
            # α is pinned at its current value in Debye mode (not in ``values``); otherwise fitted.
            (p[f"delta_eps_{i}"], p[f"tau_{i}"],
             self.terms[i - 1][2] if self.fixed_alpha else p[f"alpha_{i}"])
            for i in range(1, self.n_poles + 1)
        )
        sigma = p["sigma_dc"] if self.sigma_dc is not None else None
        return replace(self, eps_inf=p["eps_inf"], terms=terms, sigma_dc=sigma)

    # -- evaluation -----------------------------------------------------------------------------

    def epsilon(self, frequency_hz: FloatArray) -> ComplexArray:
        omega = angular_frequency(frequency_hz)
        eps = np.full(omega.shape, self.eps_inf, dtype=np.complex128)
        for de, tau, alpha in self.terms:
            eps = eps + de / (1.0 + (1j * omega * tau) ** (1.0 - alpha))
        if self.sigma_dc is not None:
            eps = eps - 1j * self.sigma_dc / (omega * EPSILON_0)
        return np.asarray(eps, dtype=np.complex128)
