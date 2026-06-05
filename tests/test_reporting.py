"""Tests for P5 reporting: formatting, manifest, methods, tables, bibliography, figures, reports."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from matplotlib.figure import Figure

from dielectric.fitting import fit_cole_cole, select_model
from dielectric.models.multipole import MultiPoleRelaxation
from dielectric.reporting import (
    ReproducibilityManifest,
    assemble_report,
    bode_figure,
    cole_cole_figure,
    format_measurement,
    methods_paragraph,
    parameter_table_csv,
    parameter_table_latex,
    render_docx,
    render_pdf,
    save_figure,
    to_bibtex,
)
from dielectric.spectrum import Spectrum

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
    render_docx(report, str(docx_path))
    render_pdf(report, str(pdf_path))
    assert docx_path.stat().st_size > 5000
    assert pdf_path.stat().st_size > 2000
