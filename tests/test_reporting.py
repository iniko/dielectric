"""Tests for P5 reporting: formatting, manifest, methods, tables, bibliography, figures, reports."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from matplotlib.figure import Figure

from dielectric.comparison import compare_spectra
from dielectric.fitting import fit_cole_cole, fit_cole_cole_conductivity, select_model
from dielectric.models.multipole import MultiPoleRelaxation
from dielectric.reporting import (
    ReproducibilityManifest,
    assemble_comparison_report,
    assemble_report,
    bode_figure,
    cole_cole_figure,
    comparison_overlay_figure,
    difference_figure,
    format_measurement,
    methods_paragraph,
    parameter_table_csv,
    parameter_table_latex,
    render_campaign_docx,
    render_campaign_html,
    render_campaign_pdf,
    render_comparison_docx,
    render_comparison_html,
    render_comparison_pdf,
    render_docx,
    render_html,
    render_pdf,
    save_figure,
    to_bibtex,
)
from dielectric.spectrum import Spectrum
from dielectric.uncertainty import combine_repeats

F = np.geomspace(2e8, 2e10, 101)


def _fit():
    truth = MultiPoleRelaxation(5.0, ((52.0, 8e-12, 0.05),), sigma_dc=0.7)
    rng = np.random.default_rng(1)
    eps = truth.epsilon(F) + rng.normal(0, 0.02, F.size) + 1j * rng.normal(0, 0.02, F.size)
    return Spectrum(F, eps), fit_cole_cole(Spectrum(F, eps))


# -- formatting (GUM / PDG) --------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,unc,expected",
    [
        (58.17, 0.67, "58.2 ± 0.7"),
        (0.793, 0.020, "0.793 ± 0.020"),
        (4.234, 0.27, "4.23 ± 0.27"),
        (8.01e-12, 3.0e-13, "(8.01 ± 0.30)e-12"),
    ],
)
def test_format_measurement_pdg(value: float, unc: float, expected: str) -> None:
    assert format_measurement(value, unc) == expected


def test_format_measurement_zero_uncertainty() -> None:
    assert "±" not in format_measurement(4.2, 0.0)


# -- manifest ----------------------------------------------------------------------------------


def test_manifest_roundtrip_and_hash() -> None:
    _, fit = _fit()
    m = ReproducibilityManifest.from_fit(fit, timestamp="2026-06-05T00:00:00Z", data_source="x.csv")
    assert m.data_hash == fit.data_hash
    assert m.library_version
    import json

    parsed = json.loads(m.to_json())
    assert parsed["model"] == "ColeCole"
    assert parsed["timestamp"] == "2026-06-05T00:00:00Z"


# -- methods paragraph -------------------------------------------------------------------------


def test_methods_paragraph_mentions_key_elements() -> None:
    _, fit = _fit()
    text = methods_paragraph(fit, n_repeats=15, band_ghz=(0.2, 20.0))
    assert "non-linear least squares" in text
    assert "R²" in text
    assert "15 repeat" in text
    assert "dielectric toolkit" in text


def test_methods_paragraph_override_phrased_as_despite() -> None:
    """An analyst override that ranks worse must read "chosen despite ΔAICc = X in favour of",
    never "preferred over ... by ΔAICc = -X" (which endorses a worse fit)."""
    import warnings as _w

    from dielectric.fitting import select_model

    spectrum, _ = _fit()
    with _w.catch_warnings():
        _w.simplefilter("ignore")
        sel = select_model(spectrum, force_model="Debye")  # far worse than the recommendation
    text = methods_paragraph(sel.chosen.result, selection=sel, n_repeats=15)
    assert "chosen despite ΔAICc = " in text
    assert "by ΔAICc = -" not in text


# -- tables ------------------------------------------------------------------------------------


def test_latex_table_has_pm_and_caption() -> None:
    _, fit = _fit()
    tex = parameter_table_latex(fit, caption="My caption")
    assert r"\pm" in tex
    assert "My caption" in tex
    assert r"\begin{tabular}" in tex


def test_csv_table_parses() -> None:
    import csv
    import io

    _, fit = _fit()
    rows = list(csv.reader(io.StringIO(parameter_table_csv(fit))))
    assert rows[0] == ["parameter", "value", "standard_uncertainty", "formatted"]
    assert any(r and r[0] == "tau" for r in rows)


# -- bibliography ------------------------------------------------------------------------------


def test_bibtex_collects_model_provenance() -> None:
    _, fit = _fit()
    bib = to_bibtex(fit.model)
    assert "@" in bib
    assert "Cole" in bib


# -- figures -----------------------------------------------------------------------------------


def test_figures_render_and_save(tmp_path: Path) -> None:
    s, fit = _fit()
    for fig_fn, name in ((bode_figure, "bode"), (cole_cole_figure, "cole")):
        fig = fig_fn(s, fit)
        assert isinstance(fig, Figure)
        out = tmp_path / f"{name}.png"
        save_figure(fig, str(out))
        assert out.exists() and out.stat().st_size > 1000


# -- end-to-end report -------------------------------------------------------------------------


def _comparison_batch(eps_s: float, seed: int):
    truth = MultiPoleRelaxation(5.0, ((eps_s - 5.0, 8e-12, 0.05),), sigma_dc=0.7)
    rng = np.random.default_rng(seed)
    base = truth.epsilon(F)
    reps = tuple(
        Spectrum(F, base + rng.normal(0, 0.03, F.size) + 1j * rng.normal(0, 0.03, F.size))
        for _ in range(8)
    )
    ta = combine_repeats(reps)
    return ta, fit_cole_cole_conductivity(ta.mean)


def test_comparison_report_assembles_and_renders(tmp_path: Path) -> None:
    ta_a, fit_a = _comparison_batch(70.0, seed=1)
    ta_b, fit_b = _comparison_batch(57.0, seed=2)
    batches = [("normal", fit_a, ta_a), ("diseased", fit_b, ta_b)]

    over = tmp_path / "overlay.png"
    save_figure(comparison_overlay_figure([(lbl, ta.mean) for lbl, _f, ta in batches]), str(over))
    diff = tmp_path / "diff.png"
    save_figure(difference_figure(compare_spectra(ta_b.mean, ta_a.mean)), str(diff))

    manifest = ReproducibilityManifest.from_fit(fit_a, timestamp="2026-06-06T00:00:00Z")
    report = assemble_comparison_report(
        title="Compare", baseline_label="normal", batches=batches, manifest=manifest,
        figure_paths=(str(over), str(diff)),
    )
    assert report.baseline == "normal"
    assert report.batch_header == ("parameter", "normal", "diseased")
    assert len(report.diffs) == 1
    assert "separates over" in report.diffs[0].verdict

    pdf_path, docx_path, html_path = tmp_path / "c.pdf", tmp_path / "c.docx", tmp_path / "c.html"
    render_comparison_pdf(report, str(pdf_path))
    render_comparison_docx(report, str(docx_path))
    render_comparison_html(report, str(html_path))
    assert pdf_path.stat().st_size > 2000
    assert docx_path.stat().st_size > 5000
    html = html_path.read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>") and "data:image/png;base64," in html
    assert "diseased" in html


def test_campaign_report_combines_samples_and_comparison(tmp_path: Path) -> None:
    batches = [("normal", *_comparison_batch(70.0, seed=1)),
               ("diseased", *_comparison_batch(57.0, seed=2))]
    samples = []
    fitted: list[tuple[str, object, object]] = []
    for label, ta, _f in batches:
        sel = select_model(ta.mean)
        fit = sel.chosen.result
        man = ReproducibilityManifest.from_fit(fit, timestamp="2026-06-07T00:00:00Z")
        fig = tmp_path / f"{label}.png"
        save_figure(bode_figure(ta.mean, fit), str(fig))
        samples.append(assemble_report(
            title=f"Dielectric analysis: {label}", fit=fit, selection=sel, manifest=man,
            figure_paths=(str(fig),),
        ))
        fitted.append((label, fit, ta))

    over = tmp_path / "overlay.png"
    overlay = comparison_overlay_figure([(lbl, ta.mean) for lbl, ta, _fit in batches])
    save_figure(overlay, str(over))
    man2 = ReproducibilityManifest.from_fit(fitted[0][1], timestamp="2026-06-07T00:00:00Z")
    comp = assemble_comparison_report(
        title="Batch comparison", baseline_label="normal", batches=fitted, manifest=man2,
        figure_paths=(str(over),),
    )

    for fmt, render in (
        ("pdf", render_campaign_pdf),
        ("docx", render_campaign_docx),
        ("html", render_campaign_html),
    ):
        p = tmp_path / f"campaign.{fmt}"
        render("Campaign report", samples, comp, str(p))
        assert p.stat().st_size > 2000
    html = (tmp_path / "campaign.html").read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>") and "data:image/png;base64," in html
    assert "normal" in html and "diseased" in html  # both batches present
    assert "separates over" in html  # the comparison verdict is included


def test_methods_paragraph_discloses_exclusion() -> None:
    _s, fit = _fit()
    disclosed = methods_paragraph(
        fit, n_repeats=11, n_repeats_total=12, n_excluded=1, outlier_k=3.5, band_ghz=(0.2, 20.0)
    )
    assert "excluding 1 of 12" in disclosed
    assert "Hampel" in disclosed and "k = 3.5" in disclosed
    kept_all = methods_paragraph(
        fit, n_repeats=12, n_repeats_total=12, n_excluded=0, outlier_k=None, band_ghz=(0.2, 20.0)
    )
    assert "no outlier screening applied" in kept_all


def test_assemble_and_render_reports(tmp_path: Path) -> None:
    s, _ = _fit()
    sel = select_model(s)
    fit = sel.chosen.result
    manifest = ReproducibilityManifest.from_fit(fit, timestamp="2026-06-05T00:00:00Z")
    fig_path = tmp_path / "bode.png"
    save_figure(bode_figure(s, fit), str(fig_path))
    report = assemble_report(
        title="Test", fit=fit, selection=sel, manifest=manifest, figure_paths=(str(fig_path),)
    )
    docx_path = tmp_path / "r.docx"
    pdf_path = tmp_path / "r.pdf"
    html_path = tmp_path / "r.html"
    render_docx(report, str(docx_path))
    render_pdf(report, str(pdf_path))
    render_html(report, str(html_path))
    assert docx_path.stat().st_size > 5000
    assert pdf_path.stat().st_size > 2000
    html = html_path.read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>")
    assert "Test" in html  # the title
    assert "data:image/png;base64," in html  # the figure is embedded, not linked
    assert "<script" not in html.lower()  # self-contained, no external/dynamic content
