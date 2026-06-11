"""Non-linear least-squares fitting of any ``DielectricModel`` to a measured spectrum."""

from __future__ import annotations

from .catalog import ModelInfo, model_info, structure_phrase
from .engine import fit
from .fitters import (
    FAMILIES,
    LADDER_FAMILIES,
    FitFn,
    compose_fitter,
    fit_cole_cole,
    fit_cole_cole_conductivity,
    fit_debye,
    fit_multipole,
    model_label,
    parse_model_label,
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
    "FAMILIES",
    "LADDER_FAMILIES",
    "FitFn",
    "FitResult",
    "ModelInfo",
    "ModelSelectionResult",
    "ModelSelectionWarning",
    "RankedFit",
    "compose_fitter",
    "default_candidates",
    "fit",
    "fit_cole_cole",
    "fit_cole_cole_conductivity",
    "fit_debye",
    "fit_multipole",
    "model_info",
    "model_label",
    "parse_model_label",
    "select_model",
    "structure_phrase",
]
