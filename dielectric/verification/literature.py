"""Compare a measured spectrum (or a fitted model) against the reference-material database.

Reports a relative-RMS distance in ε' and ε'' over the band overlap, carries each reference's
confidence flag and temperature, and warns on a temperature mismatch (water/saline ε_s drifts
≈ −0.4/°C, which can otherwise masquerade as a real difference).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..models.provenance import Confidence
from ..reference.database import query
from ..reference.materials import ReferenceMaterial
from ..spectrum import Spectrum
from ..units import BoolArray, FloatArray


@dataclass(frozen=True)
class MaterialComparison:
    """Distance of a target spectrum from one reference material."""

    material: str
    confidence: Confidence
    distance: float  # combined relative RMS (ε' and ε'')
    eps_real_rms: float
    loss_rms: float
    in_band_fraction: float
    temperature_delta_c: float | None
    notes: tuple[str, ...]


def compare_to_reference(
    target: Spectrum,
    material: ReferenceMaterial,
    *,
    target_temperature_c: float | None = None,
) -> MaterialComparison:
    """Relative-RMS distance of ``target`` from one reference material over their band overlap."""
    f = target.frequency_hz
    in_band: BoolArray = np.ones(f.size, dtype=bool)
    if material.valid_band_hz is not None:
        lo, hi = material.valid_band_hz
        in_band = (f >= lo) & (f <= hi)
    frac = float(np.mean(in_band))

    notes: list[str] = []
    if frac < 1.0:
        notes.append(
            f"{(1 - frac) * 100:.0f}% of points lie outside the reference's valid band; "
            "comparison uses the overlap only."
        )
    if material.confidence is Confidence.VERIFY:
        notes.append("reference is VERIFY-confidence; confirm its parameters before citing.")

    dt: float | None = None
    if target_temperature_c is not None:
        dt = target_temperature_c - material.temperature_c
        if abs(dt) > 2.0:
            notes.append(
                f"temperature mismatch ΔT = {dt:+.1f} °C (target {target_temperature_c} vs "
                f"reference {material.temperature_c}); ε_s differences may be temperature-driven."
            )

    if not in_band.any():
        return MaterialComparison(
            material.name, material.confidence, float("inf"), float("inf"), float("inf"),
            0.0, dt, (*notes, "no band overlap"),
        )

    fi = f[in_band]
    eps_t = target.epsilon[in_band]
    eps_r = material.model.epsilon(fi)
    scale_re = np.abs(np.real(eps_t)) + 1e-9
    scale_im = np.abs(np.imag(eps_t)) + 1e-9
    eps_real_rms = float(np.sqrt(np.mean(((np.real(eps_t) - np.real(eps_r)) / scale_re) ** 2)))
    loss_rms = float(np.sqrt(np.mean(((np.imag(eps_t) - np.imag(eps_r)) / scale_im) ** 2)))
    distance = float(np.hypot(eps_real_rms, loss_rms))

    return MaterialComparison(
        material.name, material.confidence, distance, eps_real_rms, loss_rms, frac, dt, tuple(notes)
    )


@dataclass(frozen=True)
class ReferenceOverlay:
    """Point-by-point comparison of a target spectrum against one reference, over the band overlap.

    Carries the curves needed to draw a measurement-vs-reference overlay plus a per-frequency
    relative-error trace, and descriptive goodness-of-match scalars. This is **not** a validation:
    a small error does not confirm the measurement (the reference is a population-average model).
    """

    material: str
    confidence: Confidence
    frequency_hz: FloatArray
    meas_eps_real: FloatArray
    meas_loss: FloatArray
    ref_eps_real: FloatArray
    ref_loss: FloatArray
    rel_error_pct: FloatArray  # 100·|ε*_meas − ε*_ref| / |ε*_ref| at each frequency
    rms: float  # combined relative RMS (ε' and ε'')
    eps_real_rms: float
    loss_rms: float
    mean_rel_error_pct: float
    nrmse: float  # RMS(|Δε*|) normalised by mean |ε*_meas|
    max_abs_d_eps_real: float
    max_abs_d_loss: float
    in_band_fraction: float
    temperature_delta_c: float | None
    notes: tuple[str, ...]


def reference_overlay(
    target: Spectrum,
    material: ReferenceMaterial,
    *,
    target_temperature_c: float | None = None,
) -> ReferenceOverlay:
    """Overlay curves + descriptive goodness-of-match of ``target`` vs one reference material."""
    base = compare_to_reference(target, material, target_temperature_c=target_temperature_c)
    f = target.frequency_hz
    in_band: BoolArray = np.ones(f.size, dtype=bool)
    if material.valid_band_hz is not None:
        lo, hi = material.valid_band_hz
        in_band = (f >= lo) & (f <= hi)
    fi = f[in_band]
    eps_t = target.epsilon[in_band]
    eps_r = material.model.epsilon(fi)
    diff = eps_t - eps_r
    rel_error_pct = 100.0 * np.abs(diff) / (np.abs(eps_r) + 1e-9)
    nrmse = float(np.sqrt(np.mean(np.abs(diff) ** 2)) / (np.mean(np.abs(eps_t)) + 1e-9))
    return ReferenceOverlay(
        material=base.material,
        confidence=base.confidence,
        frequency_hz=fi,
        meas_eps_real=np.real(eps_t),
        meas_loss=-np.imag(eps_t),  # display the conventional positive loss ε'' = -Im(ε*)
        ref_eps_real=np.real(eps_r),
        ref_loss=-np.imag(eps_r),
        rel_error_pct=rel_error_pct,
        rms=base.distance,
        eps_real_rms=base.eps_real_rms,
        loss_rms=base.loss_rms,
        mean_rel_error_pct=float(np.mean(rel_error_pct)),
        nrmse=nrmse,
        max_abs_d_eps_real=float(np.max(np.abs(np.real(diff)))) if fi.size else float("nan"),
        max_abs_d_loss=float(np.max(np.abs(np.imag(diff)))) if fi.size else float("nan"),
        in_band_fraction=base.in_band_fraction,
        temperature_delta_c=base.temperature_delta_c,
        notes=base.notes,
    )


def find_closest_materials(
    target: Spectrum,
    *,
    references: dict[str, ReferenceMaterial] | None = None,
    material_class: str | None = None,
    target_temperature_c: float | None = None,
    top: int = 5,
) -> list[MaterialComparison]:
    """Rank reference materials by distance from ``target`` (closest first)."""
    refs = references or query(material_class)
    comparisons = [
        compare_to_reference(target, m, target_temperature_c=target_temperature_c)
        for m in refs.values()
    ]
    comparisons.sort(key=lambda c: c.distance)
    return comparisons[:top]
