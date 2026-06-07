"""Orchestration: drive the ``dielectric`` library and map its outputs to API schemas.

This is the only place the backend touches the science library. It contains no numerics of its own.
"""

from __future__ import annotations

import math
import os
import tempfile
import warnings
from datetime import datetime, timezone
from typing import cast

import numpy as np

from dielectric.comparison import (
    compare_parameters,
    compare_spectra,
    dominant_relaxation,
    static_permittivity,
    static_permittivity_uncertainty,
)
from dielectric.convention import ConventionWarning
from dielectric.fitting import select_model
from dielectric.fitting.result import FitResult
from dielectric.fitting.selection import ModelSelectionResult
from dielectric.io.campaign import (
    Campaign,
    CampaignMetadata,
    MeasurementSet,
    ValidationSet,
)
from dielectric.io.csv_loader import load_agilent_85070
from dielectric.reference.database import get, query
from dielectric.reference.liquids import (
    mass_percent_from_molarity,
    molarity_from_mass_percent,
)
from dielectric.reference.materials import ReferenceMaterial
from dielectric.reporting import (
    ReproducibilityManifest,
    assemble_comparison_report,
    assemble_report,
    bode_figure,
    cole_cole_figure,
    comparison_overlay_figure,
    difference_figure,
    methods_paragraph,
    render_comparison_docx,
    render_comparison_html,
    render_comparison_pdf,
    render_docx,
    render_html,
    render_pdf,
    save_figure,
)
from dielectric.reporting.formatting import format_measurement
from dielectric.spectrum import Spectrum
from dielectric.uncertainty.gum import GUMBudget, UncertaintyComponent
from dielectric.uncertainty.typea import (
    TypeABand,
    TypeAResult,
    combine_repeats,
    confidence_band,
    repeat_distribution,
)
from dielectric.verification import (
    compare_to_reference,
    find_closest_materials,
    kramers_kronig_check,
    reference_overlay,
    validate_mean,
)
from dielectric.verification.literature import ReferenceOverlay
from dielectric.verification.validation import CampaignValidation, ValidationVerdict

from . import schemas
from .store import STORE, ScreeningChoice, ValidationConfig


def _screened_type_a(
    obj: MeasurementSet | ValidationSet, set_id: str | None = None
) -> TypeAResult:
    """Type A combine honoring the set's stored screening choice (threshold + manual overrides)."""
    sid = set_id or STORE.set_id_of(obj)
    ch = STORE.screening_for(sid)
    return combine_repeats(
        obj.spectra, outlier_k=ch.outlier_k, manual_exclude=ch.manual_exclude,
        manual_keep=ch.manual_keep, sample_id=obj.sample_id, temperature_c=obj.temperature_c,
    )


_SCREEN_METHOD = (
    "robust MAD-based z-score (Hampel identifier) of each repeat's median relative distance from "
    "the consensus (median) spectrum; applied only when n≥4 and never dropping all repeats"
)
_SCREEN_CITATION = "Hampel 1974; Rousseeuw & Croux 1993 (1.4826 MAD scaling)"


def _load_spectrum(content: bytes) -> tuple[Spectrum, bool]:
    """Parse an uploaded 85070 CSV; return (spectrum, sign_was_corrected)."""
    with tempfile.NamedTemporaryFile("wb", suffix=".csv", delete=False) as tf:
        tf.write(content)
        path = tf.name
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            spectrum = load_agilent_85070(path)
        corrected = any(issubclass(w.category, ConventionWarning) for w in caught)
    finally:
        os.unlink(path)
    return spectrum, corrected


def _unique_measurement_name(name: str) -> str:
    """Disambiguate a batch name so two same-named batches never collapse in the fits cache
    (which is keyed by sample_id) — that was the 'comparison needs two batches' bug."""
    existing = {ms.sample_id for ms in STORE.measurement_sets.values()}
    if name not in existing:
        return name
    i = 2
    while f"{name} ({i})" in existing:
        i += 1
    return f"{name} ({i})"


def make_measurement_set(
    files: list[tuple[str, bytes]], name: str, temperature_c: float
) -> tuple[str, bool]:
    spectra = []
    corrected = False
    for _fn, content in files:
        s, c = _load_spectrum(content)
        spectra.append(s)
        corrected = corrected or c
    ms = MeasurementSet(
        _unique_measurement_name(name), tuple(spectra), temperature_c,
        tuple(fn for fn, _ in files),
    )
    return STORE.add_measurement(ms), corrected


