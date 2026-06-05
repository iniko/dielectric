"""Havriliak-Negami relaxation model (generalises Cole-Cole and Cole-Davidson)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

import numpy as np

from ..units import ComplexArray, FloatArray, angular_frequency
from .base import DielectricModel
from .provenance import Provenance

_HN = Provenance(
    authors="Havriliak, S., Negami, S.",
    year=1967,
    title=(
        "A complex plane representation of dielectric and mechanical relaxation "
        "processes in some polymers"
    ),
    source="Polymer 8, 161",
    doi="10.1016/0032-3861(67)90021-3",
)


@dataclass(frozen=True)
class HavriliakNegami(DielectricModel):
    r"""Havriliak-Negami generalised relaxation.

    :math:`\varepsilon^* = \varepsilon_\infty
    + \Delta\varepsilon/(1 + (j\omega\tau)^{1-\alpha})^\beta`.

    Nesting (used by model selection):

    * ``beta = 1`` → Cole-Cole (broadening 1−α),
    * ``alpha = 0`` → Cole-Davidson (exponent β),
    * ``alpha = 0, beta = 1`` → Debye.
    """

    eps_inf: float
    delta_eps: float
    tau: float
    alpha: float
    beta: float
    provenance: Provenance = field(default=_HN)

    param_names: ClassVar[tuple[str, ...]] = ("eps_inf", "delta_eps", "tau", "alpha", "beta")

    def epsilon(self, frequency_hz: FloatArray) -> ComplexArray:
        omega = angular_frequency(frequency_hz)
        jwt = 1j * omega * self.tau
        eps = self.eps_inf + self.delta_eps / (1.0 + jwt ** (1.0 - self.alpha)) ** self.beta
        return np.asarray(eps, dtype=np.complex128)
