"""Cole-Davidson asymmetric-broadening relaxation model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

import numpy as np

from ..units import ComplexArray, FloatArray, angular_frequency
from .base import DielectricModel
from .provenance import Provenance

_COLE_DAVIDSON = Provenance(
    authors="Davidson, D. W., Cole, R. H.",
    year=1951,
    title="Dielectric Relaxation in Glycerol, Propylene Glycol, and n-Propanol",
    source="Journal of Chemical Physics 19, 1484",
    doi="10.1063/1.1748105",
)


@dataclass(frozen=True)
class ColeDavidson(DielectricModel):
    r"""Cole-Davidson asymmetric-broadening relaxation.

    :math:`\varepsilon^* = \varepsilon_\infty + \Delta\varepsilon/(1 + j\omega\tau)^\beta`.
    ``beta`` ∈ (0, 1] is the asymmetric broadening; β=1 recovers Debye.
    """

    eps_inf: float
    delta_eps: float
    tau: float
    beta: float
    provenance: Provenance = field(default=_COLE_DAVIDSON)

    param_names: ClassVar[tuple[str, ...]] = ("eps_inf", "delta_eps", "tau", "beta")

    def epsilon(self, frequency_hz: FloatArray) -> ComplexArray:
        omega = angular_frequency(frequency_hz)
        eps = self.eps_inf + self.delta_eps / (1.0 + 1j * omega * self.tau) ** self.beta
        return np.asarray(eps, dtype=np.complex128)