def make_validation_set(
    files: list[tuple[str, bytes]], name: str, reference: str, molarity: float,
    temperature_c: float, salinity_psu: float | None = None,
) -> tuple[str, bool]:
    spectra = []
    corrected = False
    for _fn, content in files:
        s, c = _load_spectrum(content)
        spectra.append(s)
        corrected = corrected or c
    kwargs = {"molarity": molarity} if reference == "saline" else {}
    vs = ValidationSet(name, tuple(spectra), reference, kwargs, temperature_c,
                       tuple(fn for fn, _ in files))
    vid = STORE.add_validation(vs)
    STORE.validation_config[vid] = ValidationConfig(  # seed the editable config
        reference=reference, molarity=molarity, salinity_psu=salinity_psu,
        temperature_c=temperature_c,
    )
    return vid, corrected


def set_summary(
    set_id: str, obj: MeasurementSet | ValidationSet, role: str, corrected: bool
) -> schemas.SetSummary:
    ta = _screened_type_a(obj, set_id)
    mean = ta.mean
    q = mean.quality_report()
    notes = []
    if corrected:
        notes.append("positive-loss data was detected and negated to the internal e^{jωt} "
                     "convention (Im(ε*) < 0).")
    reference = getattr(obj, "reference", None)
    molarity = obj.reference_kwargs.get("molarity") if isinstance(obj, ValidationSet) else None
    return schemas.SetSummary(
        id=set_id,
        role=role,
        name=obj.sample_id,
        n_repeats=obj.n_repeats,
        n_used=ta.n_repeats_used,
        excluded_indices=list(ta.excluded_indices),
        excluded_filenames=[
            obj.file_names[i] for i in ta.excluded_indices if i < len(obj.file_names)
        ],
        band_ghz=(mean.band_hz[0] / 1e9, mean.band_hz[1] / 1e9),
        eps_real_range=(float(mean.eps_real[0]), float(mean.eps_real[-1])),
        sigma_low_s_per_m=float(mean.effective_conductivity[0]),
        quality_warnings=list(q.warnings),
        reference=reference,
        molarity=molarity,
        notes=notes,
    )


def build_campaign(req: schemas.CampaignCreate) -> str:
    measurements = tuple(STORE.measurement_sets[i] for i in req.measurement_set_ids)
    validations = tuple(STORE.validation_sets[i] for i in req.validation_set_ids)
    campaign = Campaign(
        measurements=measurements, validations=validations,
        metadata=CampaignMetadata(title=req.title, temperature_c=req.temperature_c),
    )
    return STORE.add_campaign(campaign)


def _plot(spectrum: Spectrum, fit_model: object) -> schemas.SpectrumPlot:
    f = spectrum.frequency_hz
    fg = np.geomspace(f[0], f[-1], 200)
    return schemas.SpectrumPlot(
        frequency_hz=f.tolist(),
        eps_real=spectrum.eps_real.tolist(),
        loss=spectrum.loss.tolist(),
        fit_frequency_hz=fg.tolist(),
        fit_eps_real=fit_model.epsilon_real(fg).tolist(),  # type: ignore[attr-defined]
        fit_loss=fit_model.loss(fg).tolist(),  # type: ignore[attr-defined]
    )


def _get_set(set_id: str) -> MeasurementSet | ValidationSet:
    if set_id in STORE.measurement_sets:
        return STORE.measurement_sets[set_id]
    if set_id in STORE.validation_sets:
        return STORE.validation_sets[set_id]
    raise KeyError(f"unknown set '{set_id}'")


def _params_out(fit: FitResult) -> list[schemas.ParamOut]:
    return [
        schemas.ParamOut(
            name=n, value=fit.params[n], uncertainty=fit.param_uncertainties.get(n, 0.0),
            formatted=format_measurement(fit.params[n], fit.param_uncertainties.get(n, 0.0)),
        )
        for n in fit.model.param_names
    ]


def _ranking_out(sel: ModelSelectionResult) -> list[schemas.RankedOut]:
    return [
        schemas.RankedOut(
            label=rf.label, n_params=rf.result.n_params,
            chi2_reduced=_finite(rf.result.chi2_reduced), aicc=_finite(rf.result.aicc),
            delta_aicc=_finite(rf.delta_aicc), bic=_finite(rf.result.bic),
            r_squared=rf.result.r_squared,
            flag=("overparam" if rf.overparameterized else "degenerate" if rf.degenerate else ""),
            chosen=rf.label == sel.chosen.label,
        )
        for rf in sel.ranking
    ]


def _residual_series(fit: FitResult) -> schemas.ResidualSeries:
    f = fit.frequency_hz
    resid = fit.residuals  # ε_model − ε_data (internal convention)
    sr = fit.standardized_residuals  # raw ÷ per-point σ (dimensionless pulls)
    return schemas.ResidualSeries(
        frequency_hz=f.tolist(),
        residual_eps_real=np.real(resid).tolist(),
        residual_loss=(-np.imag(resid)).tolist(),  # loss_model − loss_data (positive-loss)
        norm_eps_real=np.real(sr).tolist(),
        norm_loss=(-np.imag(sr)).tolist(),
    )


