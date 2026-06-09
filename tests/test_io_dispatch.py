"""Tests for the vendor-neutral auto-detecting loader (:func:`dielectric.io.load_any`).

The key back-compat guarantee: an Agilent 85070 CSV must load *identically* to
``load_agilent_85070`` — the dispatcher only adds metadata, never changes the numbers.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pytest

from dielectric.convention import ConventionWarning
from dielectric.io import load_agilent_85070, load_any, save_hdf5
from dielectric.spectrum import Spectrum

ONE_FILE = "data/h02s19m01.csv"


def test_load_any_matches_agilent_byte_for_byte() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        a = load_agilent_85070(ONE_FILE)
        b = load_any(ONE_FILE)
    np.testing.assert_array_equal(a.frequency_hz, b.frequency_hz)
    np.testing.assert_array_equal(a.epsilon, b.epsilon)


def test_load_any_still_warns_on_positive_loss() -> None:
    # The sign-convention boundary must keep firing through the dispatcher.
    with pytest.warns(ConventionWarning):
        load_any(ONE_FILE)


def test_load_any_lifts_agilent_instrument_header() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        s = load_any(ONE_FILE)
    extra = s.metadata.extra
    assert extra["detected_format"] == "agilent_csv"
    assert extra["instrument_vendor"] == "Agilent Technologies"
    assert extra["instrument_model"] == "E8362B"
    assert extra["instrument_serial"] == "MY43021411"
    assert extra["instrument_firmware"] == "A.07.50.67"
    assert "measurement_date" in extra


def test_load_any_generic_csv_has_no_instrument_keys(tmp_path: Path) -> None:
    csv = tmp_path / "generic.csv"
    csv.write_text("frequency,eps',eps''\n2e8,50,-10\n1e9,45,-12\n1e10,40,-15\n")
    s = load_any(csv)
    assert s.metadata.extra["detected_format"] == "csv"
    assert "instrument_vendor" not in s.metadata.extra
    assert np.all(s.eps_imag <= 0)


def test_load_any_detects_touchstone(tmp_path: Path) -> None:
    s1p = tmp_path / "spectrum.s1p"
    s1p.write_text("! a comment\n# Hz RI\n2e8 50 -10\n1e9 45 -12\n1e10 40 -15\n")
    s = load_any(s1p)
    assert s.metadata.extra["detected_format"] == "touchstone"
    assert s.frequency_hz[0] == pytest.approx(2e8)
    assert np.all(s.eps_imag <= 0)


def test_load_any_detects_touchstone_by_hash_header(tmp_path: Path) -> None:
    # A leading '#' option line is detected as Touchstone even without an .s1p extension.
    f = tmp_path / "spectrum.txt"
    f.write_text("# GHz RI\n0.2 50 -10\n1 45 -12\n10 40 -15\n")
    s = load_any(f)
    assert s.metadata.extra["detected_format"] == "touchstone"
    assert s.frequency_hz[-1] == pytest.approx(1e10)


def test_load_any_roundtrips_hdf5(tmp_path: Path) -> None:
    f = np.geomspace(2e8, 2e10, 51)
    eps = 5 + 50 / (1 + 1j * 2 * np.pi * f * 8e-12)
    spectrum = Spectrum(f, np.asarray(eps, dtype=np.complex128))
    h5 = tmp_path / "spectrum.h5"
    save_hdf5(spectrum, h5)
    loaded = load_any(h5)
    assert loaded.metadata.extra["detected_format"] == "hdf5"
    np.testing.assert_allclose(loaded.frequency_hz, f)
    np.testing.assert_allclose(loaded.epsilon, spectrum.epsilon)
