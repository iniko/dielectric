"""Collect literature provenance from models/materials and emit BibTeX.

Every model and reference material carries a :class:`Provenance`; a report gathers all of them
(de-duplicated) so the equations and reference values it uses are automatically cited.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..models.provenance import Provenance


def collect_provenances(*sources: object) -> list[Provenance]:
    """Gather de-duplicated provenances from objects that expose ``.provenance`` or are one."""
    found: dict[str, Provenance] = {}

    def _add(p: Provenance) -> None:
        found.setdefault(p.bibtex_key(), p)

    def _visit(obj: object) -> None:
        if isinstance(obj, Provenance):
            _add(obj)
        elif hasattr(obj, "provenance") and isinstance(obj.provenance, Provenance):
            _add(obj.provenance)
        elif isinstance(obj, Iterable) and not isinstance(obj, str | bytes):
            for item in obj:
                _visit(item)

    for source in sources:
        _visit(source)
    return list(found.values())


def to_bibtex(*sources: object) -> str:
    """BibTeX for every provenance found in ``sources`` (models, materials, fits, lists)."""
    entries = collect_provenances(*sources)
    entries.sort(key=lambda p: p.bibtex_key())
    return "\n\n".join(e.to_bibtex() for e in entries)
