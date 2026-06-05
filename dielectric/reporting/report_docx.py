"""Render a :class:`ReportData` to a Word publication appendix (requires the ``report`` extra)."""

from __future__ import annotations

from pathlib import Path

from .report import ReportData


def _require_docx() -> object:
    try:
        import docx
    except ImportError as exc:  # pragma: no cover - exercised only without the optional dep
        raise ImportError(
            "DOCX reports need python-docx; install with `pip install dielectric[report]`."
        ) from exc
    return docx


def render_docx(report: ReportData, path: str | Path) -> None:
    """Write ``report`` as a .docx publication appendix."""
    docx = _require_docx()
    document = docx.Document()  # type: ignore[attr-defined]

    document.add_heading(report.title, level=0)
    document.add_paragraph(report.validation_status).runs[0].bold = True

    document.add_heading("Methods", level=1)
    document.add_paragraph(report.methods)

    document.add_heading("Fitted parameters", level=1)
    table = document.add_table(rows=1, cols=2)
    table.style = "Light Grid Accent 1"
    table.rows[0].cells[0].text = "Parameter"
    table.rows[0].cells[1].text = "Value"
    for name, value in report.parameter_rows:
        row = table.add_row().cells
        row[0].text = name
        row[1].text = value
    for label, value in report.gof_rows:
        row = table.add_row().cells
        row[0].text = label
        row[1].text = value

    document.add_heading("Model selection", level=1)
    sel_para = document.add_paragraph(report.selection_table, style="No Spacing")
    sel_para.runs[0].font.name = "Courier New"
    for note in report.extra_notes:
        document.add_paragraph(note, style="List Bullet")

    for fig_path in report.figure_paths:
        if Path(fig_path).exists():
            document.add_picture(fig_path, width=docx.shared.Inches(6.0))  # type: ignore[attr-defined]

    document.add_heading("References (BibTeX)", level=1)
    document.add_paragraph(report.bibtex, style="No Spacing")

    document.add_heading("Reproducibility manifest", level=1)
    document.add_paragraph(report.manifest_json, style="No Spacing")

    document.save(str(path))
