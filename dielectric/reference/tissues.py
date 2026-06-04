"""Biological-tissue reference dielectrics (Gabriel 1996 / IT'IS), microwave 2-Cole-Cole form.

The full Gabriel model is a 4-Cole-Cole dispersion (α, β, γ, δ) + σ. For the 0.2–20 GHz band only
the two fastest dispersions (γ ≈ ps, β ≈ ns) plus ε∞ and the ionic conductivity σ_i materially shape
the spectrum, so each tissue is embedded as a 2-pole Cole-Cole + DC σ. The µs–ms α-dispersion terms
are **documented-as-dropped**, not invented.

Provenance / honesty: network access was unavailable when this snapshot was built, so the numeric
parameters come from model knowledge rather than a live read of the authoritative IFAC "Dielectric
Properties of Body Tissues" table (Gabriel report Appendix C). The whole tissue set is therefore
flagged :attr:`Confidence.VERIFY` — usable for *comparison/guidance*, but a value must be confirmed
against the primary source before being cited. :mod:`dielectric.reference._updater` documents the
(network-gated) refresh that would promote these to HIGH.
"""

from __future__ import annotations

from ..models.multipole import MultiPoleRelaxation
from ..models.provenance import Confidence, Provenance
from .materials import ReferenceMaterial

GABRIEL_1996 = Provenance(
    authors="Gabriel, S., Lau, R. W., Gabriel, C.",
    year=1996,
    title=(
        "The dielectric properties of biological tissues: III. Parametric models "
        "for the dielectric spectrum of tissues"
    ),
    source="Physics in Medicine and Biology 41, 2271; data via IT'IS Tissue Properties (CC BY)",
    doi="10.1088/0031-9155/41/11/003",
    license="CC BY (IT'IS Tissue Properties database)",
    confidence=Confidence.VERIFY,
    note="Microwave 2-Cole-Cole restriction; confirm parameters against IFAC/Gabriel Appendix C.",
)

# tissue -> (eps_inf, (Δε1, τ1[ps], α1), (Δε2, τ2[ns], α2), σ_i[S/m])
_TISSUES: dict[str, tuple[float, tuple[float, float, float], tuple[float, float, float], float]] = {
    "blood": (4.0, (56.0, 8.377, 0.10), (5200.0, 132.6, 0.10), 0.700),
    "muscle": (4.0, (50.0, 7.234, 0.10), (7000.0, 353.7, 0.10), 0.200),
    "skin_wet": (4.0, (39.0, 7.96, 0.00), (280.0, 79.58, 0.00), 0.0004),
    "skin_dry": (4.0, (32.0, 7.234, 0.00), (1100.0, 32.48, 0.20), 0.0002),
    "fat": (2.5, (3.0, 7.96, 0.20), (15.0, 15.92, 0.10), 0.01),
    "liver": (4.0, (39.0, 8.842, 0.10), (6000.0, 530.5, 0.20), 0.02),
    "brain_grey": (4.0, (45.0, 7.958, 0.10), (400.0, 15.92, 0.15), 0.02),
    "brain_white": (4.0, (32.0, 7.958, 0.10), (100.0, 7.958, 0.10), 0.02),
    "bone_cortical": (2.5, (10.0, 13.26, 0.20), (180.0, 79.58, 0.20), 0.020),
    "kidney": (4.0, (47.0, 7.958, 0.10), (3500.0, 198.9, 0.22), 0.05),
    "lung_inflated": (2.5, (18.0, 7.958, 0.10), (500.0, 63.66, 0.10), 0.03),
    "breast_fat": (2.5, (3.0, 17.68, 0.10), (15.0, 63.66, 0.10), 0.010),
    "heart": (4.0, (50.0, 7.958, 0.10), (1200.0, 159.2, 0.05), 0.05),
}

# 0.2–20 GHz is where the 2-pole restriction is valid.
_TISSUE_BAND_HZ = (1.0e8, 2.0e10)


def _build_tissue(name: str) -> ReferenceMaterial:
    eps_inf, (d1, t1_ps, a1), (d2, t2_ns, a2), sigma = _TISSUES[name]
    model = MultiPoleRelaxation(
        eps_inf=eps_inf,
        terms=((d1, t1_ps * 1e-12, a1), (d2, t2_ns * 1e-9, a2)),
        sigma_dc=sigma,
    )
    return ReferenceMaterial(
        name=name,
        model=model,
        provenance=GABRIEL_1996,
        temperature_c=37.0,  # body temperature, as tabulated by Gabriel
        material_class="tissue",
        confidence=Confidence.VERIFY,
        valid_band_hz=_TISSUE_BAND_HZ,
    )


def all_tissues() -> dict[str, ReferenceMaterial]:
    """Every embedded tissue reference material, keyed by name."""
    return {name: _build_tissue(name) for name in _TISSUES}
