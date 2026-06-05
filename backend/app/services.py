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
from dielectric.reference.materials import ReferenceMaterial
from dielectric.reporting import (
    ReproducibilityManifest,
    assemble_report,
    bode_figure,
    cole_cole_figure,
    methods_paragraph,
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
    confidence_band,
    repeat_distribution,
)
from dielectric.verification import (
    compare_to_reference,
    find_closest_materials,
    kramers_kronig_check,
    reference_overlay,
    validate_campaign,
)

from . import schemas
from .store import STORE


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


def make_measurement_set(
    files: list[tuple[str, bytes]], name: str, temperature_c: float
) -> tuple[str, bool]:
    spectra = []
    corrected = False
    for _fn, content in files:
        s, c = _load_spectrum(content)
        spectra.append(s)
        corrected = corrected or c
    ms = MeasurementSet(name, tuple(spectra), temperature_c, tuple(fn for fn, _ in files))
    return STORE.add_measurement(ms), corrected


def make_validation_set(
    files: list[tuple[str, bytes]], name: str, reference: str, molarity: float, temperature_c: float
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
    return STORE.add_validation(vs), corrected


def set_summary(
    set_id: str, obj: MeasurementSet | ValidationSet, role: str, corrected: bool
) -> schemas.SetSummary:
    ta = obj.type_a()
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
    return schemas.ResidualSeries(
        frequency_hz=f.tolist(),
        residual_eps_real=np.real(resid).tolist(),
        residual_loss=(-np.imag(resid)).tolist(),  # loss_model − loss_data (positive-loss)
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
            ta = ms.type_a()
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


def repeats_for_set(set_id: str, frequencies_ghz: list[float]) -> schemas.RepeatsOut:
    """Type A confidence band (+ optional per-frequency distribution) for one set's repeats."""
    obj = _get_set(set_id)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ta = obj.type_a()
        band = confidence_band(ta)
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
        band=_repeat_band(band),
        distributions=dists,
    )


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
        mean = obj.type_a().mean
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
        overlay=schemas.RefOverlay(
            frequency_hz=ov.frequency_hz.tolist(), meas_eps_real=ov.meas_eps_real.tolist(),
            meas_loss=ov.meas_loss.tolist(), ref_eps_real=ov.ref_eps_real.tolist(),
            ref_loss=ov.ref_loss.tolist(), rel_error_pct=ov.rel_error_pct.tolist(),
        ),
    )


_SWEEP_MOLARITIES = (0.1, 0.154, 0.5)
_SWEEP_TEMPS = (22.0, 25.0, 27.0, 30.0, 37.0)


def saline_sweep_for_set(set_id: str) -> schemas.SalineSweepOut:
    """Rank saline (molarity × temperature) candidates by distance to confirm the standard used."""
    obj = _get_set(set_id)
    rows: list[schemas.SalineSweepRow] = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        mean = obj.type_a().mean
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
        for ms in campaign.measurements:
            ta = ms.type_a()
            spectrum = ta.mean
            sel = select_model(spectrum, force_model=req.model, n_poles=req.n_poles)
            fit = sel.chosen.result
            kk = kramers_kronig_check(spectrum, model=fit.model)
            closest = find_closest_materials(spectrum, material_class="tissue",
                                             target_temperature_c=temp, top=3)
            cv = validate_campaign(campaign) if campaign.has_validation else None
            band = (spectrum.band_hz[0] / 1e9, spectrum.band_hz[1] / 1e9)
            methods = methods_paragraph(fit, selection=sel, kk=kk, validation=cv,
                                        n_repeats=ta.n_repeats_used, band_ghz=band)

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
    cv = validate_campaign(campaign)
    return schemas.ValidationOut(
        validated=cv.validated, status=cv.status,
        verdicts=[
            schemas.ValidationVerdictOut(
                set_id=v.set_id, reference=v.reference, passed=v.passed,
                eps_real_rms=v.eps_real_rms, sigma_measured=v.sigma_measured,
                sigma_reference=v.sigma_reference, notes=list(v.notes),
            )
            for v in cv.verdicts
        ],
    )


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
    out = tempfile.mkdtemp()
    bode = os.path.join(out, "bode.png")
    cole = os.path.join(out, "cole.png")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        save_figure(bode_figure(spectrum, fit, title=sample_id), bode)
        save_figure(cole_cole_figure(spectrum, fit), cole)
    manifest = ReproducibilityManifest.from_fit(
        fit, timestamp=datetime.now(timezone.utc).isoformat(), data_source=sample_id
    )
    report = assemble_report(
        title=f"Dielectric analysis: {sample_id}", fit=fit, selection=sel, manifest=manifest,
        validation=sample["validation"], kk=sample["kk"], n_repeats=sample["n_repeats"],
        band_ghz=sample["band"], figure_paths=(bode, cole),
    )
    path = os.path.join(out, f"report.{fmt}")
    if fmt == "docx":
        render_docx(report, path)
    elif fmt == "html":
        render_html(report, path)
    else:
        render_pdf(report, path)
    return path


def _finite(x: float) -> float:
    """JSON has no inf/nan — clamp to large sentinels so responses serialise."""
    if math.isinf(x):
        return 1e308 if x > 0 else -1e308
    if math.isnan(x):
        return 0.0
    return x
