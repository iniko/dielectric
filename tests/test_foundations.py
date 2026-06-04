"""Tests for P0 foundations: units, sign convention, Spectrum, quality pass."""

from __future__ import annotations

import numpy as np
import pytest

import dielectric as d
from dielectric.constants import EPSILON_0
from dielectric.convention import ConventionWarning, detect_and_correct_imaginary
from dielectric.units import (
    FrequencyUnit,
    PermittivityKind,
    angular_frequency,
    celsius_to_kelvin,
    to_hz,
    to_relative_permittivity,
)


def _cole_cole(f: np.ndarray) -> np.ndarray:
    """A simple lossy spectrum in internal convention (Im < 0)."""
    return 5 + 50 / (1 + 1j * 2 * np.pi * f * 8e-12)


# -- units -------------------------------------------------------------------------------------


def test_frequency_unit_conversion() -> None:
    assert to_hz(np.array([1.0]), FrequencyUnit.GHZ)[0] == pytest.approx(1e9)
    assert to_hz(np.array([200.0]), FrequencyUnit.MHZ)[0] == pytest.approx(2e8)


def test_absolute_to_relative_permittivity() -> None:
    abs_vals = np.array([78.0]) * EPSILON_0
    rel = to_relative_permittivity(abs_vals, PermittivityKind.ABSOLUTE)
    assert rel[0] == pytest.approx(78.0)
    # relative passes through unchanged
    assert to_relative_permittivity(np.array([78.0]), PermittivityKind.RELATIVE)[0] == 78.0


def test_angular_frequency_and_temperature() -> None:
    assert angular_frequency(np.array([1.0]))[0] == pytest.approx(2 * np.pi)
    assert celsius_to_kelvin(25.0) == pytest.approx(298.15)


# -- sign convention ---------------------------------------------------------------------------


def test_positive_loss_is_negated_with_warning() -> None:
    raw = np.array([77.1, 73.0, 50.0, 20.4])  # Agilent-style positive loss
    with pytest.warns(ConventionWarning):
        corrected, warning = detect_and_correct_imaginary(raw, source="h02")
    assert warning is not None
    assert np.median(corrected) < 0  # now internal convention


def test_negative_loss_passes_through_silently() -> None:
    raw = np.array([-77.1, -73.0, -20.4])  # already internal convention
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error")  # any warning would fail the test
        corrected, warning = detect_and_correct_imaginary(raw)
    assert warning is None
    np.testing.assert_array_equal(corrected, raw)


# -- Spectrum ----------------------------------------------------------------------------------


def test_spectrum_validation_rejects_bad_input() -> None:
    f = np.geomspace(2e8, 2e10, 10)
    with pytest.raises(ValueError, match="length mismatch"):
        d.Spectrum(f, np.ones(9, dtype=complex))
    with pytest.raises(ValueError, match="strictly increasing"):
        d.Spectrum(f[::-1], _cole_cole(f))


def test_spectrum_derived_quantities() -> None:
    f = np.geomspace(2e8, 2e10, 101)
    s = d.Spectrum(f, _cole_cole(f))
    # loss is positive (display convention) while internal imag is negative
    assert np.all(s.loss >= 0)
    assert np.all(s.eps_imag <= 0)
    # σ_eff = -ω ε0 Im(ε*) ≥ 0 for a passive medium
    assert np.all(s.effective_conductivity >= 0)
    assert s.band_hz == (pytest.approx(2e8), pytest.approx(2e10))


def test_quality_pass_clean_vs_spike() -> None:
    f = np.geomspace(2e8, 2e10, 101)
    eps = _cole_cole(f)
    clean = d.Spectrum(f, eps).quality_report()
    assert clean.n_outliers == 0
    assert clean.ok

    spiked = eps.copy()
    spiked[40] *= 1.15
    rep = d.Spectrum(f, spiked).quality_report()
    assert 40 in rep.outlier_indices
    assert not rep.ok


def test_quality_pass_flags_narrow_band() -> None:
    f = np.geomspace(1e9, 1.05e9, 20)  # < 1 decade
    rep = d.Spectrum(f, _cole_cole(f)).quality_report()
    assert any("decade" in w for w in rep.warnings)
