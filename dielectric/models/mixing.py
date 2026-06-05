"""Effective-medium / mixing models for composites.

Each composes two :class:`DielectricModel` instances — a ``host`` matrix and an ``inclusion`` phase
at volume fraction ``volume_fraction`` — and returns the effective ε* of the mixture, so a composite
behaves like any other model for fitting, comparison, and uncertainty.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

import numpy as np

from ..units import ComplexArray, FloatArray
from .base import DielectricModel
from .provenance import Provenance

_MG = Provenance(
    authors="Maxwell Garnett, J. C.",
    year=1904,
    title="Colours in metal glasses and in metallic films",
    source="Philosophical Transactions of the Royal Society A 203, 385",
    doi="10.1098/rsta.1904.0024",
)
_BRUGGEMAN = Provenance(
    authors="Bruggeman, D. A. G.",
    year=1935,
    title="Berechnung verschiedener physikalischer Konstanten von heterogenen Substanzen",
    source="Annalen der Physik 416, 636",
    doi="10.1002/andp.19354160705",
)
_LOOYENGA = Provenance(
    authors="Looyenga, H.",
    year=1965,
    title="Dielectric constants of heterogeneous mixtures",
    source="Physica 31, 401",
    doi="10.1016/0031-8914(65)90045-5",
)


def _check_fraction(f: float) -> None:
    if not 0.0 <= f <= 1.0:
        raise ValueError(f"volume_fraction must be in [0, 1], got {f}")


@dataclass(frozen=True)
class MaxwellGarnett(DielectricModel):
    """Maxwell-Garnett mixing: dilute spherical inclusions in a host matrix."""

    host: DielectricModel
    inclusion: DielectricModel
    volume_fraction: float
    provenance: Provenance = field(default=_MG)

    param_names: ClassVar[tuple[str, ...]] = ("volume_fraction",)

    def __post_init__(self) -> None:
        _check_fraction(self.volume_fraction)

    def epsilon(self, frequency_hz: FloatArray) -> ComplexArray:
        eh = self.host.epsilon(frequency_hz)
        ei = self.inclusion.epsilon(frequency_hz)
        f = self.volume_fraction
        num = ei + 2 * eh + 2 * f * (ei - eh)
        den = ei + 2 * eh - f * (ei - eh)
        return eh * num / den


@dataclass(frozen=True)
class Bruggeman(DielectricModel):
    """Symmetric Bruggeman effective-medium approximation (percolating, self-consistent)."""

    host: DielectricModel
    inclusion: DielectricModel
    volume_fraction: float
    provenance: Provenance = field(default=_BRUGGEMAN)

    param_names: ClassVar[tuple[str, ...]] = ("volume_fraction",)

    def __post_init__(self) -> None:
        _check_fraction(self.volume_fraction)

    def epsilon(self, frequency_hz: FloatArray) -> ComplexArray:
        e1 = self.inclusion.epsilon(frequency_hz)
        e2 = self.host.epsilon(frequency_hz)
        f1 = self.volume_fraction
        f2 = 1.0 - f1
        # 2 ε² − b ε − ε1 ε2 = 0, with b = f1(2ε1−ε2) + f2(2ε2−ε1).
        b = f1 * (2 * e1 - e2) + f2 * (2 * e2 - e1)
        disc = np.sqrt(b * b + 8.0 * e1 * e2)
        root_plus = (b + disc) / 4.0
        root_minus = (b - disc) / 4.0
        # Pick the physical root: negative imaginary part (loss) and positive real part.
        choose_plus = (np.imag(root_plus) <= 0) & (np.real(root_plus) > 0)
        return np.where(choose_plus, root_plus, root_minus)


@dataclass(frozen=True)
class Looyenga(DielectricModel):
    """Looyenga (Landau-Lifshitz-Looyenga) cube-root mixing rule."""

    host: DielectricModel
    inclusion: DielectricModel
    volume_fraction: float
    provenance: Provenance = field(default=_LOOYENGA)

    param_names: ClassVar[tuple[str, ...]] = ("volume_fraction",)

    def __post_init__(self) -> None:
        _check_fraction(self.volume_fraction)

    def epsilon(self, frequency_hz: FloatArray) -> ComplexArray:
        eh = self.host.epsilon(frequency_hz)
        ei = self.inclusion.epsilon(frequency_hz)
        f = self.volume_fraction
        cube_root = f * ei ** (1 / 3) + (1 - f) * eh ** (1 / 3)
        return cube_root**3
