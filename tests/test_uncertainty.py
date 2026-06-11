"""Tests for P6 uncertainty: Monte Carlo and the GUM/JCGM-100 budget engine."""

from __future__ import annotations

import math

import numpy as np
import pytest

from dielectric.models.multipole import MultiPoleRelaxation
from dielectric.spectrum import Spectrum
from dielectric.uncertainty import (
    UncertaintyComponent,
    coaxial_probe_permittivity_budget,
    combine_repeats,
    confidence_band,
    monte_carlo,
    repeat_distribution,
)
from dielectric.uncertainty.gum import GUMBudget
from dielectric.uncertainty.typea import budget_scalars


def _repeats(n: int = 10, noise: float = 0.05, seed: int = 0) -> tuple[Spectrum, ...]:
    f = np.geomspace(2e8, 2e10, 64)
    truth = MultiPoleRelaxation(5.0, ((52.0, 8e-12, 0.05),), sigma_dc=0.7)
    base = truth.epsilon(f)
    rng = np.random.default_rng(seed)
    return tuple(
        Spectrum(f, base + rng.normal(0, noise, f.size) + 1j * rng.normal(0, noise, f.size))
        for _ in range(n)
    )


def test_confidence_band_brackets_the_mean() -> None:
    ta = combine_repeats(_repeats())
    band = confidence_band(ta, k=1.96)
    assert band.coverage_k == 1.96
    assert band.frequency_hz.size == ta.mean.frequency_hz.size
    assert np.all(band.eps_real_lo <= band.eps_real)
    assert np.all(band.eps_real <= band.eps_real_hi)
    assert np.all(band.sigma_lo <= band.sigma)
    assert np.all(band.eps_real_hi - band.eps_real_lo > 0)


def _with_bad_repeat(n_good: int = 8, seed: int = 0) -> tuple[Spectrum, ...]:
    f = np.geomspace(2e8, 2e10, 40)
    base = 5 + 50 / (1 + 1j * 2 * np.pi * f * 8e-12)
    rng = np.random.default_rng(seed)
    good = [
        Spectrum(f, base + rng.normal(0, 0.02, f.size) + 1j * rng.normal(0, 0.02, f.size))
        for _ in range(n_good)
    ]
    good.append(Spectrum(f, base * 1.5))  # an obviously bad repeat at the last index
    return tuple(good)


def test_combine_repeats_zscores_and_threshold_are_surfaced() -> None:
    reps = _with_bad_repeat()
    ta = combine_repeats(reps, outlier_k=3.5)
    assert ta.repeat_zscores.size == len(reps)  # one z-score per input repeat, original order
    assert len(reps) - 1 in ta.excluded_indices
    assert ta.outlier_k_used == 3.5
    assert ta.n_repeats_total == len(reps)
    assert ta.reason(len(reps) - 1) == "excluded (k·MAD rule)"


def test_combine_repeats_keep_all_disables_screen() -> None:
    reps = _with_bad_repeat()
    ta = combine_repeats(reps, outlier_k=None)
    assert ta.excluded_indices == ()
    assert ta.outlier_k_used is None
    assert ta.n_repeats_used == len(reps)


def test_combine_repeats_manual_override_both_ways() -> None:
    reps = _with_bad_repeat()
    bad = len(reps) - 1
    kept = combine_repeats(reps, outlier_k=3.5, manual_keep=[bad])
    assert bad not in kept.excluded_indices
    assert kept.reason(bad) == "kept (manual override)"
    dropped = combine_repeats(reps, outlier_k=3.5, manual_exclude=[0])
    assert 0 in dropped.excluded_indices and bad in dropped.excluded_indices
    assert dropped.reason(0) == "excluded (manual)"


def test_repeat_distribution_summarises_per_frequency() -> None:
    reps = _repeats(n=12)
    dists = repeat_distribution(reps, [1e9, 5e9])
    assert len(dists) == 2
    d = dists[0]
    assert d.eps_real_samples.size == 12
    assert 0.0 <= d.shapiro_p_real <= 1.0
    assert abs(d.frequency_hz - 1e9) / 1e9 < 0.1


def _square(x: np.ndarray) -> float:
    return float(x[0] ** 2)


def test_monte_carlo_is_reproducible_with_seed() -> None:
    a = monte_carlo(_square, np.array([2.0]), np.array([0.1]), seed=7, n_samples=1000)
    b = monte_carlo(_square, np.array([2.0]), np.array([0.1]), seed=7, n_samples=1000)
    assert a.scalar == b.scalar  # identical seed → identical result


def test_monte_carlo_linear_propagation_matches_analytic() -> None:
    # y = 3x → σ_y = 3 σ_x
    mc = monte_carlo(
        lambda x: 3.0 * x[0], np.array([1.0]), np.array([0.2]), seed=0, n_samples=20000
    )
    assert mc.scalar[1] == pytest.approx(0.6, rel=0.05)


def test_monte_carlo_correlated_covariance() -> None:
    cov = np.array([[0.04, 0.03], [0.03, 0.04]])  # strong positive correlation
    mc = monte_carlo(lambda x: x[0] - x[1], np.array([1.0, 1.0]), cov, seed=1, n_samples=20000)
    # difference of positively-correlated variables has reduced variance
    assert mc.scalar[1] < math.sqrt(0.04 + 0.04)


def test_gum_combines_in_quadrature() -> None:
    comps = (UncertaintyComponent("a", 3.0), UncertaintyComponent("b", 4.0))
    budget = GUMBudget("x", 100.0, comps)
    assert budget.combined_standard_uncertainty == pytest.approx(5.0)


