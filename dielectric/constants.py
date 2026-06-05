"""Physical constants used across the toolkit (SI units).

Values are CODATA 2018. Kept in one place so every module shares identical numerics.
"""

from __future__ import annotations

#: Vacuum permittivity ε₀ [F/m].
EPSILON_0: float = 8.8541878128e-12

#: Vacuum permeability μ₀ [H/m].
MU_0: float = 1.25663706212e-6

#: Speed of light in vacuum c [m/s].
SPEED_OF_LIGHT: float = 299792458.0

#: Boltzmann constant k_B [J/K].
BOLTZMANN: float = 1.380649e-23

#: Elementary charge e [C].
ELEMENTARY_CHARGE: float = 1.602176634e-19

#: 0 °C expressed in kelvin, for temperature conversions.
ZERO_CELSIUS_IN_KELVIN: float = 273.15
