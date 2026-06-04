"""DC ionic conductivity term — a composable ``DielectricModel`` contribution.

In the ``e^{jωt}`` convention a static conductivity σ adds a purely imaginary (lossy) term
:math:`-j\\,\\sigma/(\\omega\\varepsilon_0)` to ε* that diverges as ω→0. Add it to a relaxation
model: ``cole_cole + DCConductivity(sigma=0.7)``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

import numpy as np

from ..constants import EPSILON_0
from ..units import ComplexArray, FloatArray, angular_frequency
from .base import DielectricModel
from .provenance import Provenance

_OHMIC = Provenance(
    authors="(standard result)",
    year=0,
    title="Ohmic loss term σ/(jωε₀) in the e^{jωt} convention",
    source="classical electromagnetism",
)


@dataclass(frozen=True)
class DCConductivity(DielectricModel):
    r"""Pure DC conductivity contribution: :math:`\varepsilon^* = -j\,\sigma/(\omega\varepsilon_0)`.

    Carries no ε∞ (contributes 0 real part), so it composes cleanly with a relaxation model.
    """

    sigma: float
    provenance: Provenance = field(default=_OHMIC)

    param_names: ClassVar[tuple[str, ...]] = ("sigma",)

    def epsilon(self, frequency_hz: FloatArray) -> ComplexArray:
        omega = angular_frequency(frequency_hz)
        return np.asarray(-1j * self.sigma / (omega * EPSILON_0), dtype=np.complex128)
