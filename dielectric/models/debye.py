"""Debye single-relaxation model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

import numpy as np

from ..units import ComplexArray, FloatArray, angular_frequency
from .base import DielectricModel
from .provenance import Provenance

_DEBYE = Provenance(
    authors="Debye, P.",
    year=1929,
    title="Polar Molecules",
    source="Chemical Catalog Company, New York",
)


@dataclass(frozen=True)
class Debye(DielectricModel):
    r"""Debye single relaxation.

    :math:`\varepsilon^* = \varepsilon_\infty + \Delta\varepsilon/(1 + j\omega\tau)`.

    Parameters
    ----------
    eps_inf:
        High-frequency permittivity ε∞.
    delta_eps:
        Relaxation strength Δε = ε_s − ε∞.
    tau:
        Relaxation time τ [s] (fit in log10 space; see :mod:`dielectric.fitting`).
    """

    eps_inf: float
    delta_eps: float
    tau: float
    provenance: Provenance = field(default=_DEBYE)

    param_names: ClassVar[tuple[str, ...]] = ("eps_inf", "delta_eps", "tau")

    def epsilon(self, frequency_hz: FloatArray) -> ComplexArray:
        omega = angular_frequency(frequency_hz)
        eps = self.eps_inf + self.delta_eps / (1.0 + 1j * omega * self.tau)
        return np.asarray(eps, dtype=np.complex128)