def _resolve_force_model(req: schemas.FitRequest) -> str | None:
    """Constrained customization: explicit model wins; else the DC-σ toggle picks a family."""
    if req.model:
        return req.model
    if req.dc_sigma is True:
        return "Cole-Cole + DC σ"
    if req.dc_sigma is False:
        return "Cole-Cole"
    return None


def fit_campaign(campaign_id: str, req: schemas.FitRequest) -> schemas.FitOut:
    """Fit + select a model per measurement sample, cache the fit, return the fit step payload."""
    if req.fixed_params:
        raise ValueError("fixing individual parameters is not yet supported")
    campaign = STORE.campaigns[campaign_id]
    force = _resolve_force_model(req)
    results: list[schemas.FitResultOut] = []
    cache: dict[str, dict[str, object]] = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for ms in campaign.measurements:
            ta = _screened_type_a(ms)
            spectrum = ta.mean
            sel = select_model(spectrum, force_model=force, n_poles=req.n_poles)
            fit = sel.chosen.result
            band = (spectrum.band_hz[0] / 1e9, spectrum.band_hz[1] / 1e9)
            results.append(schemas.FitResultOut(
                sample_id=ms.sample_id, chosen_model=sel.chosen.label, overridden=sel.overridden,
                params=_params_out(fit), r_squared=fit.r_squared,
                chi2_reduced=_finite(fit.chi2_reduced), aicc=_finite(fit.aicc),
                ranking=_ranking_out(sel), selection_warnings=list(sel.warnings),
                plot=_plot(spectrum, fit.model), residual=_residual_series(fit),
            ))
            cache[ms.sample_id] = {"fit": fit, "selection": sel, "spectrum": spectrum,
                                   "type_a": ta, "band": band}
    STORE.fits[campaign_id] = cache
    return schemas.FitOut(campaign_id=campaign_id, results=results)


def _fits(campaign_id: str) -> dict[str, dict[str, object]]:
    """Return the cached per-sample fits, computing a default fit if the step was skipped."""
    cache = STORE.fits.get(campaign_id)
    if cache is None:
        fit_campaign(campaign_id, schemas.FitRequest())
        cache = STORE.fits[campaign_id]
    return cache


def kk_campaign(campaign_id: str) -> schemas.KKDetailOut:
    """Kramers-Kronig detail (predicted vs measured ε') per sample, from the cached fit."""
    cache = _fits(campaign_id)
    results: list[schemas.KKDetail] = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for sample_id, entry in cache.items():
            spectrum = cast(Spectrum, entry["spectrum"])
            fit = cast(FitResult, entry["fit"])
            kk = kramers_kronig_check(spectrum, model=fit.model)
            pred = kk.predicted_eps_real
            meas = kk.measured_eps_real
            rel = (np.abs(pred - meas) / (np.abs(meas) + 1e-9)).tolist()
            results.append(schemas.KKDetail(
                sample_id=sample_id, frequency_hz=spectrum.frequency_hz.tolist(),
                predicted_eps_real=pred.tolist(), measured_eps_real=meas.tolist(),
                relative_residual=rel, residual_rms=kk.residual_rms,
                truncation_estimate=kk.truncation_estimate, consistent=kk.is_consistent,
                warnings=list(kk.warnings),
            ))
    return schemas.KKDetailOut(campaign_id=campaign_id, results=results)


def _repeat_details(
    obj: MeasurementSet | ValidationSet, ta: TypeAResult
) -> list[schemas.RepeatDetail]:
    files = obj.file_names
    excluded = set(ta.excluded_indices)
    return [
        schemas.RepeatDetail(
            index=i,
            filename=files[i] if i < len(files) else f"repeat {i + 1}",
            zscore=_finite(float(ta.repeat_zscores[i])),
            kept=i not in excluded,
            reason=ta.reason(i),
        )
        for i in range(obj.n_repeats)
    ]


def _screening_impact(
    obj: MeasurementSet | ValidationSet, ta: TypeAResult
) -> schemas.ScreeningImpact | None:
    """How the Type A mean shifts if the excluded repeats were kept (reuses compare_spectra)."""
    if not ta.excluded_indices:
        return None  # nothing excluded → no impact to report
    all_mean = combine_repeats(obj.spectra, outlier_k=None).mean
    diff = compare_spectra(all_mean, ta.mean)  # all-repeats vs screened
    f = ta.mean.frequency_hz
    j = 0  # lowest in-band frequency as the reference point
    return schemas.ScreeningImpact(
        frequency_ref_hz=float(f[j]),
        eps_real_with=_finite(float(ta.mean.eps_real[j])),
        eps_real_without=_finite(float(all_mean.eps_real[j])),
        sigma_with=_finite(float(ta.mean.effective_conductivity[j])),
        sigma_without=_finite(float(all_mean.effective_conductivity[j])),
        max_abs_d_eps_real=_finite(float(np.max(np.abs(diff.delta_eps_real)))),
        max_abs_d_sigma=_finite(float(np.max(np.abs(diff.delta_sigma)))),
    )


