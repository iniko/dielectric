"""In-memory session store for uploaded sets, campaigns, and cached analyses.

Deliberately simple (a dict) — persistence (PostgreSQL) is a later pass. Not thread-safe beyond the
single-process dev server, which is all the toolkit's interactive use needs.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from dielectric.io.campaign import Campaign, MeasurementSet, ValidationSet


@dataclass
class Store:
    measurement_sets: dict[str, MeasurementSet] = field(default_factory=dict)
    validation_sets: dict[str, ValidationSet] = field(default_factory=dict)
    campaigns: dict[str, Campaign] = field(default_factory=dict)
    analyses: dict[str, object] = field(default_factory=dict)  # campaign_id -> CampaignAnalysis

    def new_id(self) -> str:
        return uuid.uuid4().hex[:12]

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
