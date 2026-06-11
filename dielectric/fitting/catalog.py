"""Plain-language descriptions and equations for the candidate models.

Everything here is derived from the model-label grammar
(:func:`dielectric.fitting.fitters.parse_model_label`),
so there is a single source of truth — adding a candidate to the panel automatically gets a
description and an equation with no parallel hand-maintained map to drift out of sync.

The displayed loss is the conventional positive ``ε'' = -Im(ε*)``; the equations below are written
in the internal engineering convention (``e^{jωt}``, ``Im(ε*) < 0``) used by the models.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models.base import DielectricModel
from ..models.multipole import MultiPoleRelaxation
from .fitters import parse_model_label

# Per-family single-pole equation fragment and a one-word shape annotation for the dropdown.
_FAMILY_POLE: dict[str, tuple[str, str]] = {
    "Debye": ("Δε/(1 + jωτ)", "single ideal (unbroadened) relaxation"),
    "Cole-Cole": ("Δε/(1 + (jωτ)^(1−α))", "symmetric broadening"),
    "Cole-Davidson": ("Δε/(1 + jωτ)^β", "asymmetric broadening"),
    "Havriliak-Negami": ("Δε/(1 + (jωτ)^(1−α))^β", "general (asymmetric) broadening"),
    "Jonscher": ("A·(jω/ω_ref)^(n−1)", "fractional power law, no discrete pole"),
}
_DC_TERM = " − jσ_dc/(ωε₀)"


@dataclass(frozen=True)
class ModelInfo:
    """Human-facing metadata for a model label."""

    label: str
    family: str
    n_poles: int
    dc_sigma: bool
    equation: str  # unicode, e.g. "ε* = ε∞ + Σₙ Δεₙ/(1 + jωτₙ) − jσ_dc/(ωε₀)"
    description: str  # "two unbroadened (Debye) relaxations plus a DC-conductivity term"
    annotation: str  # one-liner for the family dropdown


def _poles_phrase(family: str, n_poles: int) -> str:
    if family == "Jonscher":
        return "a Jonscher universal-response term"
    shape = {
        "Debye": "unbroadened (Debye)",
        "Cole-Cole": "Cole-Cole (symmetrically broadened)",
        "Cole-Davidson": "Cole-Davidson (asymmetrically broadened)",
        "Havriliak-Negami": "Havriliak-Negami",
    }[family]
    noun = "relaxation" if n_poles == 1 else "relaxations"
    count = {1: "a single", 2: "two", 3: "three"}.get(n_poles, str(n_poles))
    return f"{count} {shape} {noun}"


def model_info(label: str) -> ModelInfo:
    """Equation + plain-language description for a model label (grammar-derived)."""
    family, n_poles, dc = parse_model_label(label)
    pole_eq, annotation = _FAMILY_POLE[family]

    if family == "Jonscher" or n_poles == 1:
        equation = f"ε* = ε∞ + {pole_eq}"
    else:
        # Σₙ form with a subscript n on the per-pole symbols.
        summed = (pole_eq.replace("Δε", "Δεₙ").replace("τ", "τₙ")
                  .replace("α", "αₙ").replace("β", "βₙ"))
        equation = f"ε* = ε∞ + Σₙ {summed}"
    if dc:
        equation += _DC_TERM

    description = _poles_phrase(family, n_poles)
    if dc:
        description += " plus a DC-conductivity term"

    return ModelInfo(
        label=label, family=family, n_poles=n_poles, dc_sigma=dc,
        equation=equation, description=description, annotation=annotation,
    )


def structure_phrase(model: DielectricModel) -> str:
    """A description derived from a fitted model *instance* (fallback when no label is at hand)."""
    if isinstance(model, MultiPoleRelaxation):
        family = "Debye" if model.fixed_alpha else "Cole-Cole"
        phrase = _poles_phrase(family, model.n_poles)
        if model.sigma_dc is not None:
            phrase += " plus a DC-conductivity term"
        return phrase
    name = type(model).__name__
    family = {
        "Debye": "Debye",
        "ColeCole": "Cole-Cole",
        "ColeDavidson": "Cole-Davidson",
        "HavriliakNegami": "Havriliak-Negami",
        "JonscherUniversal": "Jonscher",
    }.get(name, name)
    return _poles_phrase(family, 1)
