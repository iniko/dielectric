"""Assemble and render a campaign-level **batch comparison** report (PDF / Word / HTML).

Mirrors :mod:`dielectric.reporting.report` but for the "normal vs diseased — is there a
difference?" workflow: a per-batch parameter table plus, for each non-baseline batch, a
parameter-difference table (Δ, z-score, significance), a verdict, and overlay/difference figures.
Reuses the comparison numerics in :mod:`dielectric.comparison` so report and view never drift.
"""

from __future__ import annotations

import base64
import html
from dataclasses import dataclass
from pathlib import Path

from ..comparison import (
    ParameterDifference,
    compare_parameters,
    compare_spectra,
    dominant_relaxation,
    static_permittivity,
    static_permittivity_uncertainty,
)
from ..fitting.result import FitResult
from ..uncertainty.typea import TypeAResult
from .bibliography import to_bibtex
from .formatting import format_measurement
from .manifest import ReproducibilityManifest

_PARAM_LABEL = {"eps_static": "ε_s", "eps_inf": "ε∞", "tau_dominant": "τ", "sigma_dc": "σ_DC"}


@dataclass(frozen=True)
class DiffBlock:
    """One non-baseline batch compared against the baseline."""

    title: str
    verdict: str
    sig_band_pct: float
    rows: tuple[tuple[str, str, str, str, str, bool], ...]  # param, A, B, Δ, z, significant
    notes: tuple[str, ...]


@dataclass(frozen=True)
class ComparisonReportData:
    """Format-independent content of a batch-comparison report."""

    title: str
    baseline: str
    batch_header: tuple[str, ...]
    batch_rows: tuple[tuple[str, ...], ...]
    diffs: tuple[DiffBlock, ...]
    bibtex: str
    manifest_json: str
    figure_paths: tuple[str, ...] = ()


# A batch is identified by (label, fit, Type A result).
Batch = tuple[str, FitResult, TypeAResult]


def _scaled(name: str) -> float:
    return 1e12 if name == "tau_dominant" else 1.0  # τ shown in ps


def _fmt_value(name: str, value: float, u: float) -> str:
    s = _scaled(name)
    text = format_measurement(value * s, u * s)
    return f"{text} ps" if name == "tau_dominant" else text


def _batch_param_cell(name: str, fit: FitResult) -> str:
    if name == "eps_static":
        return _fmt_value(
            name, static_permittivity(fit.model), static_permittivity_uncertainty(fit)
        )
    if name == "tau_dominant":
        tau, u = dominant_relaxation(fit)
        return _fmt_value(name, tau, u)
    if name in fit.params:
        return _fmt_value(name, fit.params[name], fit.param_uncertainties.get(name, 0.0))
    return "—"


def _diff_block(label: str, fit: FitResult, ta: TypeAResult, base: Batch) -> DiffBlock:
    _, base_fit, base_ta = base
    pdiffs: list[ParameterDifference] = compare_parameters(fit, base_fit)
    rows = tuple(
        (
            _PARAM_LABEL.get(p.name, p.name),
            _fmt_value(p.name, p.a, p.ua),
            _fmt_value(p.name, p.b, p.ub),
            f"{p.delta * _scaled(p.name):+.3g}",
            f"{p.z:.2f}" if p.z == p.z else "—",  # NaN guard
            p.significant,
        )
        for p in pdiffs
    )
    sd = compare_spectra(ta.mean, base_ta.mean)
    band_pct = 100.0 * float(sd.significant_eps.mean()) if sd.significant_eps.size else 0.0
    sig_names = [_PARAM_LABEL.get(p.name, p.name) for p in pdiffs if p.significant]
    if sig_names:
        verdict = f"Differs from baseline: {', '.join(sig_names)} (z ≥ 1.96)."
    else:
        verdict = "No parameter differs from the baseline at z ≥ 1.96."
    verdict += f" ε′ separates over {band_pct:.0f}% of the band."
    return DiffBlock(
        title=f"{label} − {base[0]}", verdict=verdict, sig_band_pct=band_pct,
        rows=rows, notes=sd.notes,
    )


