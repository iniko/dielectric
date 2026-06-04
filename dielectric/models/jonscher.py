"""Jonscher universal dielectric response (power-law / constant-phase) model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

import numpy as np

from ..units import ComplexArray, FloatArray, angular_frequency
from .base import DielectricModel
from .provenance import Provenance

_JONSCHER = Provenance(
    authors="Jonscher, A. K.",
    year=1977,
    title="The 'universal' dielectric response",
    source="Nature 267, 673",
    doi="10.1038/267673a0",
)


@dataclass(frozen=True)
class JonscherUniversal(DielectricModel):
    r"""Jonscher universal response:
    :math:`\varepsilon^* = \varepsilon_\infty + A\,(j\omega/\omega_{ref})^{\,n-1}`.

    ``n`` ∈ (0, 1) is the power-law exponent (loss ε'' ∝ ω^{n−1}); ``A`` is the strength. The
    reference angular frequency ``omega_ref`` fixes the units of ``A`` and is **not** a fitted
    parameter (default reference 1 GHz).
    """

    eps_inf: float
    A: float
    n: float
    f_ref_hz: float = 1e9
    provenance: Provenance = field(default=_JONSCHER)

    param_names: ClassVar[tuple[str, ...]] = ("eps_inf", "A", "n")

    def epsilon(self, frequency_hz: FloatArray) -> ComplexArray:
        omega = angular_frequency(frequency_hz)
        omega_ref = 2.0 * np.pi * self.f_ref_hz
        eps = self.eps_inf + self.A * (1j * omega / omega_ref) ** (self.n - 1.0)
        return np.asarray(eps, dtype=np.complex128)
