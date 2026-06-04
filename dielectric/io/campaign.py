"""Multi-set campaign model: repeatability groups, validation groups, and their metadata.

A **set** is one repeatability group — many repeat files of a single sample, averaged (Type A) into
a mean spectrum + SEM. A :class:`Campaign` holds *any number* of measurement sets and *any number*
of validation sets. Validation is optional; a campaign with no validation set is reported as
**"not validated"** (the pass/fail QC itself lives in :mod:`dielectric.verification.validation`).
"""

from __future__ import annotations

import glob
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..spectrum import Spectrum
from ..uncertainty.typea import TypeAResult, combine_repeats
from .csv_loader import load_agilent_85070

Loader = Callable[[str | Path], Spectrum]


def _load_glob(pattern: str, loader: Loader) -> tuple[tuple[Spectrum, ...], tuple[str, ...]]:
    paths = sorted(glob.glob(pattern))
    if not paths:
        raise FileNotFoundError(f"no files matched: {pattern}")
    spectra = tuple(loader(p) for p in paths)
    return spectra, tuple(Path(p).name for p in paths)


@dataclass(frozen=True)
class MeasurementSet:
    """A repeatability group: repeat spectra of one sample."""

    sample_id: str
    spectra: tuple[Spectrum, ...]
    temperature_c: float | None = None
    file_names: tuple[str, ...] = ()

    @classmethod
    def from_glob(
        cls,
        pattern: str,
        *,
        sample_id: str | None = None,
        loader: Loader = load_agilent_85070,
        temperature_c: float | None = None,
    ) -> MeasurementSet:
        spectra, names = _load_glob(pattern, loader)
        sid = sample_id or Path(pattern).stem
        return cls(sid, spectra, temperature_c, names)

    @property
    def n_repeats(self) -> int:
        return len(self.spectra)

    def type_a(self, *, outlier_k: float | None = 3.5) -> TypeAResult:
        """Combine the repeats into a Type A mean spectrum + SEM."""
        return combine_repeats(
            self.spectra,
            outlier_k=outlier_k,
            sample_id=self.sample_id,
            temperature_c=self.temperature_c,
        )


@dataclass(frozen=True)
class ValidationSet:
    """A repeatability group measuring a *known reference material*, for the QC check.

    ``reference`` names the embedded reference material (e.g. ``"saline"``); ``reference_kwargs``
    parameterizes it (e.g. ``{"molarity": 0.154}`` for 0.9 % NaCl) so any value is supported.
    """

    sample_id: str
    spectra: tuple[Spectrum, ...]
    reference: str
    reference_kwargs: dict[str, float] = field(default_factory=dict)
    temperature_c: float | None = None
    file_names: tuple[str, ...] = ()

    @classmethod
    def from_glob(
        cls,
        pattern: str,
        *,
        reference: str,
        reference_kwargs: dict[str, float] | None = None,
        sample_id: str | None = None,
        loader: Loader = load_agilent_85070,
        temperature_c: float | None = None,
    ) -> ValidationSet:
        spectra, names = _load_glob(pattern, loader)
        sid = sample_id or Path(pattern).stem
        return cls(sid, spectra, reference, reference_kwargs or {}, temperature_c, names)

    @property
    def n_repeats(self) -> int:
        return len(self.spectra)

    def type_a(self, *, outlier_k: float | None = 3.5) -> TypeAResult:
        return combine_repeats(
            self.spectra,
            outlier_k=outlier_k,
            sample_id=self.sample_id,
            temperature_c=self.temperature_c,
        )


@dataclass(frozen=True)
class CampaignMetadata:
    """Typed/validated context for a campaign."""

    title: str = ""
    operator: str = ""
    date: str = ""
    temperature_c: float = 25.0  # assumed measurement temperature (h02 decision: 25 °C)
    notes: str = ""
    extra: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Campaign:
    """Any number of measurement sets + any number of validation sets + metadata."""

    measurements: tuple[MeasurementSet, ...]
    validations: tuple[ValidationSet, ...] = ()
    metadata: CampaignMetadata = field(default_factory=CampaignMetadata)

    def __post_init__(self) -> None:
        if not self.measurements:
            raise ValueError("a campaign needs at least one measurement set")

    @property
    def has_validation(self) -> bool:
        return len(self.validations) > 0