def _screening_info(ta: TypeAResult) -> schemas.ScreeningInfo:
    return schemas.ScreeningInfo(
        outlier_k=ta.outlier_k_used,
        n_total=ta.n_repeats_total,
        n_used=ta.n_repeats_used,
        n_excluded=len(ta.excluded_indices),
        manual_exclude=list(ta.manual_exclude),
        manual_keep=list(ta.manual_keep),
        method=_SCREEN_METHOD,
        citation=_SCREEN_CITATION,
    )


def repeats_for_set(set_id: str, frequencies_ghz: list[float]) -> schemas.RepeatsOut:
    """Type A band + transparent per-repeat screening breakdown for one set's repeats."""
    obj = _get_set(set_id)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ta = _screened_type_a(obj, set_id)
        band = confidence_band(ta)
        details = _repeat_details(obj, ta)
        screening = _screening_info(ta)
        impact = _screening_impact(obj, ta)
        dists: list[schemas.RepeatDistributionOut] = []
        if frequencies_ghz:
            for d in repeat_distribution(obj.spectra, [g * 1e9 for g in frequencies_ghz]):
                dists.append(schemas.RepeatDistributionOut(
                    frequency_hz=d.frequency_hz,
                    eps_real_samples=d.eps_real_samples.tolist(),
                    eps_imag_samples=d.eps_imag_samples.tolist(),
                    eps_real_mean=d.eps_real_mean, eps_real_std=d.eps_real_std,
                    eps_imag_mean=d.eps_imag_mean, eps_imag_std=d.eps_imag_std,
                    shapiro_p_real=_finite(d.shapiro_p_real),
                    shapiro_p_imag=_finite(d.shapiro_p_imag),
                ))
    return schemas.RepeatsOut(
        set_id=set_id, name=obj.sample_id, n_repeats=obj.n_repeats, n_used=ta.n_repeats_used,
        excluded_indices=list(ta.excluded_indices), coverage_k=band.coverage_k,
        band=_repeat_band(band), distributions=dists,
        repeats=details, screening=screening, impact=impact,
    )


def set_screening(set_id: str, req: schemas.ScreeningRequest) -> schemas.RepeatsOut:
    """Persist a set's screening choice, invalidate dependent caches, return the refreshed view."""
    _get_set(set_id)  # 404 if unknown
    STORE.screening[set_id] = ScreeningChoice(
        outlier_k=req.outlier_k,
        manual_exclude=tuple(req.manual_exclude),
        manual_keep=tuple(req.manual_keep),
    )
    STORE.invalidate_caches_for_set(set_id)
    return repeats_for_set(set_id, [])


def _repeat_band(band: TypeABand) -> schemas.RepeatBand:
    return schemas.RepeatBand(
        frequency_hz=band.frequency_hz.tolist(), eps_real=band.eps_real.tolist(),
        eps_real_lo=band.eps_real_lo.tolist(), eps_real_hi=band.eps_real_hi.tolist(),
        sigma=band.sigma.tolist(), sigma_lo=band.sigma_lo.tolist(), sigma_hi=band.sigma_hi.tolist(),
    )


def _reference_material(req: schemas.ReferenceMatchRequest) -> ReferenceMaterial:
    kwargs: dict[str, float] = {"temperature_c": req.temperature_c}
    if req.molarity is not None:
        kwargs["molarity"] = req.molarity
    if req.salinity_psu is not None:
        kwargs["salinity_psu"] = req.salinity_psu
    try:
        return get(req.reference, **kwargs)
    except (TypeError, ValueError):
        return get(req.reference)  # tissues etc. take no parameters


def reference_match_for_set(
    set_id: str, req: schemas.ReferenceMatchRequest
) -> schemas.ReferenceMatchOut:
    """Descriptive goodness-of-match of a set's Type A mean against a chosen reference material."""
    obj = _get_set(set_id)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        mean = _screened_type_a(obj, set_id).mean
        material = _reference_material(req)
        ov = reference_overlay(mean, material, target_temperature_c=req.temperature_c)
    return schemas.ReferenceMatchOut(
        set_id=set_id, reference_label=ov.material, confidence=ov.confidence.value,
        rms=_finite(ov.rms), eps_real_rms=_finite(ov.eps_real_rms), loss_rms=_finite(ov.loss_rms),
        mean_rel_error_pct=_finite(ov.mean_rel_error_pct), nrmse=_finite(ov.nrmse),
        max_abs_d_eps_real=_finite(ov.max_abs_d_eps_real),
        max_abs_d_loss=_finite(ov.max_abs_d_loss),
        in_band_fraction=ov.in_band_fraction, temperature_delta_c=ov.temperature_delta_c,
        notes=list(ov.notes),
        overlay=_ref_overlay(ov),
    )


