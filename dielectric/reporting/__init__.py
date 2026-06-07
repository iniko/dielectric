"""Publication-ready reporting: formatting, tables, figures, methods prose, manifest, reports."""

from __future__ import annotations

from .bibliography import collect_provenances, to_bibtex
from .campaign_report import (
    render_campaign_docx,
    render_campaign_html,
    render_campaign_pdf,
)
from .comparison_report import (
    ComparisonReportData,
    assemble_comparison_report,
    render_comparison_docx,
    render_comparison_html,
    render_comparison_pdf,
)
from .figures import (
    bode_figure,
    cole_cole_figure,
    comparison_overlay_figure,
    difference_figure,
    save_figure,
)
from .formatting import format_measurement, format_param
from .manifest import ReproducibilityManifest
from .methods import methods_paragraph
from .report import ReportData, assemble_report
from .report_docx import render_docx
from .report_html import render_html
from .report_pdf import render_pdf
from .tables import (
    parameter_table_csv,
    parameter_table_latex,
    selection_table_csv,
)

__all__ = [
    "ComparisonReportData",
    "ReportData",
    "ReproducibilityManifest",
    "assemble_comparison_report",
    "assemble_report",
    "bode_figure",
    "cole_cole_figure",
    "collect_provenances",
    "comparison_overlay_figure",
    "difference_figure",
    "format_measurement",
    "format_param",
    "methods_paragraph",
    "parameter_table_csv",
    "parameter_table_latex",
    "render_campaign_docx",
    "render_campaign_html",
    "render_campaign_pdf",
    "render_comparison_docx",
    "render_comparison_html",
    "render_comparison_pdf",
    "render_docx",
    "render_html",
    "render_pdf",
    "save_figure",
    "selection_table_csv",
    "to_bibtex",
]
