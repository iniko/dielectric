"""Registry and query API over the embedded reference materials.

Parameterizable materials (water, saline at any molarity, seawater, alcohols) are resolved through
factory functions so ``get("saline", molarity=0.05)`` works; tissues are looked up by name/alias.
"""

from __future__ import annotations

from collections.abc import Callable

from .liquids import (
    all_liquids,
    ethanol,
    methanol,
    saline,
    seawater,
    water,
)
from .materials import ReferenceMaterial
from .tissues import all_tissues

#: Factories for materials that take parameters (concentration, temperature).
_FACTORIES: dict[str, Callable[..., ReferenceMaterial]] = {
    "water": water,
    "saline": saline,
    "seawater": seawater,
    "methanol": methanol,
    "ethanol": ethanol,
}


def _alias_index() -> dict[str, str]:
    """Map every name and alias (lower-case) to a canonical lookup key."""
    index: dict[str, str] = {}
    for name in _FACTORIES:
        index[name] = name
    for key, mat in {**all_tissues(), **all_liquids()}.items():
        index[key.lower()] = key
        for alias in mat.aliases:
            index.setdefault(alias.lower(), key)
    return index


def get(name: str, **kwargs: float) -> ReferenceMaterial:
    """Resolve a reference material by name or alias, passing ``kwargs`` to parameterized factories.

    Examples
    --------
    ``get("blood")``, ``get("water", temperature_c=20)``, ``get("saline", molarity=0.05)``.
    """
    key = name.lower()
    index = _alias_index()
    canonical = index.get(key, key)

    if canonical in _FACTORIES:
        return _FACTORIES[canonical](**kwargs)

    tissues = all_tissues()
    if canonical in tissues:
        if kwargs:
            raise ValueError(f"tissue '{canonical}' does not accept parameters {list(kwargs)}")
        return tissues[canonical]

    liquids = all_liquids()
    if canonical in liquids:
        # static liquid entry but a factory exists for its base name
        base = canonical.split("_")[0]
        if base in _FACTORIES:
            return _FACTORIES[base](**kwargs)
        return liquids[canonical]

    raise KeyError(f"unknown reference material '{name}'; try query() to list available materials")


def query(material_class: str | None = None) -> dict[str, ReferenceMaterial]:
    """All default reference materials, optionally filtered by class ('tissue' or 'liquid')."""
    everything = {**all_tissues(), **all_liquids()}
    if material_class is None:
        return everything
    return {k: m for k, m in everything.items() if m.material_class == material_class}


def list_materials(material_class: str | None = None) -> list[str]:
    return sorted(query(material_class))
