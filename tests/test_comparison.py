"""Tests for batch comparison: spectrum difference (per-frequency) and parameter difference."""

from __future__ import annotations

import numpy as np

from dielectric.comparison import (
    compare_parameters,
    compare_spectra,
    dominant_relaxation,
    static_permittivity,
)
from dielectric.fitting import fit_cole_cole_conductivity
from dielectric.models.multipole import MultiPoleRelaxation
from dielectric.spectrum import Spectrum
from dielectric.uncertainty import combine_repeats

F = np.geomspace(2e8, 2e10, 80)


def _noisy(spectra_grid: np.ndarray, base: np.ndarray, n: int, noise: float, seed: int):
    rng = np.random.default_rng(seed)
    return tuple(
        Spectrum(
            spectra_grid,
            base + rng.normal(0, noise, base.size) + 1j * rng.normal(0, noise, base.size),
        )
        for _ in range(n)
    )


def _batch(eps_s: float, n: int = 10, noise: float = 0.03, seed: int = 0):
    """A Type A mean spectrum + a DC-aware Cole-Cole fit for a batch with the given ε_s."""
    truth = MultiPoleRelaxation(5.0, ((eps_s - 5.0, 8e-12, 0.05),), sigma_dc=0.7)
    mean = combine_repeats(_noisy(F, truth.epsilon(F), n, noise, seed)).mean
    return mean, fit_cole_cole_conductivity(mean)


def test_static_permittivity_and_dominant_tau() -> None:
    model = MultiPoleRelaxation(5.0, ((47.0, 8e-12, 0.0), (3.0, 1e-9, 0.0)))
    assert static_permittivity(model) == 55.0  # 5 + 47 + 3
    # the dominant pole (Δε=47) sets the reported relaxation time
    _mean, fit = _batch(57.0)
    tau, u = dominant_relaxation(fit)
    assert tau > 0 and np.isfinite(u)


def test_identical_batches_show_no_significant_difference() -> None:
    mean_a, _ = _batch(57.0, seed=1)
    mean_b, _ = _batch(57.0, seed=2)  # same truth, different noise draw
    diff = compare_spectra(mean_a, mean_b)
    assert diff.frequency_hz.size == F.size
    # same underlying spectrum → very few points flagged (tolerate a little noise)
    assert diff.significant_eps.mean() < 0.1
    assert not diff.notes  # shared grid → no interpolation note


def test_shifted_batches_are_significant_with_expected_sign() -> None:
    mean_a, fit_a = _batch(70.0, seed=1)  # higher static permittivity
    mean_b, fit_b = _batch(57.0, seed=2)
    diff = compare_spectra(mean_a, mean_b)
    # a 13-unit ε_s gap with tight SEM → most low-frequency ε′ points separate
    assert diff.significant_eps.mean() > 0.5
    assert np.median(diff.delta_eps_real) > 0  # A − B > 0

    params = {p.name: p for p in compare_parameters(fit_a, fit_b)}
    eps_s = params["eps_static"]
    assert eps_s.delta > 0 and eps_s.z > 1.96 and eps_s.significant
    assert "sigma_dc" in params  # both fits carry a DC term


def test_mismatched_grids_interpolate_and_note() -> None:
    mean_a, _ = _batch(60.0, seed=3)
    # batch B on a coarser, offset grid within the same band
    fb = np.geomspace(3e8, 1.8e10, 50)
    truth = MultiPoleRelaxation(5.0, ((55.0, 8e-12, 0.05),), sigma_dc=0.7)
    mean_b = combine_repeats(_noisy(fb, truth.epsilon(fb), 10, 0.03, 9)).mean
    diff = compare_spectra(mean_a, mean_b)
    assert diff.notes and "interpolated" in diff.notes[0]
    # the overlap grid is bounded by batch B's narrower band
    assert diff.frequency_hz[0] >= 3e8 - 1 and diff.frequency_hz[-1] <= 1.8e10 + 1
