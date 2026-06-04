"""Embedded literature reference materials (biological-tissue emphasis) for comparison.

Every material is a pre-configured :class:`DielectricModel` with provenance and a per-value
confidence flag (HIGH / VERIFY). See :mod:`dielectric.reference._updater` for the authoritative
sources and the (network-gated) refresh that promotes VERIFY values to HIGH.
"""

from __future__ import annotations

from .database import get, list_materials, query
from .liquids import ethanol, methanol, saline, seawater, water
from .materials import ReferenceMaterial
from .tissues import all_tissues

__all__ = [
    "ReferenceMaterial",
    "all_tissues",
    "ethanol",
    "get",
    "list_materials",
    "methanol",
    "query",
    "saline",
    "seawater",
    "water",
]
