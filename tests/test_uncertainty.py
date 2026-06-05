"""Tests for P6 uncertainty: Monte Carlo and the GUM/JCGM-100 budget engine."""

from __future__ import annotations

import math

import numpy as np
import pytest

from dielectric.uncertainty import (
    UncertaintyComponent,
    coaxial_probe_permittivity_budget,
    monte_carlo,
)
from dielectric.uncertainty.gum import GUMBudget


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
