"""Tests for P3: reference database query, parameterization, confidence/provenance."""

from __future__ import annotations

import numpy as np
import pytest

from dielectric.models.provenance import Confidence
from dielectric.reference import get, list_materials, query, water
from dielectric.reference._updater import refresh_from_sources

F = np.array([2e8, 1e9, 1e10, 2e10])


def test_query_by_class() -> None:
    tissues = query("tissue")
    liquids = query("liquid")
    assert "blood" in tissues
    assert "water" in liquids
    assert all(m.material_class == "tissue" for m in tissues.values())
    assert set(list_materials()) == set(tissues) | set(liquids)


def test_get_resolves_aliases() -> None:
    assert get("pure_water").name == "water"
    assert get("saline").name.startswith("saline")


def test_saline_is_molarity_parameterized() -> None:
    low = get("saline", molarity=0.05)
    high = get("saline", molarity=0.154)
    # higher molarity → higher ionic conductivity
    assert high.model.effective_conductivity(F)[0] > low.model.effective_conductivity(F)[0]


def test_temperature_parameterization_changes_water() -> None:
    cold = water(10.0).model.epsilon(np.array([1e6]))[0].real
    warm = water(40.0).model.epsilon(np.array([1e6]))[0].real
    assert cold > warm  # static permittivity falls with temperature


def test_confidence_flags() -> None:
    assert get("water").confidence is Confidence.HIGH
    assert get("blood").confidence is Confidence.VERIFY  # tissue snapshot is unconfirmed
    assert get("saline").confidence is Confidence.VERIFY


def test_tissue_values_are_lossy_and_have_band() -> None:
    blood = get("blood")
    assert np.all(blood.model.epsilon(F).imag <= 0)
    assert blood.valid_band_hz is not None


def test_provenance_bibtex_marks_verify() -> None:
    bib = get("blood").provenance.to_bibtex()
    assert "Gabriel" in bib
    assert "VERIFY" in bib


def test_unknown_material_raises() -> None:
    with pytest.raises(KeyError, match="unknown reference material"):
        get("unobtainium")


def test_updater_is_documented_but_not_executed() -> None:
    with pytest.raises(NotImplementedError, match="Online refresh is not enabled"):
        refresh_from_sources()