def assemble_comparison_report(
    *,
    title: str,
    baseline_label: str,
    batches: list[Batch],
    manifest: ReproducibilityManifest,
    figure_paths: tuple[str, ...] = (),
) -> ComparisonReportData:
    """Build :class:`ComparisonReportData` from the fitted batches (one is the baseline)."""
    base = next((b for b in batches if b[0] == baseline_label), batches[0])
    labels = [label for label, _, _ in batches]
    header = ("parameter", *labels)

    def row(param_label: str, cell: object) -> tuple[str, ...]:
        return (param_label, *[str(cell(b)) for b in batches])  # type: ignore[operator]

    batch_rows = (
        row("model", lambda b: type(b[1].model).__name__),
        row("ε_s", lambda b: _batch_param_cell("eps_static", b[1])),
        row("ε∞", lambda b: _batch_param_cell("eps_inf", b[1])),
        row("τ", lambda b: _batch_param_cell("tau_dominant", b[1])),
        row("σ_DC", lambda b: _batch_param_cell("sigma_dc", b[1])),
        row(
            "repeats used",
            lambda b: f"{b[2].n_repeats_used}/{b[2].n_repeats_total}"
            + (f" ({len(b[2].excluded_indices)} excl.)" if b[2].excluded_indices else ""),
        ),
    )
    diffs = tuple(
        _diff_block(label, fit, ta, base)
        for (label, fit, ta) in batches
        if label != base[0]
    )
    bibtex = to_bibtex(*[fit.model for _, fit, _ in batches])
    return ComparisonReportData(
        title=title, baseline=base[0], batch_header=header, batch_rows=batch_rows,
        diffs=diffs, bibtex=bibtex, manifest_json=manifest.to_json(), figure_paths=figure_paths,
    )


# -- renderers ----------------------------------------------------------------------------------


def write_comparison_pdf(pdf: object, report: ComparisonReportData) -> None:
    """Write the comparison sections into an existing FPDF document."""
    from .report_pdf import _ascii

    pdf.add_page()  # type: ignore[attr-defined]

    def cell(text: str, h: float) -> None:
        pdf.multi_cell(0, h, _ascii(text), new_x="LMARGIN", new_y="NEXT")  # type: ignore[attr-defined]

    pdf.set_font("Helvetica", "B", 16)  # type: ignore[attr-defined]
    cell(report.title, 9)
    pdf.set_font("Helvetica", "", 10)  # type: ignore[attr-defined]
    cell(f"Baseline batch: {report.baseline}", 6)
    pdf.ln(1)  # type: ignore[attr-defined]

    pdf.set_font("Helvetica", "B", 13)  # type: ignore[attr-defined]
    cell("Batch summary", 7)
    pdf.set_font("Courier", "", 8)  # type: ignore[attr-defined]
    cell(" | ".join(report.batch_header), 4)
    for r in report.batch_rows:
        cell(" | ".join(r), 4)
    pdf.ln(1)  # type: ignore[attr-defined]

    for blk in report.diffs:
        pdf.set_font("Helvetica", "B", 12)  # type: ignore[attr-defined]
        cell(blk.title, 6)
        pdf.set_font("Helvetica", "", 10)  # type: ignore[attr-defined]
        cell(blk.verdict, 5)
        pdf.set_font("Courier", "", 8)  # type: ignore[attr-defined]
        cell(f"{'param':<8}{'A':>16}{'baseline':>16}{'Δ':>12}{'z':>8}", 4)
        for pname, a, b, d, z, sig in blk.rows:
            mark = " *" if sig else ""
            cell(f"{pname:<8}{a:>16}{b:>16}{d:>12}{z:>8}{mark}", 4)
        for note in blk.notes:
            pdf.set_font("Helvetica", "", 9)  # type: ignore[attr-defined]
            cell(f"- {note}", 4)
        pdf.ln(1)  # type: ignore[attr-defined]

    for fig_path in report.figure_paths:
        if Path(fig_path).exists():
            pdf.add_page()  # type: ignore[attr-defined]
            pdf.image(fig_path, w=180)  # type: ignore[attr-defined]

    pdf.add_page()  # type: ignore[attr-defined]
    pdf.set_font("Helvetica", "B", 13)  # type: ignore[attr-defined]
    cell("References (BibTeX)", 7)
    pdf.set_font("Courier", "", 8)  # type: ignore[attr-defined]
    cell(report.bibtex, 4)
    pdf.set_font("Helvetica", "B", 13)  # type: ignore[attr-defined]
    cell("Reproducibility manifest", 7)
    pdf.set_font("Courier", "", 8)  # type: ignore[attr-defined]
    cell(report.manifest_json, 4)


def render_comparison_pdf(report: ComparisonReportData, path: str | Path) -> None:
    from .report_pdf import new_pdf

    pdf = new_pdf()
    write_comparison_pdf(pdf, report)
    pdf.output(str(path))  # type: ignore[attr-defined]


