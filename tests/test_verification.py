"""Tests for P4 verification: Kramers-Kronig, literature comparison, known-reference QC."""

from __future__ import annotations

import warnings

import numpy as np

from dielectric.io import Campaign, MeasurementSet, ValidationSet
from dielectric.io.campaign import CampaignMetadata
from dielectric.models.debye import Debye
from dielectric.reference import get
from dielectric.spectrum import Spectrum
from dielectric.verification import (
    compare_to_reference,
    find_closest_materials,
    kramers_kronig_check,
    validate_campaign,
    validate_set,
)

F = np.geomspace(1e8, 1e11, 120)


def test_kk_consistent_for_debye_pair() -> None:
    """A Debye spectrum is its own KK pair → near-zero residual (validates the transform)."""
    deb = Debye(5.0, 70.0, 8e-12)
    kk = kramers_kronig_check(Spectrum(F, deb.epsilon(F)), model=deb)
    assert kk.residual_rms < 0.02
    assert kk.is_consistent


def test_kk_without_model_warns_about_extrapolation() -> None:
    deb = Debye(5.0, 70.0, 8e-12)
    kk = kramers_kronig_check(Spectrum(F, deb.epsilon(F)))  # no model → constant extrapolation
    assert any("extrapolat" in w for w in kk.warnings)


def test_find_closest_materials_is_ranked() -> None:
    blood = get("blood")
    target = Spectrum(np.geomspace(2e8, 2e10, 60), blood.model.epsilon(np.geomspace(2e8, 2e10, 60)))
    ranked = find_closest_materials(target, material_class="tissue", top=3)
    assert ranked[0].material == "blood"  # closest to itself
    assert ranked[0].distance < ranked[1].distance


def test_temperature_mismatch_is_noted() -> None:
    water = get("water")
    f = np.geomspace(2e8, 2e10, 40)
    target = Spectrum(f, water.model.epsilon(f))
    cmp = compare_to_reference(target, water, target_temperature_c=10.0)
    assert any("temperature mismatch" in n for n in cmp.notes)


def test_validation_passes_for_matching_saline() -> None:
    f = np.geomspace(2e8, 2e10, 80)
    sal = get("saline", molarity=0.154, temperature_c=25.0)
    repeats = tuple(Spectrum(f, sal.model.epsilon(f)) for _ in range(3))
    vs = ValidationSet("ref", repeats, reference="saline", reference_kwargs={"molarity": 0.154})
    verdict = validate_set(vs, temperature_c=25.0)
    assert verdict.passed
    assert verdict.eps_real_rms < 0.05


def test_validation_fails_for_wrong_reference() -> None:
    f = np.geomspace(2e8, 2e10, 80)
    # measured = water, but declared reference = strong saline → σ mismatch should fail QC
    measured = get("water").model.epsilon(f)
    vs = ValidationSet("ref", (Spectrum(f, measured),), reference="saline",
                       reference_kwargs={"molarity": 0.5})
    verdict = validate_set(vs, temperature_c=25.0)
    assert not verdict.passed


def test_campaign_validation_all_must_pass() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        meas = MeasurementSet.from_glob("data/h02s19m*.csv")
        val = ValidationSet.from_glob("data/h02v*.csv", reference="saline",
                                      reference_kwargs={"molarity": 0.154})
    campaign = Campaign(measurements=(meas,), validations=(val,),
                        metadata=CampaignMetadata(temperature_c=25.0))
    cv = validate_campaign(campaign)
    assert cv.validated  # the real saline validation passes
    assert cv.verdicts[0].reference == "saline_0.154M"


def test_campaign_without_validation_is_not_validated() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        meas = MeasurementSet.from_glob("data/h02s19m*.csv")
    cv = validate_campaign(Campaign(measurements=(meas,)))
    assert not cv.validated
    assert "NOT VALIDATED" in cv.status


def test_kk_residual_property_threshold() -> None:
    deb = Debye(5.0, 70.0, 8e-12)
    kk = kramers_kronig_check(Spectrum(F, deb.epsilon(F)), model=deb)
    assert isinstance(kk.truncation_estimate, float)
    assert 0.0 <= kk.truncation_estimate <= 1.0
