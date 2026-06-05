"""Publication-ready reporting: formatting, tables, figures, methods prose, manifest, reports."""

from __future__ import annotations

from .bibliography import collect_provenances, to_bibtex
from .figures import bode_figure, cole_cole_figure, save_figure
from .formatting import format_measurement, format_param
from .manifest import ReproducibilityManifest
from .methods import methods_paragraph
from .report import ReportData, assemble_report
from .report_docx import render_docx
from .report_pdf import render_pdf
from .tables import (
    parameter_table_csv,
    parameter_table_latex,
    selection_table_csv,
)

__all__ = [
    "ReportData",
    "ReproducibilityManifest",
    "assemble_report",
    "bode_figure",
    "cole_cole_figure",
    "collect_provenances",
    "format_measurement",
    "format_param",
    "methods_paragraph",
    "parameter_table_csv",
    "parameter_table_latex",
    "render_docx",
    "render_pdf",
    "save_figure",
    "selection_table_csv",
    "to_bibtex",
]
