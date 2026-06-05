"""Pydantic request/response schemas — the API contract.

The backend is a thin orchestrator: these schemas mirror library outputs as JSON, and never contain
any numerics of their own.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SetSummary(BaseModel):
    id: str
    role: str  # "measurement" | "validation"
    name: str
    n_repeats: int
    n_used: int
    excluded_indices: list[int]
    band_ghz: tuple[float, float]
    eps_real_range: tuple[float, float]
    sigma_low_s_per_m: float
    quality_warnings: list[str]
    reference: str | None = None
    molarity: float | None = None
    notes: list[str] = Field(default_factory=list)


class CampaignCreate(BaseModel):
    measurement_set_ids: list[str]
    validation_set_ids: list[str] = Field(default_factory=list)
    temperature_c: float = 25.0
    title: str = ""


class CampaignSummary(BaseModel):
    id: str
    measurement_set_ids: list[str]
    validation_set_ids: list[str]
    temperature_c: float


class AnalyzeRequest(BaseModel):
    model: str | None = None  # force a model label
    n_poles: int | None = None  # force the number of poles


class ParamOut(BaseModel):
    name: str
    value: float
    uncertainty: float
    formatted: str


class RankedOut(BaseModel):
    label: str
    n_params: int
    chi2_reduced: float
    aicc: float
    delta_aicc: float
    bic: float
    r_squared: float
    flag: str  # "", "overparam", "degenerate"
    chosen: bool


class KKOut(BaseModel):
    residual_rms: float
    consistent: bool
    truncation_estimate: float


class MaterialMatch(BaseModel):
    material: str
    distance: float
    eps_real_rms: float
    loss_rms: float
    confidence: str


class SpectrumPlot(BaseModel):
    frequency_hz: list[float]
    eps_real: list[float]
    loss: list[float]
    fit_frequency_hz: list[float]
    fit_eps_real: list[float]
    fit_loss: list[float]


class ValidationVerdictOut(BaseModel):
    set_id: str
    reference: str
    passed: bool
    eps_real_rms: float
    sigma_measured: float
    sigma_reference: float
    notes: list[str]


class ValidationOut(BaseModel):
    validated: bool
    status: str
    verdicts: list[ValidationVerdictOut]


class AnalysisResult(BaseModel):
    sample_id: str
    chosen_model: str
    overridden: bool
    params: list[ParamOut]
    r_squared: float
    chi2_reduced: float
    aicc: float
    ranking: list[RankedOut]
    selection_warnings: list[str]
    kk: KKOut
    closest_materials: list[MaterialMatch]
    methods_paragraph: str
    plot: SpectrumPlot


class CampaignAnalysis(BaseModel):
    campaign_id: str
    results: list[AnalysisResult]
    validation: ValidationOut


class MaterialOut(BaseModel):
    name: str
    material_class: str
    confidence: str
    temperature_c: float


class BudgetComponentIn(BaseModel):
    name: str
    standard_uncertainty: float
    sensitivity: float = 1.0
    dof: float = float("inf")
    kind: str = "B"


class BudgetRequest(BaseModel):
    measurand: str = "ε'"
    nominal_value: float
    unit: str = ""
    components: list[BudgetComponentIn]
    coverage_level: float = 0.95


class BudgetContribution(BaseModel):
    name: str
    kind: str
    contribution: float
    dof: float
    percent: float


class BudgetResult(BaseModel):
    combined_standard_uncertainty: float
    effective_dof: float
    coverage_factor: float
    expanded_uncertainty: float
    relative_expanded: float
    contributions: list[BudgetContribution]
    table: str
