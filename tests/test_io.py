"""Tests for P3b: CSV loading, sign convention at the boundary, multi-set campaign, Type A."""

from __future__ import annotations

import warnings

import numpy as np
import pytest

from dielectric.convention import ConventionWarning
from dielectric.io import (
    Campaign,
    MeasurementSet,
    ValidationSet,
    load_agilent_85070,
)
from dielectric.io.csv_loader import load_csv
from dielectric.spectrum import Spectrum
from dielectric.uncertainty.typea import combine_repeats

MEAS_GLOB = "data/h02s19m*.csv"
VAL_GLOB = "data/h02v*.csv"
ONE_FILE = "data/h02s19m01.csv"


def test_agilent_loader_warns_and_negates_loss() -> None:
    with pytest.warns(ConventionWarning):
        s = load_agilent_85070(ONE_FILE)
    assert isinstance(s, Spectrum)
    assert s.frequency_hz.size == 101
    assert s.band_hz[0] == pytest.approx(2e8)
    assert s.band_hz[1] == pytest.approx(2e10)
    assert np.all(s.eps_imag <= 0)  # internal convention
    assert np.all(s.loss >= 0)  # display convention
    assert np.all(s.effective_conductivity >= 0)


def test_generic_csv_loader_matches_agilent() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        a = load_agilent_85070(ONE_FILE)
        b = load_csv(ONE_FILE, header_contains="frequency")
    np.testing.assert_allclose(a.epsilon, b.epsilon)


def test_measurement_set_loads_all_repeats() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ms = MeasurementSet.from_glob(MEAS_GLOB, sample_id="h02", temperature_c=25.0)
    assert ms.n_repeats == 15
    assert ms.temperature_c == 25.0
    assert len(ms.file_names) == 15


def test_type_a_mean_has_sem_and_screens_outlier() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ms = MeasurementSet.from_glob(MEAS_GLOB)
    ta = ms.type_a()
    assert ta.mean.sem is not None
    assert np.all(ta.mean.sem.real >= 0)
    assert ta.n_repeats_used <= 15
    # the SEM should be small relative to the signal (good repeatability)
    assert np.median(ta.mean.sem.real) < 5.0


def test_outlier_screen_excludes_injected_bad_repeat() -> None:
    f = np.geomspace(2e8, 2e10, 51)
    base = 5 + 50 / (1 + 1j * 2 * np.pi * f * 8e-12)
    rng = np.random.default_rng(0)
    repeats = [
        Spectrum(f, base + rng.normal(0, 0.02, f.size) + 1j * rng.normal(0, 0.02, f.size))
        for _ in range(8)
    ]
    repeats.append(Spectrum(f, base * 1.5))  # an obviously bad repeat
    ta = combine_repeats(repeats, outlier_k=3.5)
    assert 8 in ta.excluded_indices


def test_validation_set_carries_reference() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        vs = ValidationSet.from_glob(
            VAL_GLOB, reference="saline", reference_kwargs={"molarity": 0.154}
        )
    assert vs.reference == "saline"
    assert vs.reference_kwargs["molarity"] == 0.154
    assert vs.n_repeats == 25


def test_campaign_requires_measurements_and_tracks_validation() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ms = MeasurementSet.from_glob(MEAS_GLOB)
        vs = ValidationSet.from_glob(VAL_GLOB, reference="saline")
    campaign = Campaign(measurements=(ms,), validations=(vs,))
    assert campaign.has_validation
    assert not Campaign(measurements=(ms,)).has_validation
    with pytest.raises(ValueError, match="at least one measurement"):
        Campaign(measurements=())


def test_combine_repeats_rejects_grid_mismatch() -> None:
    s1 = Spectrum(np.geomspace(2e8, 2e10, 51), np.ones(51, dtype=complex))
    s2 = Spectrum(np.geomspace(2e8, 2e10, 41), np.ones(41, dtype=complex))
    with pytest.raises(ValueError, match="shared frequency grid"):
        combine_repeats([s1, s2])
