"""In-memory session store for uploaded sets, campaigns, and cached analyses.

Deliberately simple (a dict) — persistence (PostgreSQL) is a later pass. Not thread-safe beyond the
single-process dev server, which is all the toolkit's interactive use needs.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from dielectric.io.campaign import Campaign, MeasurementSet, ValidationSet


@dataclass
class ScreeningChoice:
    """A set's repeat-screening configuration (the user's transparent, auditable choice)."""

    outlier_k: float | None = 3.5  # None disables the k·MAD screen (keep all, with a UI warning)
    manual_exclude: tuple[int, ...] = ()  # repeats forced out regardless of the rule
    manual_keep: tuple[int, ...] = ()  # repeats forced in despite the rule


@dataclass
class ValidationConfig:
    """A validation set's editable reference + the measurement batch(es) it validates."""

    reference: str = "saline"
    molarity: float = 0.154  # for saline (mol/L)
    salinity_psu: float | None = None  # for seawater
    temperature_c: float = 25.0
    measurement_set_ids: tuple[str, ...] = ()  # batches this validation is linked to


@dataclass
class Store:
    measurement_sets: dict[str, MeasurementSet] = field(default_factory=dict)
    validation_sets: dict[str, ValidationSet] = field(default_factory=dict)
    campaigns: dict[str, Campaign] = field(default_factory=dict)
    analyses: dict[str, object] = field(default_factory=dict)  # campaign_id -> CampaignAnalysis
    # campaign_id -> {sample_id -> {"fit": ..., "spectrum": ..., ...}}
    fits: dict[str, dict[str, dict[str, object]]] = field(default_factory=dict)
    screening: dict[str, ScreeningChoice] = field(default_factory=dict)  # set_id -> choice
    # validation set_id -> editable reference config
    validation_config: dict[str, ValidationConfig] = field(default_factory=dict)

    def new_id(self) -> str:
        return uuid.uuid4().hex[:12]

    def screening_for(self, set_id: str | None) -> ScreeningChoice:
        return self.screening.get(set_id, ScreeningChoice()) if set_id else ScreeningChoice()

    def validation_config_for(self, set_id: str | None) -> ValidationConfig:
        if not set_id:
            return ValidationConfig()
        return self.validation_config.get(set_id, ValidationConfig())

    def set_id_of(self, obj: object) -> str | None:
        """Reverse-lookup a stored set's id by object identity (campaigns hold the objects)."""
        for sid, ms in self.measurement_sets.items():
            if ms is obj:
                return sid
        for sid, vs in self.validation_sets.items():
            if vs is obj:
                return sid
        return None

    def invalidate_caches_for_set(self, set_id: str) -> None:
        """Drop cached fits/analyses for every campaign containing this set (screening changed)."""
        obj: MeasurementSet | ValidationSet | None = self.measurement_sets.get(set_id)
        if obj is None:
            obj = self.validation_sets.get(set_id)
        if obj is None:
            return
        for cid, camp in list(self.campaigns.items()):
            if any(m is obj for m in (*camp.measurements, *camp.validations)):
                self.fits.pop(cid, None)
                self.analyses.pop(cid, None)

    def add_measurement(self, ms: MeasurementSet) -> str:
        sid = self.new_id()
        self.measurement_sets[sid] = ms
        return sid

    def add_validation(self, vs: ValidationSet) -> str:
        sid = self.new_id()
        self.validation_sets[sid] = vs
        return sid

    def add_campaign(self, campaign: Campaign) -> str:
        cid = self.new_id()
        self.campaigns[cid] = campaign
        return cid


STORE = Store()