def test_rectangular_distribution_divisor() -> None:
    c = UncertaintyComponent.rectangular("cal", half_width=0.3)
    assert c.standard_uncertainty == pytest.approx(0.3 / math.sqrt(3.0))


def test_welch_satterthwaite_and_coverage_factor() -> None:
    # one dominant Type A component with low dof → k noticeably > 2
    comps = (UncertaintyComponent.type_a("rep", 1.0, dof=4),)
    budget = GUMBudget("x", 10.0, comps)
    assert budget.effective_dof == pytest.approx(4.0)
    assert budget.coverage_factor(0.95) > 2.5  # t(4) ≈ 2.78


def test_input_uncertainty_injection_increases_budget() -> None:
    without = coaxial_probe_permittivity_budget(
        58.0, type_a_std=0.67, type_a_dof=13, fit_std=1.4, input_inversion_relative=0.0
    )
    with_input = coaxial_probe_permittivity_budget(
        58.0, type_a_std=0.67, type_a_dof=13, fit_std=1.4, input_inversion_relative=0.03
    )
    assert with_input.combined_standard_uncertainty > without.combined_standard_uncertainty
    assert any("input/inversion" in c.name for c in with_input.components)


def test_relative_input_component_value() -> None:
    c = UncertaintyComponent.relative_input("inv", 0.03, 58.0)
    assert c.standard_uncertainty == pytest.approx(0.03 * 58.0)


def test_gum_table_and_expanded_uncertainty() -> None:
    budget = coaxial_probe_permittivity_budget(
        58.0, type_a_std=0.67, type_a_dof=13, fit_std=1.4,
        temperature_sensitivity=-0.36, temperature_half_width_c=2.0, input_inversion_relative=0.03,
    )
    table = budget.table()
    assert "combined standard uncertainty" in table
    assert "input/inversion" in table
    assert "temperature" in table
    # expanded uncertainty exceeds the combined standard uncertainty (k > 1)
    assert budget.expanded_uncertainty(0.95) > budget.combined_standard_uncertainty
    assert 0 < budget.relative_expanded < 1


def test_gum_large_dof_coverage_factor_near_two() -> None:
    comps = (UncertaintyComponent("b", 1.0),)  # all Type B → infinite dof
    budget = GUMBudget("x", 10.0, comps)
    assert budget.effective_dof == math.inf
    assert budget.coverage_factor(0.95) == pytest.approx(1.96, abs=0.02)


def test_component_validation_fails_loud() -> None:
    for bad_u in (-1.0, math.nan, math.inf):
        with pytest.raises(ValueError, match="standard_uncertainty"):
            UncertaintyComponent("u", bad_u)
    for bad_dof in (0.0, -3.0, math.nan):
        with pytest.raises(ValueError, match="dof"):
            UncertaintyComponent("d", 1.0, dof=bad_dof)
    with pytest.raises(ValueError, match="kind"):
        UncertaintyComponent("k", 1.0, kind="C")
    with pytest.raises(ValueError, match="sensitivity"):
        UncertaintyComponent("s", 1.0, sensitivity=math.inf)
    # zero uncertainty and infinite dof are legitimate
    ok = UncertaintyComponent("ok", 0.0, dof=math.inf)
    assert ok.contribution == 0.0


def test_triangular_distribution_divisor() -> None:
    c = UncertaintyComponent.triangular("t", half_width=0.6)
    assert c.standard_uncertainty == pytest.approx(0.6 / math.sqrt(6.0))
    assert c.kind == "B" and c.dof == math.inf


def test_gum_table_aligns_with_long_names() -> None:
    comps = (
        UncertaintyComponent("repeatability (Type A)", 0.67, dof=13, kind="A"),
        UncertaintyComponent("data inversion (instrument/probe software)", 1.74),
    )
    table = GUMBudget("ε'", 58.0, comps).table()
    lines = table.split("\n")
    header, sep = lines[1], lines[2]
    assert len(header) == len(sep)
    component_rows = lines[3 : 3 + len(comps)]
    assert all(len(r) == len(sep) for r in component_rows)
    assert "1000000000" not in table


def test_gum_table_infinite_dof_prints_inf() -> None:
    table = GUMBudget("x", 10.0, (UncertaintyComponent("b", 1.0),)).table()
    assert table.split("\n")[3].rstrip().endswith("inf")  # the component row's dof column
    assert "effective dof = inf" in table


def test_type_a_component_requires_finite_dof() -> None:
    with pytest.raises(ValueError, match="finite dof"):
        UncertaintyComponent("rep", 0.5, kind="A")  # default dof = inf
    assert UncertaintyComponent("rep", 0.5, dof=9, kind="A").dof == 9


def test_budget_scalars_median_over_band() -> None:
    ta = combine_repeats(_repeats(n=10))
    s = budget_scalars(ta)
    assert s.dof == ta.n_repeats_used - 1
    assert s.eps_real_median == pytest.approx(float(np.median(ta.mean.eps_real)))
    assert ta.mean.sem is not None
    assert s.eps_real_sem_median == pytest.approx(float(np.median(ta.mean.sem.real)))
    assert s.eps_real_sem_median > 0
    # a valid Type A budget component can be built straight from it
    comp = UncertaintyComponent.type_a("rep", s.eps_real_sem_median, s.dof)
    assert comp.kind == "A"


def test_budget_scalars_rejects_single_repeat() -> None:
    ta = combine_repeats(_repeats(n=1))
    with pytest.raises(ValueError, match="repeats"):
        budget_scalars(ta)