def _ref_overlay(ov: ReferenceOverlay) -> schemas.RefOverlay:
    return schemas.RefOverlay(
        frequency_hz=ov.frequency_hz.tolist(), meas_eps_real=ov.meas_eps_real.tolist(),
        meas_loss=ov.meas_loss.tolist(), ref_eps_real=ov.ref_eps_real.tolist(),
        ref_loss=ov.ref_loss.tolist(), rel_error_pct=ov.rel_error_pct.tolist(),
    )


_SWEEP_MOLARITIES = (0.1, 0.154, 0.5)
_SWEEP_TEMPS = (22.0, 25.0, 27.0, 30.0, 37.0)


def saline_sweep_for_set(set_id: str) -> schemas.SalineSweepOut:
    """Rank saline (molarity × temperature) candidates by distance to confirm the standard used."""
    obj = _get_set(set_id)
    rows: list[schemas.SalineSweepRow] = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        mean = _screened_type_a(obj, set_id).mean
        for m in _SWEEP_MOLARITIES:
            for t in _SWEEP_TEMPS:
                material = get("saline", molarity=m, temperature_c=t)
                cmp = compare_to_reference(mean, material, target_temperature_c=t)
                rows.append(schemas.SalineSweepRow(
                    molarity=m, temperature_c=t, rms=_finite(cmp.distance),
                    eps_real_rms=_finite(cmp.eps_real_rms),
                ))
    rows.sort(key=lambda r: r.rms)
    return schemas.SalineSweepOut(set_id=set_id, rows=rows)


# ---- editable, batch-linked validation --------------------------------------------------------


def _config_kwargs(cfg: ValidationConfig) -> dict[str, float]:
    """Reference-specific kwargs for `database.get` from a stored validation config."""
    if cfg.reference == "saline":
        return {"molarity": cfg.molarity}
    if cfg.reference == "seawater" and cfg.salinity_psu is not None:
        return {"salinity_psu": cfg.salinity_psu}
    return {}


def _material_from_config(cfg: ValidationConfig) -> ReferenceMaterial:
    kwargs = {**_config_kwargs(cfg), "temperature_c": cfg.temperature_c}
    try:
        return get(cfg.reference, **kwargs)
    except (TypeError, ValueError):
        return get(cfg.reference)


def _verdict_for(vset: ValidationSet, vid: str | None, cfg: ValidationConfig) -> ValidationVerdict:
    mean = _screened_type_a(vset, vid).mean
    return validate_mean(
        mean, set_id=vset.sample_id, reference=cfg.reference,
        reference_kwargs=_config_kwargs(cfg), temperature_c=cfg.temperature_c,
    )


def _configured_campaign_validation(campaign: Campaign) -> CampaignValidation:
    """Validate each set against its **stored (editable) config**, not the baked-in reference."""
    verdicts = tuple(
        _verdict_for(vs, STORE.set_id_of(vs), STORE.validation_config_for(STORE.set_id_of(vs)))
        for vs in campaign.validations
    )
    validated = bool(verdicts) and all(v.passed for v in verdicts)
    if not verdicts:
        status = "NOT VALIDATED — no reference QC set was provided."
    elif validated:
        status = f"VALIDATED — all {len(verdicts)} reference QC set(s) passed."
    else:
        n_fail = sum(not v.passed for v in verdicts)
        status = f"NOT VALIDATED — {n_fail}/{len(verdicts)} reference QC set(s) failed."
    return CampaignValidation(validated=validated, verdicts=verdicts, status=status)


def _config_out(cfg: ValidationConfig) -> schemas.ValidationConfigOut:
    saline = cfg.reference == "saline"
    return schemas.ValidationConfigOut(
        reference=cfg.reference,
        molarity=cfg.molarity if saline else None,
        mass_percent=mass_percent_from_molarity(cfg.molarity) if saline else None,
        salinity_psu=cfg.salinity_psu if cfg.reference == "seawater" else None,
        temperature_c=cfg.temperature_c,
    )


def _verdict_out(v: ValidationVerdict, linked: list[str]) -> schemas.ValidationVerdictOut:
    return schemas.ValidationVerdictOut(
        set_id=v.set_id, reference=v.reference, passed=v.passed,
        eps_real_rms=_finite(v.eps_real_rms), sigma_measured=_finite(v.sigma_measured),
        sigma_reference=_finite(v.sigma_reference), notes=list(v.notes), linked_batches=linked,
    )


