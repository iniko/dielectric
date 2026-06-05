"""Known-reference QC: validate a campaign against the literature value of a known material.

A validation set is repeat measurements of a *known reference material* (e.g. saline). We confirm
the probe/inversion is trustworthy by comparing the set's Type A mean to that material's literature
model over the band overlap, **assessing ε' and σ_DC separately** (the σ-dominated low-frequency
loss would otherwise swamp a single combined metric). A campaign is ``validated`` only if **all**
its validation sets pass; with no validation set it is reported **"not validated"**.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..io.campaign import Campaign, ValidationSet
from ..reference.database import get
from ..units import BoolArray, FloatArray


@dataclass(frozen=True)
class ValidationVerdict:
    """QC outcome for one validation set."""

    set_id: str
    reference: str
    passed: bool
    eps_real_rms: float
    sigma_rel_deviation: float
    sigma_measured: float
    sigma_reference: float
    temperature_delta_c: float | None
    in_band_fraction: float
    tol_eps: float
    tol_sigma: float
    notes: tuple[str, ...]


@dataclass(frozen=True)
class CampaignValidation:
    """Aggregate validation status for a campaign."""

    validated: bool
    verdicts: tuple[ValidationVerdict, ...]
    status: str  # human-readable label for reports

    @property
    def has_validation(self) -> bool:
        return len(self.verdicts) > 0


def _low_freq_sigma(eff_sigma: FloatArray, n: int = 5) -> float:
    """Robust DC-conductivity estimate: median σ_eff over the lowest few in-band points."""
    k = min(n, eff_sigma.size)
    return float(np.median(eff_sigma[:k]))


def validate_set(
    vset: ValidationSet,
    *,
    temperature_c: float,
    tol_eps: float = 0.10,
    tol_sigma: float = 0.35,
    outlier_k: float | None = 3.5,
) -> ValidationVerdict:
    """QC one validation set against its declared reference material."""
    mean = vset.type_a(outlier_k=outlier_k).mean
    kwargs: dict[str, float] = {**vset.reference_kwargs, "temperature_c": temperature_c}
    try:
        material = get(vset.reference, **kwargs)
    except (TypeError, ValueError):
        material = get(vset.reference, **vset.reference_kwargs)

    f = mean.frequency_hz
    in_band: BoolArray = np.ones(f.size, dtype=bool)
    if material.valid_band_hz is not None:
        lo, hi = material.valid_band_hz
        in_band = (f >= lo) & (f <= hi)
    frac = float(np.mean(in_band))
    fi = f[in_band]
    eps_meas = mean.epsilon[in_band]
    eps_ref = material.model.epsilon(fi)

    scale = np.abs(np.real(eps_meas)) + 1e-9
    eps_real_rms = float(np.sqrt(np.mean(((np.real(eps_meas) - np.real(eps_ref)) / scale) ** 2)))

    sigma_meas = _low_freq_sigma(mean.effective_conductivity[in_band])
    sigma_ref = _low_freq_sigma(material.model.effective_conductivity(fi))
    sigma_rel = abs(sigma_meas - sigma_ref) / (abs(sigma_ref) + 1e-9)

    notes: list[str] = []
    dt = temperature_c - material.temperature_c
    if abs(dt) > 2.0:
        notes.append(
            f"ΔT = {dt:+.1f} °C vs the reference's {material.temperature_c} °C; an ε' offset may "
            "be temperature-driven rather than a probe error."
        )
    if material.confidence.value == "VERIFY":
        notes.append("reference is VERIFY-confidence; pass/fail margin inherits that uncertainty")
    if frac < 1.0:
        notes.append(f"{(1 - frac) * 100:.0f}% of points outside reference band; QC uses overlap")

    passed = eps_real_rms <= tol_eps and sigma_rel <= tol_sigma
    return ValidationVerdict(
        set_id=vset.sample_id,
        reference=material.name,
        passed=passed,
        eps_real_rms=eps_real_rms,
        sigma_rel_deviation=sigma_rel,
        sigma_measured=sigma_meas,
        sigma_reference=sigma_ref,
        temperature_delta_c=dt,
        in_band_fraction=frac,
        tol_eps=tol_eps,
        tol_sigma=tol_sigma,
        notes=tuple(notes),
    )


def validate_campaign(
    campaign: Campaign,
    *,
    temperature_c: float | None = None,
    tol_eps: float = 0.10,
    tol_sigma: float = 0.35,
) -> CampaignValidation:
    """Validate every validation set; the campaign is ``validated`` only if **all** pass."""
    temp = temperature_c if temperature_c is not None else campaign.metadata.temperature_c
    if not campaign.has_validation:
        return CampaignValidation(
            validated=False,
            verdicts=(),
            status="NOT VALIDATED — no reference QC set was provided.",
        )
    verdicts = tuple(
        validate_set(vs, temperature_c=temp, tol_eps=tol_eps, tol_sigma=tol_sigma)
        for vs in campaign.validations
    )
    validated = all(v.passed for v in verdicts)
    if validated:
        status = f"VALIDATED — all {len(verdicts)} reference QC set(s) passed."
    else:
        n_fail = sum(not v.passed for v in verdicts)
        status = f"NOT VALIDATED — {n_fail}/{len(verdicts)} reference QC set(s) failed."
    return CampaignValidation(validated=validated, verdicts=verdicts, status=status)
