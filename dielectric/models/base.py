"""The ``DielectricModel`` interface — the toolkit's single extension point.

Everything downstream (fitting, mixing, reference materials, verification, uncertainty, reporting)
is written against this ABC, never against concrete model classes. A reference material is just a
pre-configured model instance, so library materials compose with fitting/comparison/uncertainty
exactly like a user-fitted model.

Sign convention: :meth:`epsilon` returns ε* in the internal ``e^{jωt}`` convention, i.e. with
**Im(ε*) < 0 for lossy media**.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

import numpy as np

from ..constants import EPSILON_0
from ..units import ComplexArray, FloatArray, angular_frequency
from .provenance import Provenance


class DielectricModel(ABC):
    """Immutable value object mapping frequency → complex relative permittivity.

    Concrete subclasses are frozen dataclasses holding their parameters. They must implement
    :meth:`epsilon` and expose :attr:`param_names` / :attr:`params` so the generic fitting engine
    can operate on any model without knowing its identity.
    """

    #: Ordered names of the free parameters (used by the generic fitter).
    param_names: ClassVar[tuple[str, ...]] = ()

    #: Source for the model equation; subclasses set this (as a dataclass field).
    provenance: Provenance

    @abstractmethod
    def epsilon(self, frequency_hz: FloatArray) -> ComplexArray:
        """Complex relative permittivity ε*(f), internal convention (Im < 0 for loss)."""

    # -- generic parameter access, used by fitting/uncertainty ----------------------------------

    @property
    def params(self) -> dict[str, float]:
        """Ordered mapping of free-parameter name → value."""
        return {name: float(getattr(self, name)) for name in self.param_names}

    @property
    def n_params(self) -> int:
        return len(self.param_names)

    def with_params(self, values: dict[str, float]) -> DielectricModel:
        """Return a copy with the named parameters replaced (others unchanged)."""
        import dataclasses

        return dataclasses.replace(self, **values)  # type: ignore[type-var]

    # -- derived quantities shared by every model -----------------------------------------------

    def epsilon_real(self, frequency_hz: FloatArray) -> FloatArray:
        """ε'(f)."""
        return np.real(self.epsilon(frequency_hz))

    def epsilon_imag(self, frequency_hz: FloatArray) -> FloatArray:
        """Im(ε*)(f), internal convention (≤ 0 for a lossy medium)."""
        return np.imag(self.epsilon(frequency_hz))

    def loss(self, frequency_hz: FloatArray) -> FloatArray:
        """ε''(f) = -Im(ε*) — the conventional positive loss shown in figures/tables."""
        return -np.imag(self.epsilon(frequency_hz))

    def loss_tangent(self, frequency_hz: FloatArray) -> FloatArray:
        """tan δ = ε'' / ε'."""
        eps = self.epsilon(frequency_hz)
        return -np.imag(eps) / np.real(eps)

    def effective_conductivity(self, frequency_hz: FloatArray) -> FloatArray:
        """σ_eff(f) = -ω·ε₀·Im(ε*) [S/m] (positive for a passive lossy medium)."""
        omega = angular_frequency(frequency_hz)
        return -omega * EPSILON_0 * np.imag(self.epsilon(frequency_hz))

    def __add__(self, other: DielectricModel) -> SumModel:
        """Compose models by adding their susceptibility contributions (e.g. relaxation + DC σ).

        Only one summand should carry ε∞ (others should contribute 0 at the high-frequency limit),
        otherwise ε∞ is double-counted.
        """
        return SumModel((self, other))


class SumModel(DielectricModel):
    """A sum of model contributions, evaluated as Σ εᵢ(f).

    Used for composition (e.g. ``cole_cole + DCConductivity``); not directly fittable — fit the
    flat-parameter concrete models (e.g. :class:`MultiPoleRelaxation` with ``sigma_dc``) instead.
    """

    param_names: ClassVar[tuple[str, ...]] = ()

    def __init__(self, terms: tuple[DielectricModel, ...]):
        self.terms = terms
        sources = "; ".join(t.provenance.citation() for t in terms)
        self.provenance = Provenance(
            authors="composite",
            year=0,
            title="Sum of dielectric contributions",
            source=sources,
        )

    def epsilon(self, frequency_hz: FloatArray) -> ComplexArray:
        total = np.zeros_like(np.asarray(frequency_hz, dtype=np.complex128))
        for term in self.terms:
            total = total + term.epsilon(frequency_hz)
        return total