def validation_detail(set_id: str) -> schemas.ValidationDetailOut:
    """Per validation set: verdict + reference overlay (+ saline sweep) under its current config."""
    if set_id not in STORE.validation_sets:
        raise KeyError(f"unknown validation set '{set_id}'")
    vset = STORE.validation_sets[set_id]
    cfg = STORE.validation_config_for(set_id)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        verdict = _verdict_for(vset, set_id, cfg)
        material = _material_from_config(cfg)
        mean = _screened_type_a(vset, set_id).mean
        ov = reference_overlay(mean, material, target_temperature_c=cfg.temperature_c)
        sweep = saline_sweep_for_set(set_id).rows if cfg.reference == "saline" else None
    linked = list(cfg.measurement_set_ids)
    return schemas.ValidationDetailOut(
        set_id=set_id, name=vset.sample_id, reference_label=ov.material,
        confidence=ov.confidence.value, config=_config_out(cfg),
        verdict=_verdict_out(verdict, linked), overlay=_ref_overlay(ov),
        saline_sweep=sweep, linked_batches=linked,
    )


def set_validation_config(
    set_id: str, req: schemas.ValidationConfigRequest
) -> schemas.ValidationDetailOut:
    """Persist an edited validation reference + batch link, invalidate caches, return the detail."""
    if set_id not in STORE.validation_sets:
        raise KeyError(f"unknown validation set '{set_id}'")
    molarity = req.molarity
    if req.mass_percent is not None:
        molarity = molarity_from_mass_percent(req.mass_percent)
    if molarity is None:
        molarity = STORE.validation_config_for(set_id).molarity  # keep prior on a non-saline edit
    STORE.validation_config[set_id] = ValidationConfig(
        reference=req.reference, molarity=molarity, salinity_psu=req.salinity_psu,
        temperature_c=req.temperature_c, measurement_set_ids=tuple(req.measurement_set_ids),
    )
    STORE.invalidate_caches_for_set(set_id)
    return validation_detail(set_id)


def _param_summary(fit: FitResult) -> schemas.ParamSummary:
    p, u = fit.params, fit.param_uncertainties
    tau, tau_u = dominant_relaxation(fit)
    has_sigma = "sigma_dc" in p
    return schemas.ParamSummary(
        eps_static=_finite(static_permittivity(fit.model)),
        eps_static_u=_finite(static_permittivity_uncertainty(fit)),
        eps_inf=_finite(p["eps_inf"]), eps_inf_u=_finite(u.get("eps_inf", 0.0)),
        tau_dominant_s=_finite(tau), tau_dominant_u=_finite(tau_u),
        sigma_dc=_finite(p["sigma_dc"]) if has_sigma else None,
        sigma_dc_u=_finite(u.get("sigma_dc", 0.0)) if has_sigma else None,
    )


def compare_campaign(campaign_id: str, req: schemas.CompareRequest) -> schemas.CompareOut:
    """Overlay every batch and pairwise-difference each against a baseline (normal vs diseased)."""
    cache = _fits(campaign_id)
    sample_ids = list(cache.keys())
    if len(sample_ids) < 2:
        raise ValueError("comparison needs at least two measurement sets")
    baseline = req.baseline or sample_ids[0]
    if baseline not in cache:
        raise ValueError(f"unknown baseline batch '{baseline}'")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        batches: list[schemas.BatchSummary] = []
        for sid in sample_ids:
            entry = cache[sid]
            fit = cast(FitResult, entry["fit"])
            sel = cast(ModelSelectionResult, entry["selection"])
            ta = cast(TypeAResult, entry["type_a"])
            batches.append(schemas.BatchSummary(
                sample_id=sid, model=sel.chosen.label,
                band=_repeat_band(confidence_band(ta)), params=_param_summary(fit),
            ))

        base_fit = cast(FitResult, cache[baseline]["fit"])
        base_mean = cast(TypeAResult, cache[baseline]["type_a"]).mean
        differences: list[schemas.BatchDifference] = []
        for sid in sample_ids:
            if sid == baseline:
                continue
            entry = cache[sid]
            a_fit = cast(FitResult, entry["fit"])
            a_mean = cast(TypeAResult, entry["type_a"]).mean
            sd = compare_spectra(a_mean, base_mean)
            differences.append(schemas.BatchDifference(
                sample_id=sid, baseline=baseline,
                spectrum=schemas.SpectrumDiff(
                    frequency_hz=sd.frequency_hz.tolist(),
                    delta_eps_real=sd.delta_eps_real.tolist(),
                    se_eps_real=sd.se_eps_real.tolist(),
                    significant_eps=[bool(x) for x in sd.significant_eps],
                    delta_sigma=sd.delta_sigma.tolist(), se_sigma=sd.se_sigma.tolist(),
                    significant_sigma=[bool(x) for x in sd.significant_sigma],
                    coverage_k=sd.coverage_k, notes=list(sd.notes),
                ),
                params=[
                    schemas.ParamDiff(
                        name=pd.name, a=_finite(pd.a), ua=_finite(pd.ua), b=_finite(pd.b),
                        ub=_finite(pd.ub), delta=_finite(pd.delta), z=_finite(pd.z),
                        significant=pd.significant,
                    )
                    for pd in compare_parameters(a_fit, base_fit)
                ],
            ))
    return schemas.CompareOut(
        campaign_id=campaign_id, baseline=baseline, batches=batches, differences=differences
    )


