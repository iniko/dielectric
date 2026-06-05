"""Tests for P1 models: sign convention, model nesting, composition, mixing."""

from __future__ import annotations

import numpy as np
import pytest

from dielectric.models import (
    Bruggeman,
    ColeCole,
    ColeDavidson,
    DCConductivity,
    Debye,
    HavriliakNegami,
    JonscherUniversal,
    Looyenga,
    MaxwellGarnett,
    MultiPoleRelaxation,
)

F = np.geomspace(2e8, 2e10, 101)


def test_all_models_are_lossy_negative_imag() -> None:
    """Every passive model must have Im(ε*) ≤ 0 in the internal convention."""
    models = [
        Debye(5.0, 70.0, 8e-12),
        ColeCole(5.0, 70.0, 8e-12, 0.1),
        ColeDavidson(5.0, 70.0, 8e-12, 0.7),
        HavriliakNegami(5.0, 70.0, 8e-12, 0.1, 0.7),
        JonscherUniversal(5.0, 2.0, 0.6),
        DCConductivity(0.7),
        MultiPoleRelaxation(5.0, ((50.0, 8e-12, 0.1), (20.0, 1e-9, 0.1)), sigma_dc=0.7),
    ]
    for m in models:
        assert np.all(m.epsilon(F).imag <= 1e-12), type(m).__name__
        assert np.all(m.loss(F) >= -1e-12), type(m).__name__


def test_hn_nests_cole_cole_and_cole_davidson_and_debye() -> None:
    eps_inf, de, tau = 5.0, 70.0, 8e-12
    # β=1 → Cole-Cole
    hn_cc = HavriliakNegami(eps_inf, de, tau, 0.15, 1.0)
    cc = ColeCole(eps_inf, de, tau, 0.15)
    np.testing.assert_allclose(hn_cc.epsilon(F), cc.epsilon(F), rtol=1e-10)
    # α=0 → Cole-Davidson
    hn_cd = HavriliakNegami(eps_inf, de, tau, 0.0, 0.7)
    cd = ColeDavidson(eps_inf, de, tau, 0.7)
    np.testing.assert_allclose(hn_cd.epsilon(F), cd.epsilon(F), rtol=1e-10)
    # α=0, β=1 → Debye
    hn_db = HavriliakNegami(eps_inf, de, tau, 0.0, 1.0)
    db = Debye(eps_inf, de, tau)
    np.testing.assert_allclose(hn_db.epsilon(F), db.epsilon(F), rtol=1e-10)


def test_multipole_single_term_equals_cole_cole_and_debye() -> None:
    mp_cc = MultiPoleRelaxation(5.0, ((70.0, 8e-12, 0.1),))
    cc = ColeCole(5.0, 70.0, 8e-12, 0.1)
    np.testing.assert_allclose(mp_cc.epsilon(F), cc.epsilon(F), rtol=1e-12)
    mp_db = MultiPoleRelaxation(5.0, ((70.0, 8e-12, 0.0),))
    db = Debye(5.0, 70.0, 8e-12)
    np.testing.assert_allclose(mp_db.epsilon(F), db.epsilon(F), rtol=1e-12)


def test_multipole_flat_params_roundtrip() -> None:
    mp = MultiPoleRelaxation(5.0, ((50.0, 8e-12, 0.1), (20.0, 1e-9, 0.05)), sigma_dc=0.7)
    assert mp.param_names == (
        "eps_inf",
        "delta_eps_1", "tau_1", "alpha_1",
        "delta_eps_2", "tau_2", "alpha_2",
        "sigma_dc",
    )
    assert mp.n_params == 8
    updated = mp.with_params({"eps_inf": 6.0, "sigma_dc": 0.9})
    assert updated.params["eps_inf"] == 6.0
    assert updated.params["sigma_dc"] == 0.9
    assert updated.params["delta_eps_1"] == 50.0  # unchanged


def test_conductivity_composition_adds_loss() -> None:
    cc = ColeCole(5.0, 70.0, 8e-12, 0.1)
    composite = cc + DCConductivity(0.7)
    # at the lowest frequency the conductivity term dominates the loss
    assert composite.loss(F)[0] > cc.loss(F)[0]
    # real part unchanged by the (purely imaginary) conductivity term
    np.testing.assert_allclose(composite.epsilon(F).real, cc.epsilon(F).real, rtol=1e-10)


def test_sigma_eff_recovers_dc_conductivity() -> None:
    sigma = 0.7
    m = DCConductivity(sigma)
    np.testing.assert_allclose(m.effective_conductivity(F), sigma, rtol=1e-10)


def test_mixing_limits_to_pure_phases() -> None:
    host = Debye(2.0, 0.0, 1e-12)  # ε=2 constant
    incl = Debye(10.0, 0.0, 1e-12)  # ε=10 constant
    for rule in (MaxwellGarnett, Bruggeman, Looyenga):
        m0 = rule(host, incl, 0.0)
        m1 = rule(host, incl, 1.0)
        np.testing.assert_allclose(m0.epsilon(F).real, 2.0, rtol=1e-6)
        np.testing.assert_allclose(m1.epsilon(F).real, 10.0, rtol=1e-6)


def test_mixing_rejects_bad_fraction() -> None:
    host = Debye(2.0, 0.0, 1e-12)
    with pytest.raises(ValueError, match="volume_fraction"):
        MaxwellGarnett(host, host, 1.5)
