"""Combine the per-batch reports and the batch-comparison into one **campaign report** document.

Reuses the section-writers from the per-sample (:mod:`report_pdf`/`report_docx`/`report_html`) and
comparison (:mod:`comparison_report`) renderers so the combined file never drifts from the
standalone ones. One file (PDF/Word/HTML): every batch's analysis, then the comparison section.
"""

from __future__ import annotations

from pathlib import Path

from .comparison_report import (
    ComparisonReportData,
    comparison_body_html,
    write_comparison_docx,
    write_comparison_pdf,
)
from .report import ReportData
from .report_docx import new_docx, write_report_docx
from .report_html import html_document, report_body_html
from .report_pdf import new_pdf, write_report_pdf


def render_campaign_html(
    title: str,
    samples: list[ReportData],
    comparison: ComparisonReportData | None,
    path: str | Path,
) -> None:
    parts = [report_body_html(s) for s in samples]
    if comparison is not None:
        parts.append(comparison_body_html(comparison))
    body = "\n<hr style='margin:2.5rem 0;border:none;border-top:2px solid #e5e5e5' />\n".join(parts)
    Path(path).write_text(html_document(title, body), encoding="utf-8")


def render_campaign_pdf(
    title: str,
    samples: list[ReportData],
    comparison: ComparisonReportData | None,
    path: str | Path,
) -> None:
    pdf = new_pdf()
    for s in samples:
        write_report_pdf(pdf, s)
    if comparison is not None:
        write_comparison_pdf(pdf, comparison)
    pdf.output(str(path))  # type: ignore[attr-defined]


def render_campaign_docx(
    title: str,
    samples: list[ReportData],
    comparison: ComparisonReportData | None,
    path: str | Path,
) -> None:
    document, docx = new_docx()
    for i, s in enumerate(samples):
        if i > 0:
            document.add_page_break()  # type: ignore[attr-defined]
        write_report_docx(document, s, docx)
    if comparison is not None:
        document.add_page_break()  # type: ignore[attr-defined]
        write_comparison_docx(document, comparison, docx)
    document.save(str(path))  # type: ignore[attr-defined]