def analyze_campaign(campaign_id: str, req: schemas.AnalyzeRequest) -> schemas.CampaignAnalysis:
    campaign = STORE.campaigns[campaign_id]
    temp = campaign.metadata.temperature_c
    results: list[schemas.AnalysisResult] = []
    cache: dict[str, dict[str, object]] = {}

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        cv = _configured_campaign_validation(campaign) if campaign.has_validation else None
        for ms in campaign.measurements:
            ta = _screened_type_a(ms)
            spectrum = ta.mean
            sel = select_model(spectrum, force_model=req.model, n_poles=req.n_poles)
            fit = sel.chosen.result
            kk = kramers_kronig_check(spectrum, model=fit.model)
            closest = find_closest_materials(spectrum, material_class="tissue",
                                             target_temperature_c=temp, top=3)
            band = (spectrum.band_hz[0] / 1e9, spectrum.band_hz[1] / 1e9)
            methods = methods_paragraph(
                fit, selection=sel, kk=kk, validation=cv,
                n_repeats=ta.n_repeats_used, n_repeats_total=ta.n_repeats_total,
                n_excluded=len(ta.excluded_indices), outlier_k=ta.outlier_k_used, band_ghz=band,
            )

            results.append(schemas.AnalysisResult(
                sample_id=ms.sample_id, chosen_model=sel.chosen.label, overridden=sel.overridden,
                params=_params_out(fit), r_squared=fit.r_squared,
                chi2_reduced=_finite(fit.chi2_reduced),
                aicc=_finite(fit.aicc), ranking=_ranking_out(sel),
                selection_warnings=list(sel.warnings),
                kk=schemas.KKOut(residual_rms=kk.residual_rms, consistent=kk.is_consistent,
                                 truncation_estimate=kk.truncation_estimate),
                closest_materials=[
                    schemas.MaterialMatch(material=c.material, distance=c.distance,
                                          eps_real_rms=c.eps_real_rms, loss_rms=c.loss_rms,
                                          confidence=c.confidence.value)
                    for c in closest
                ],
                methods_paragraph=methods, plot=_plot(spectrum, fit.model),
            ))
            cache[ms.sample_id] = {"fit": fit, "selection": sel, "spectrum": spectrum,
                                   "kk": kk, "validation": cv, "n_repeats": ta.n_repeats_used,
                                   "type_a": ta, "band": band}

        validation = _validation_out(campaign)

    analysis = schemas.CampaignAnalysis(campaign_id=campaign_id, results=results,
                                        validation=validation)
    STORE.analyses[campaign_id] = {"analysis": analysis, "samples": cache}
    STORE.fits[campaign_id] = cache  # let the KK/report steps reuse the fitted models
    return analysis


def _validation_out(campaign: Campaign) -> schemas.ValidationOut:
    if not campaign.has_validation:
        return schemas.ValidationOut(validated=False,
                                     status="NOT VALIDATED — no reference QC set provided.",
                                     verdicts=[])
    verdicts: list[schemas.ValidationVerdictOut] = []
    for vs in campaign.validations:
        vid = STORE.set_id_of(vs)
        cfg = STORE.validation_config_for(vid)
        verdicts.append(_verdict_out(_verdict_for(vs, vid, cfg), list(cfg.measurement_set_ids)))
    cv = _configured_campaign_validation(campaign)
    return schemas.ValidationOut(validated=cv.validated, status=cv.status, verdicts=verdicts)


def list_materials() -> list[schemas.MaterialOut]:
    return [
        schemas.MaterialOut(name=m.name, material_class=m.material_class,
                            confidence=m.confidence.value, temperature_c=m.temperature_c)
        for m in query().values()
    ]


def compute_budget(req: schemas.BudgetRequest) -> schemas.BudgetResult:
    comps = tuple(
        UncertaintyComponent(c.name, c.standard_uncertainty, c.sensitivity, c.dof, c.kind)
        for c in req.components
    )
    budget = GUMBudget(req.measurand, req.nominal_value, comps, req.unit)
    uc = budget.combined_standard_uncertainty
    contributions = [
        schemas.BudgetContribution(
            name=c.name, kind=c.kind, contribution=c.contribution, dof=c.dof,
            percent=100.0 * (c.contribution**2) / (uc**2) if uc > 0 else 0.0,
        )
        for c in comps
    ]
    return schemas.BudgetResult(
        combined_standard_uncertainty=uc, effective_dof=_finite(budget.effective_dof),
        coverage_factor=budget.coverage_factor(req.coverage_level),
        expanded_uncertainty=budget.expanded_uncertainty(req.coverage_level),
        relative_expanded=_finite(budget.relative_expanded),
        contributions=contributions, table=budget.table(req.coverage_level),
    )


