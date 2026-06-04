"""Non-linear least-squares fitting of any ``DielectricModel`` to a measured spectrum."""

from __future__ import annotations

from .engine import fit
from .fitters import (
    fit_cole_cole,
    fit_cole_cole_conductivity,
    fit_debye,
    fit_multipole,
)
from .result import FitResult
from .selection import (
    ModelSelectionResult,
    ModelSelectionWarning,
    RankedFit,
    default_candidates,
    select_model,
)

__all__ = [
    "FitResult",
    "ModelSelectionResult",
    "ModelSelectionWarning",
    "RankedFit",
    "default_candidates",
    "fit",
    "fit_cole_cole",
    "fit_cole_cole_conductivity",
    "fit_debye",
    "fit_multipole",
    "select_model",
]
