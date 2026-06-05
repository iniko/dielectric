"""Literature provenance carried by every model and reference material.

A model or reference value is only as trustworthy as its source. Every :class:`DielectricModel`
and every embedded reference number carries a :class:`Provenance` so reports can cite the equation
and source automatically, and so a student is never able to publish an *unconfirmed* value
unknowingly (see :class:`Confidence`).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Confidence(str, Enum):
    """Trust level of an embedded numeric value.

    * :attr:`HIGH` — transcribed directly from the primary source (with DOI), equation reproduced
      and unit-checked.
    * :attr:`VERIFY` — derived, secondary-sourced, or otherwise unconfirmed; **never cited bare**.
      Reports render the flag so the value is visibly provisional.
    """

    HIGH = "HIGH"
    VERIFY = "VERIFY"


@dataclass(frozen=True)
class Provenance:
    """A citable source for a model or dataset."""

    authors: str
    year: int
    title: str
    source: str  # journal / report / database name
    doi: str | None = None
    license: str | None = None
    confidence: Confidence = Confidence.HIGH
    note: str | None = None

    def citation(self) -> str:
        """A compact human-readable citation."""
        base = f"{self.authors} ({self.year}). {self.title}. {self.source}"
        if self.doi:
            base += f". https://doi.org/{self.doi}"
        return base

    def short_citation(self) -> str:
        """An inline-prose citation, e.g. ``"Cole et al. (1941)"`` or ``"Debye (1929)"``."""
        surnames = [p.strip() for p in self.authors.replace(";", ",").split(",") if p.strip()]
        first = surnames[0] if surnames else "ref"
        # count distinct surnames (entries that are not just initials like "K. S.")
        names = [s for s in surnames if not all(tok.endswith(".") for tok in s.split())]
        suffix = " et al." if len(names) > 1 else ""
        return f"{first}{suffix} ({self.year})"

    def bibtex_key(self) -> str:
        first_author = self.authors.split(",")[0].split(" ")[0].strip() or "ref"
        return f"{first_author}{self.year}"

    def to_bibtex(self) -> str:
        """A minimal BibTeX ``@article`` / ``@misc`` entry for this source."""
        entry_type = "article" if self.doi else "misc"
        fields = [
            f"  author = {{{self.authors}}}",
            f"  title = {{{self.title}}}",
            f"  year = {{{self.year}}}",
            f"  journal = {{{self.source}}}",
        ]
        if self.doi:
            fields.append(f"  doi = {{{self.doi}}}")
        if self.note or self.confidence is Confidence.VERIFY:
            note = self.note or ""
            if self.confidence is Confidence.VERIFY:
                note = (note + " " if note else "") + "[VERIFY: confirm against primary source]"
            fields.append(f"  note = {{{note.strip()}}}")
        body = ",\n".join(fields)
        return f"@{entry_type}{{{self.bibtex_key()},\n{body}\n}}"
