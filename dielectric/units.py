"""Explicit, typed units at the I/O boundary.

Silent unit errors (Hz vs GHz, relative vs absolute permittivity) are a classic way a novice
publishes a wrong number. We make units explicit *where data enters the toolkit* and convert to a
single internal convention: frequency in **Hz**, permittivity as **relative** (dimensionless).
"""

from __future__ import annotations

from enum import Enum

import numpy as np
import numpy.typing as npt

from .constants import EPSILON_0, ZERO_CELSIUS_IN_KELVIN

FloatArray = npt.NDArray[np.float64]
ComplexArray = npt.NDArray[np.complex128]
BoolArray = npt.NDArray[np.bool_]


class FrequencyUnit(str, Enum):
    """Frequency unit of an input column."""

    HZ = "Hz"
    KHZ = "kHz"
    MHZ = "MHz"
    GHZ = "GHz"
    THZ = "THz"

    @property
    def to_hz_factor(self) -> float:
        return {
            FrequencyUnit.HZ: 1.0,
            FrequencyUnit.KHZ: 1e3,
            FrequencyUnit.MHZ: 1e6,
            FrequencyUnit.GHZ: 1e9,
            FrequencyUnit.THZ: 1e12,
        }[self]


class PermittivityKind(str, Enum):
    """Whether a permittivity column is relative (ε_r) or absolute (ε = ε_r·ε₀, [F/m])."""

    RELATIVE = "relative"
    ABSOLUTE = "absolute"


def to_hz(values: FloatArray, unit: FrequencyUnit) -> FloatArray:
    """Convert a frequency array to Hz (the internal unit)."""
    return np.asarray(values, dtype=np.float64) * unit.to_hz_factor


def to_relative_permittivity(values: FloatArray, kind: PermittivityKind) -> FloatArray:
    """Convert a permittivity array to relative (dimensionless), the internal unit."""
    arr = np.asarray(values, dtype=np.float64)
    if kind is PermittivityKind.ABSOLUTE:
        return arr / EPSILON_0
    return arr


def celsius_to_kelvin(t_celsius: float) -> float:
    return t_celsius + ZERO_CELSIUS_IN_KELVIN


def kelvin_to_celsius(t_kelvin: float) -> float:
    return t_kelvin - ZERO_CELSIUS_IN_KELVIN


def angular_frequency(frequency_hz: FloatArray) -> FloatArray:
    """ω = 2πf, with f in Hz."""
    return 2.0 * np.pi * np.asarray(frequency_hz, dtype=np.float64)
