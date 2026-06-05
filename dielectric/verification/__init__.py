"""Verification: literature comparison, Kramers-Kronig consistency, known-reference QC."""

from __future__ import annotations

from .kramers_kronig import KKResult, kramers_kronig_check
from .literature import (
    MaterialComparison,
    compare_to_reference,
    find_closest_materials,
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
    "ValidationVerdict",
    "compare_to_reference",
    "find_closest_materials",
    "kramers_kronig_check",
    "validate_campaign",
    "validate_set",
]
