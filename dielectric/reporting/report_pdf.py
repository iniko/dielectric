"""Render a :class:`ReportData` to a PDF publication appendix (requires the ``report`` extra).

Uses fpdf2 (pure Python, no system libraries) so PDF export works anywhere the toolkit installs.
"""

from __future__ import annotations

from pathlib import Path

from .report import ReportData


def _require_fpdf() -> object:
    try:
        from fpdf import FPDF
    except ImportError as exc:  # pragma: no cover - exercised only without the optional dep
        raise ImportError(
            "PDF reports need fpdf2; install with `pip install dielectric[report]`."
        ) from exc
    return FPDF


def _ascii(text: str) -> str:
    """fpdf2 core fonts are latin-1; replace the few unicode symbols we emit."""
    replacements = {
        "ε": "eps", "ω": "omega", "τ": "tau", "α": "alpha", "β": "beta", "σ": "sigma",
        "χ": "chi", "²": "^2", "±": "+/-", "∞": "inf", "Δ": "d", "°": "deg",
        "′": "'", "″": "''", "–": "-", "—": "-", "→": "->", "≈": "~", "·": ".",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text.encode("latin-1", "replace").decode("latin-1")


def render_pdf(report: ReportData, path: str | Path) -> None:
    """Write ``report`` as a PDF publication appendix."""
    fpdf_cls = _require_fpdf()
    pdf = fpdf_cls()  # type: ignore[operator]
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    def cell(text: str, h: float) -> None:
        # new_x="LMARGIN"/new_y="NEXT" returns the cursor to the left margin on the next line, so
        # the following full-width multi_cell does not get zero available width.
        pdf.multi_cell(0, h, _ascii(text), new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "B", 16)
    cell(report.title, 9)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(150, 0, 0)
    cell(report.validation_status, 7)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)

    def heading(text: str) -> None:
        pdf.set_font("Helvetica", "B", 13)
        cell(text, 7)

    def body(text: str) -> None:
        pdf.set_font("Helvetica", "", 10)
        cell(text, 5)
        pdf.ln(1)

    def mono(text: str) -> None:
        pdf.set_font("Courier", "", 8)
        cell(text, 4)
        pdf.ln(1)

    heading("Methods")
    body(report.methods)

    heading("Fitted parameters")
    for name, value in (*report.parameter_rows, *report.gof_rows):
        body(f"  {name} = {value}")

    heading("Model selection")
    mono(report.selection_table)
    for note in report.extra_notes:
        body(f"- {note}")

    for fig_path in report.figure_paths:
        if Path(fig_path).exists():
            pdf.add_page()
            pdf.image(fig_path, w=180)

    pdf.add_page()
    heading("References (BibTeX)")
    mono(report.bibtex)
    heading("Reproducibility manifest")
    mono(report.manifest_json)

    pdf.output(str(path))
