"""Orchestration: drive the ``dielectric`` library and map its outputs to API schemas.

This is the only place the backend touches the science library. It contains no numerics of its own.
"""

from __future__ import annotations

import math
import os
import tempfile
import warnings
from datetime import datetime, timezone

import numpy as np

from dielectric.convention import ConventionWarning
from dielectric.fitting import select_model
from dielectric.io.campaign import (
    Campaign,
    CampaignMetadata,
    MeasurementSet,
    ValidationSet,
)
from dielectric.io.csv_loader import load_agilent_85070
from dielectric.reference.database import query
from dielectric.reporting import (
    ReproducibilityManifest,
    assemble_report,
    bode_figure,
    cole_cole_figure,
    methods_paragraph,
    render_docx,
    render_pdf,
    save_figure,
)
from dielectric.reporting.formatting import format_measurement
from dielectric.spectrum import Spectrum
from dielectric.uncertainty.gum import GUMBudget, UncertaintyComponent
from dielectric.verification import (
    find_closest_materials,
    kramers_kronig_check,
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

            params = [
                schemas.ParamOut(
                    name=n, value=fit.params[n], uncertainty=fit.param_uncertainties.get(n, 0.0),
                    formatted=format_measurement(
                        fit.params[n], fit.param_uncertainties.get(n, 0.0)
                    ),
                )
                for n in fit.model.param_names
            ]
            ranking = [
                schemas.RankedOut(
                    label=rf.label, n_params=rf.result.n_params,
                    chi2_reduced=_finite(rf.result.chi2_reduced), aicc=_finite(rf.result.aicc),
                    delta_aicc=_finite(rf.delta_aicc), bic=_finite(rf.result.bic),
                    r_squared=rf.result.r_squared,
                    flag=(
                        "overparam" if rf.overparameterized
                        else "degenerate" if rf.degenerate else ""
                    ),
                    chosen=rf.label == sel.chosen.label,
                )
                for rf in sel.ranking
            ]
            results.append(schemas.AnalysisResult(
                sample_id=ms.sample_id, chosen_model=sel.chosen.label, overridden=sel.overridden,
                params=params, r_squared=fit.r_squared, chi2_reduced=_finite(fit.chi2_reduced),
                aicc=_finite(fit.aicc), ranking=ranking, selection_warnings=list(sel.warnings),
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
                                   "band": band}

        validation = _validation_out(campaign)

    analysis = schemas.CampaignAnalysis(campaign_id=campaign_id, results=results,
                                        validation=validation)
    STORE.analyses[campaign_id] = {"analysis": analysis, "samples": cache}
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
