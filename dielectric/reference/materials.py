"""Reference material = a pre-configured ``DielectricModel`` instance + provenance + temperature.

Because a reference material *is* a model, it composes with fitting, comparison, and uncertainty
exactly like a user-fitted model. Every embedded numeric value carries a :class:`Confidence` flag
(HIGH / VERIFY) so an unconfirmed value is never cited bare in a report.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models.base import DielectricModel
from ..models.provenance import Confidence, Provenance


@dataclass(frozen=True)
class ReferenceMaterial:
    """A named, citable reference dielectric with a known measurement temperature."""

    name: str
    model: DielectricModel
    provenance: Provenance
    temperature_c: float
    material_class: str  # e.g. "tissue", "liquid"
    confidence: Confidence = Confidence.HIGH
    valid_band_hz: tuple[float, float] | None = None
    aliases: tuple[str, ...] = field(default_factory=tuple)

    def epsilon(self, frequency_hz: object) -> object:
        """Convenience pass-through to the underlying model."""
        return self.model.epsilon(frequency_hz)  # type: ignore[arg-type]

    @property
    def is_confirmed(self) -> bool:
        return self.confidence is Confidence.HIGH
