"""Tests for P7: the CLI end-to-end and the MATLAB-port reference cross-check."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from dielectric.cli import main
from dielectric.models.multipole import MultiPoleRelaxation

# A small subset of the measurement repeats keeps the integration test fast.
MEAS = "data/h02s19m0[1-5].csv"
VAL = "data/h02v0[1-5].csv"


def test_cli_analyze_writes_artifacts(tmp_path: Path) -> None:
    rc = main(["analyze", "--measure", MEAS, "--out", str(tmp_path), "--no-report"])
    assert rc == 0
    produced = {p.name for p in tmp_path.iterdir()}
    assert any(n.endswith("_bode.png") for n in produced)
    assert any(n.endswith("_params.tex") for n in produced)
    assert any(n.endswith("_methods.txt") for n in produced)
    assert any(n.endswith("_manifest.json") for n in produced)
    # the sanitized id has no glob characters
    assert not any("*" in n for n in produced)


def test_cli_with_validation_and_report(tmp_path: Path) -> None:
    rc = main([
        "analyze", "--measure", MEAS, "--validate", VAL, "--reference", "saline",
        "--molarity", "0.154", "--temperature", "25", "--out", str(tmp_path),
    ])
    assert rc == 0
    methods = next(tmp_path.glob("*_methods.txt")).read_text()
    assert "validated" in methods.lower()
    assert any(p.name.endswith("_report.pdf") for p in tmp_path.iterdir())
    assert any(p.name.endswith("_report.docx") for p in tmp_path.iterdir())


def test_cli_model_override(tmp_path: Path) -> None:
    rc = main([
        "analyze", "--measure", MEAS, "--poles", "2", "--out", str(tmp_path), "--no-report",
    ])
    assert rc == 0
    manifest = next(tmp_path.glob("*_manifest.json")).read_text()
    assert "MultiPoleRelaxation" in manifest


def test_matlab_reference_vector_matches_python_core() -> None:
    """The reference vector hard-coded in matlab/run_tests.m must match the Python evaluator."""
    f = np.array([2e8, 1e9, 5e9, 2e10])
    eps = MultiPoleRelaxation(5.0, ((52.0, 8e-12, 0.1),), sigma_dc=0.7).epsilon(f)
    expected = np.array([
        56.858016 - 63.726489j,
        56.229526 - 15.976496j,
        51.310630 - 15.144748j,
        30.892846 - 22.835008j,
    ])
    np.testing.assert_allclose(eps, expected, atol=1e-4)
