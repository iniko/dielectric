"""``dielectric`` — a publication-ready dielectric spectroscopy analysis toolkit.

Workflow: already-inverted ε*(f) → quality-check → (auto) fit → verify (literature + Kramers-Kronig
+ known-reference QC) → uncertainty → publication-ready export.

Sign convention is engineering ``e^{jωt}``: ε* = ε' + j·Im(ε*) with Im(ε*) < 0 for lossy media.
"""

from __future__ import annotations

from .constants import EPSILON_0
from .convention import ConventionWarning
from .models import Confidence, DielectricModel, Provenance
from .spectrum import QualityReport, Spectrum, SpectrumMetadata
from .units import FrequencyUnit, PermittivityKind

__version__ = "0.1.0"

__all__ = [
    "EPSILON_0",
    "Confidence",
    "ConventionWarning",
    "DielectricModel",
    "FrequencyUnit",
    "PermittivityKind",
    "Provenance",
    "QualityReport",
    "Spectrum",
    "SpectrumMetadata",
    "__version__",
]
