"""Cole-Cole symmetric-broadening relaxation model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

import numpy as np

from ..units import ComplexArray, FloatArray, angular_frequency
from .base import DielectricModel
from .provenance import Provenance

_COLE_COLE = Provenance(
    authors="Cole, K. S., Cole, R. H.",
    year=1941,
    title="Dispersion and Absorption in Dielectrics I. Alternating Current Characteristics",
    source="Journal of Chemical Physics 9, 341",
    doi="10.1063/1.1750906",
)


@dataclass(frozen=True)
class ColeCole(DielectricModel):
    r"""Cole-Cole symmetric-broadening relaxation.

    :math:`\varepsilon^* = \varepsilon_\infty + \Delta\varepsilon/(1 + (j\omega\tau)^{1-\alpha})`.
    ``alpha`` ∈ [0, 1) is the symmetric broadening; α=0 recovers Debye.
    """

    eps_inf: float
    delta_eps: float
    tau: float
    alpha: float
    provenance: Provenance = field(default=_COLE_COLE)

    param_names: ClassVar[tuple[str, ...]] = ("eps_inf", "delta_eps", "tau", "alpha")

    def epsilon(self, frequency_hz: FloatArray) -> ComplexArray:
        omega = angular_frequency(frequency_hz)
        jwt = 1j * omega * self.tau
        eps = self.eps_inf + self.delta_eps / (1.0 + jwt ** (1.0 - self.alpha))
        return np.asarray(eps, dtype=np.complex128)
