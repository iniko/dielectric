"""Verification: literature comparison, Kramers-Kronig consistency, known-reference QC."""

from __future__ import annotations

from .kramers_kronig import KKResult, kramers_kronig_check
from .literature import (
    MaterialComparison,
    ReferenceOverlay,
    compare_to_reference,
    find_closest_materials,
    reference_overlay,
)
from .validation import (
    CampaignValidation,
    ValidationVerdict,
    validate_campaign,
    validate_set,
)

__all__ = [
    "CampaignValidation",
    "KKResult",
    "MaterialComparison",
    "ReferenceOverlay",
    "ValidationVerdict",
    "compare_to_reference",
    "find_closest_materials",
    "kramers_kronig_check",
    "reference_overlay",
    "validate_campaign",
    "validate_set",
]