def write_comparison_docx(document: object, report: ComparisonReportData, docx: object) -> None:
    """Write the comparison sections into an existing Word document."""
    document.add_heading(report.title, level=0)  # type: ignore[attr-defined]
    document.add_paragraph(f"Baseline batch: {report.baseline}")  # type: ignore[attr-defined]

    document.add_heading("Batch summary", level=1)  # type: ignore[attr-defined]
    table = document.add_table(rows=1, cols=len(report.batch_header))  # type: ignore[attr-defined]
    table.style = "Light Grid Accent 1"
    for j, h in enumerate(report.batch_header):
        table.rows[0].cells[j].text = h
    for r in report.batch_rows:
        cells = table.add_row().cells
        for j, val in enumerate(r):
            cells[j].text = val

    for blk in report.diffs:
        document.add_heading(blk.title, level=1)  # type: ignore[attr-defined]
        document.add_paragraph(blk.verdict)  # type: ignore[attr-defined]
        t = document.add_table(rows=1, cols=5)  # type: ignore[attr-defined]
        t.style = "Light Grid Accent 1"
        for j, h in enumerate(("parameter", "A", "baseline", "Δ", "z")):
            t.rows[0].cells[j].text = h
        for pname, a, b, d, z, sig in blk.rows:
            cells = t.add_row().cells
            for j, val in enumerate((pname + (" *" if sig else ""), a, b, d, z)):
                cells[j].text = val
        for note in blk.notes:
            document.add_paragraph(note, style="List Bullet")  # type: ignore[attr-defined]

    for fig_path in report.figure_paths:
        if Path(fig_path).exists():
            document.add_picture(fig_path, width=docx.shared.Inches(6.0))  # type: ignore[attr-defined]

    document.add_heading("References (BibTeX)", level=1)  # type: ignore[attr-defined]
    document.add_paragraph(report.bibtex, style="No Spacing")  # type: ignore[attr-defined]
    document.add_heading("Reproducibility manifest", level=1)  # type: ignore[attr-defined]
    document.add_paragraph(report.manifest_json, style="No Spacing")  # type: ignore[attr-defined]


def render_comparison_docx(report: ComparisonReportData, path: str | Path) -> None:
    from .report_docx import new_docx

    document, docx = new_docx()
    write_comparison_docx(document, report, docx)
    document.save(str(path))  # type: ignore[attr-defined]


def _embed(fig_path: str) -> str:
    p = Path(fig_path)
    if not p.exists():
        return ""
    data = base64.b64encode(p.read_bytes()).decode("ascii")
    return f'<img class="fig" src="data:image/png;base64,{data}" alt="{html.escape(p.stem)}" />'


def _html_table(header: tuple[str, ...], rows: tuple[tuple[str, ...], ...]) -> str:
    head = "".join(f"<th>{html.escape(h)}</th>" for h in header)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in r) + "</tr>" for r in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


_HTML_CSS = """
body { font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
       max-width: 900px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }
h1 { font-size: 1.7rem; } h2 { font-size: 1.15rem; border-bottom: 1px solid #e5e5e5;
     padding-bottom: .2rem; margin-top: 1.8rem; }
table { border-collapse: collapse; margin: .5rem 0; font-variant-numeric: tabular-nums; }
td, th { padding: .25rem .7rem; border-bottom: 1px solid #eee; text-align: left; }
.verdict { background: #fcefe7; color: #9a3b12; padding: .5rem .75rem; border-radius: 6px; }
.fig { max-width: 100%; margin: .75rem 0; border: 1px solid #eee; border-radius: 6px; }
pre { background: #f6f8fa; border: 1px solid #e5e7eb; border-radius: 6px; padding: .75rem;
      overflow-x: auto; font: 12px/1.4 ui-monospace, Menlo, monospace; }
"""


def comparison_body_html(report: ComparisonReportData, *, title_tag: str = "h1") -> str:
    """The comparison content (heading + sections), reusable inside a combined document."""
    diff_html = ""
    for blk in report.diffs:
        drows = tuple(
            (p + (" *" if sig else ""), a, b, d, z) for (p, a, b, d, z, sig) in blk.rows
        )
        diff_html += (
            f"<h2>{html.escape(blk.title)}</h2>"
            f"<p class='verdict'>{html.escape(blk.verdict)}</p>"
            + _html_table(("parameter", "A", "baseline", "Δ", "z"), drows)
            + "".join(f"<p>⚠ {html.escape(n)}</p>" for n in blk.notes)
        )
    figures = "".join(_embed(fp) for fp in report.figure_paths)
    return f"""<{title_tag}>{html.escape(report.title)}</{title_tag}>
<p>Baseline batch: <b>{html.escape(report.baseline)}</b></p>
<h2>Batch summary</h2>
{_html_table(report.batch_header, report.batch_rows)}
{diff_html}
<h2>Figures</h2>
{figures or "<p>(no figures)</p>"}
<h2>References (BibTeX)</h2><pre>{html.escape(report.bibtex)}</pre>
<h2>Reproducibility manifest</h2><pre>{html.escape(report.manifest_json)}</pre>
"""


def render_comparison_html(report: ComparisonReportData, path: str | Path) -> None:
    from .report_html import html_document

    Path(path).write_text(
        html_document(report.title, comparison_body_html(report)), encoding="utf-8"
    )