def generate_report(campaign_id: str, sample_id: str, fmt: str) -> str:
    entry = STORE.analyses.get(campaign_id)
    if entry is None:
        raise KeyError("campaign has not been analyzed yet")
    sample = entry["samples"].get(sample_id)  # type: ignore[index]
    if sample is None:
        raise KeyError(f"unknown sample '{sample_id}'")
    fit, sel, spectrum = sample["fit"], sample["selection"], sample["spectrum"]
    ta = cast(TypeAResult, sample["type_a"])
    out = tempfile.mkdtemp()
    bode = os.path.join(out, "bode.png")
    cole = os.path.join(out, "cole.png")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        save_figure(bode_figure(spectrum, fit, title=sample_id), bode)
        save_figure(cole_cole_figure(spectrum, fit), cole)
    manifest = ReproducibilityManifest.from_fit(
        fit, timestamp=datetime.now(timezone.utc).isoformat(), data_source=sample_id,
        extra={
            "n_repeats_total": str(ta.n_repeats_total),
            "n_repeats_used": str(ta.n_repeats_used),
            "n_repeats_excluded": str(len(ta.excluded_indices)),
            "excluded_indices": str(list(ta.excluded_indices)),
            "outlier_k": "off" if ta.outlier_k_used is None else f"{ta.outlier_k_used:g}",
        },
    )
    report = assemble_report(
        title=f"Dielectric analysis: {sample_id}", fit=fit, selection=sel, manifest=manifest,
        validation=sample["validation"], kk=sample["kk"], n_repeats=ta.n_repeats_used,
        n_repeats_total=ta.n_repeats_total, n_excluded=len(ta.excluded_indices),
        outlier_k=ta.outlier_k_used, band_ghz=sample["band"], figure_paths=(bode, cole),
    )
    path = os.path.join(out, f"report.{fmt}")
    if fmt == "docx":
        render_docx(report, path)
    elif fmt == "html":
        render_html(report, path)
    else:
        render_pdf(report, path)
    return path


def generate_comparison_report(campaign_id: str, baseline: str | None, fmt: str) -> str:
    """Render a campaign-level batch-comparison report (PDF/Word/HTML) from the cached fits."""
    cache = _fits(campaign_id)  # computes a default fit per batch if the step was skipped
    sample_ids = list(cache.keys())
    if len(sample_ids) < 2:
        raise ValueError("a comparison report needs at least two measurement batches")
    base_label = baseline or sample_ids[0]
    if base_label not in cache:
        raise ValueError(f"unknown baseline batch '{base_label}'")

    batches = [
        (sid, cast(FitResult, cache[sid]["fit"]), cast(TypeAResult, cache[sid]["type_a"]))
        for sid in sample_ids
    ]
    base_ta = cast(TypeAResult, cache[base_label]["type_a"])
    out = tempfile.mkdtemp()
    figs: list[str] = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        overlay = comparison_overlay_figure([(sid, ta.mean) for sid, _, ta in batches])
        op = os.path.join(out, "overlay.png")
        save_figure(overlay, op)
        figs.append(op)
        for i, (sid, _fit, ta) in enumerate(batches):
            if sid == base_label:
                continue
            sd = compare_spectra(ta.mean, base_ta.mean)
            dp = os.path.join(out, f"diff_{i}.png")
            save_figure(difference_figure(sd, sample_label=sid, baseline_label=base_label), dp)
            figs.append(dp)
    manifest = ReproducibilityManifest.from_fit(
        batches[0][1], timestamp=datetime.now(timezone.utc).isoformat(),
        data_source=f"batch comparison vs {base_label}",
        extra={"batches": str(sample_ids), "baseline": base_label},
    )
    report = assemble_comparison_report(
        title=f"Batch comparison (baseline: {base_label})", baseline_label=base_label,
        batches=batches, manifest=manifest, figure_paths=tuple(figs),
    )
    path = os.path.join(out, f"comparison.{fmt}")
    if fmt == "docx":
        render_comparison_docx(report, path)
    elif fmt == "html":
        render_comparison_html(report, path)
    else:
        render_comparison_pdf(report, path)
    return path


def _finite(x: float) -> float:
    """JSON has no inf/nan — clamp to large sentinels so responses serialise."""
    if math.isinf(x):
        return 1e308 if x > 0 else -1e308
    if math.isnan(x):
        return 0.0
    return x
