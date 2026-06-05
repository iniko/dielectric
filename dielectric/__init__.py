"""``dielectric`` — a publication-ready dielectric spectroscopy analysis toolkit.

Workflow: already-inverted ε*(f) → quality-check → (auto) fit → verify (literature + Kramers-Kronig
+ known-reference QC) → uncertainty → publication-ready export.

Sign convention is engineering ``e^{jωt}``: ε* = ε' + j·Im(ε*) with Im(ε*) < 0 for lossy media.

The heavy reporting/figure helpers live in :mod:`dielectric.reporting` (import explicitly) so a bare
``import dielectric`` stays lightweight.
"""

from __future__ import annotations

from .constants import EPSILON_0
from .convention import ConventionWarning
from .fitting import FitResult, fit, fit_multipole, select_model
from .io import (
    Campaign,
    CampaignMetadata,
    MeasurementSet,
    ValidationSet,
    load_agilent_85070,
    load_csv,
)
from .models import (
    ColeCole,
    ColeDavidson,
    Confidence,
    DCConductivity,
    Debye,
    DielectricModel,
    HavriliakNegami,
    JonscherUniversal,
    MultiPoleRelaxation,
    Provenance,
)
from .reference import get as get_material
from .reference import query as query_materials
from .spectrum import QualityReport, Spectrum, SpectrumMetadata
from .uncertainty import combine_repeats
from .units import FrequencyUnit, PermittivityKind
from .verification import (
    find_closest_materials,
    kramers_kronig_check,
    validate_campaign,
)

__version__ = "0.1.0"

__all__ = [
    "EPSILON_0",
    "Campaign",
    "CampaignMetadata",
    "ColeCole",
    "ColeDavidson",
    "Confidence",
    "ConventionWarning",
    "DCConductivity",
    "Debye",
    "DielectricModel",
    "FitResult",
    "FrequencyUnit",
    "HavriliakNegami",
    "JonscherUniversal",
    "MeasurementSet",
    "MultiPoleRelaxation",
    "PermittivityKind",
    "Provenance",
    "QualityReport",
    "Spectrum",
    "SpectrumMetadata",
    "ValidationSet",
    "__version__",
    "combine_repeats",
    "find_closest_materials",
    "fit",
    "fit_multipole",
    "get_material",
    "kramers_kronig_check",
    "load_agilent_85070",
    "load_csv",
    "query_materials",
    "select_model",
    "validate_campaign",
]
