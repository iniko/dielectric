"""Assemble a structured report once, render it to multiple formats (docx, pdf).

``ReportData`` is the format-independent content; :mod:`dielectric.reporting.report_docx` and
:mod:`dielectric.reporting.report_pdf` render it. This keeps the publication-appendix content in one
place so the Word and PDF outputs never drift.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..fitting.result import FitResult
from ..fitting.selection import ModelSelectionResult
from ..verification.kramers_kronig import KKResult
from ..verification.validation import CampaignValidation
from .bibliography import to_bibtex
from .formatting import format_measurement
from .manifest import ReproducibilityManifest
from .methods import methods_paragraph


@dataclass(frozen=True)
class ReportData:
    """Format-independent content of a publication-appendix report."""

    title: str
    validation_status: str
    methods: str
    parameter_rows: tuple[tuple[str, str], ...]  # (name, "value ± u")
    gof_rows: tuple[tuple[str, str], ...]  # (label, value)
    selection_table: str
    bibtex: str
    manifest_json: str
    figure_paths: tuple[str, ...] = ()
    extra_notes: tuple[str, ...] = field(default_factory=tuple)


def assemble_report(
    *,
    title: str,
    fit: FitResult,
    selection: ModelSelectionResult,
    manifest: ReproducibilityManifest,
    validation: CampaignValidation | None = None,
    kk: KKResult | None = None,
    n_repeats: int | None = None,
    n_repeats_total: int | None = None,
    n_excluded: int = 0,
    outlier_k: float | None = None,
    band_ghz: tuple[float, float] | None = None,
    figure_paths: tuple[str, ...] = (),
) -> ReportData:
    """Build :class:`ReportData` from the analysis objects."""
    methods = methods_paragraph(
        fit, selection=selection, kk=kk, validation=validation,
        n_repeats=n_repeats, n_repeats_total=n_repeats_total, n_excluded=n_excluded,
        outlier_k=outlier_k, band_ghz=band_ghz,
    )
    param_rows = tuple(
        (name, format_measurement(fit.params[name], fit.param_uncertainties.get(name, 0.0)))
        for name in fit.model.param_names
    )
    gof_rows = (
        ("R²", f"{fit.r_squared:.4f}"),
        ("reduced χ²", f"{fit.chi2_reduced:.3g}"),
        ("AICc", f"{fit.aicc:.4g}"),
        ("BIC", f"{fit.bic:.4g}"),
    )
    notes: list[str] = []
    for w in selection.warnings:
        notes.append(w)
    if kk is not None:
        notes.append(
            f"Kramers-Kronig relative ε' residual: {kk.residual_rms * 100:.1f}% "
            f"({'consistent' if kk.is_consistent else 'INCONSISTENT'})."
        )

    status = validation.status if validation else "NOT VALIDATED — no reference QC provided."
    return ReportData(
        title=title,
        validation_status=status,
        methods=methods,
        parameter_rows=param_rows,
        gof_rows=gof_rows,
        selection_table=selection.table(),
        bibtex=to_bibtex(fit.model, *(rf.result.model for rf in selection.ranking)),
        manifest_json=manifest.to_json(),
        figure_paths=figure_paths,
        extra_notes=tuple(notes),
    )
