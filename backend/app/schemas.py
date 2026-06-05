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


# ---- step endpoints (stepwise UX): repeats, fit, KK, reference match, saline sweep -------------


class RepeatBand(BaseModel):
    frequency_hz: list[float]
    eps_real: list[float]
    eps_real_lo: list[float]
    eps_real_hi: list[float]
    sigma: list[float]
    sigma_lo: list[float]
    sigma_hi: list[float]


class RepeatDistributionOut(BaseModel):
    frequency_hz: float
    eps_real_samples: list[float]
    eps_imag_samples: list[float]
    eps_real_mean: float
    eps_real_std: float
    eps_imag_mean: float
    eps_imag_std: float
    shapiro_p_real: float
    shapiro_p_imag: float


class RepeatsOut(BaseModel):
    set_id: str
    name: str
    n_repeats: int
    n_used: int
    excluded_indices: list[int]
    coverage_k: float
    band: RepeatBand
    distributions: list[RepeatDistributionOut] = Field(default_factory=list)


class FitRequest(BaseModel):
    model: str | None = None  # force a candidate label
    n_poles: int | None = None  # force the number of poles
    dc_sigma: bool | None = None  # prefer a model family carrying a DC-σ term
    fixed_params: dict[str, float] = Field(default_factory=dict)  # name -> fixed value


class ResidualSeries(BaseModel):
    frequency_hz: list[float]
    residual_eps_real: list[float]  # Re(ε_model − ε_data)
    residual_loss: list[float]  # (−Im ε_model) − (−Im ε_data): positive-loss residual


class FitResultOut(BaseModel):
    sample_id: str
    chosen_model: str
    overridden: bool
    params: list[ParamOut]
    r_squared: float
    chi2_reduced: float
    aicc: float
    ranking: list[RankedOut]
    selection_warnings: list[str]
    plot: SpectrumPlot
    residual: ResidualSeries


class FitOut(BaseModel):
    campaign_id: str
    results: list[FitResultOut]


class KKDetail(BaseModel):
    sample_id: str
    frequency_hz: list[float]
    predicted_eps_real: list[float]
    measured_eps_real: list[float]
    relative_residual: list[float]  # |predicted − measured| / |measured| at each frequency
    residual_rms: float
    truncation_estimate: float
    consistent: bool
    warnings: list[str]


class KKDetailOut(BaseModel):
    campaign_id: str
    results: list[KKDetail]


class ReferenceMatchRequest(BaseModel):
    reference: str = "saline"
    temperature_c: float = 25.0
    molarity: float | None = None
    salinity_psu: float | None = None


class RefOverlay(BaseModel):
    frequency_hz: list[float]
    meas_eps_real: list[float]
    meas_loss: list[float]
    ref_eps_real: list[float]
    ref_loss: list[float]
    rel_error_pct: list[float]


class ReferenceMatchOut(BaseModel):
    set_id: str
    reference_label: str
    confidence: str
    rms: float
    eps_real_rms: float
    loss_rms: float
    mean_rel_error_pct: float
    nrmse: float
    max_abs_d_eps_real: float
    max_abs_d_loss: float
    in_band_fraction: float
    temperature_delta_c: float | None
    notes: list[str]
    overlay: RefOverlay


class SalineSweepRow(BaseModel):
    molarity: float
    temperature_c: float
    rms: float
    eps_real_rms: float


class SalineSweepOut(BaseModel):
    set_id: str
    rows: list[SalineSweepRow]  # sorted by rms ascending


# ---- batch comparison (normal vs diseased, etc.) ----------------------------------------------


class ParamSummary(BaseModel):
    eps_static: float
    eps_static_u: float
    eps_inf: float
    eps_inf_u: float
    tau_dominant_s: float
    tau_dominant_u: float
    sigma_dc: float | None = None
    sigma_dc_u: float | None = None


class BatchSummary(BaseModel):
    sample_id: str
    model: str
    band: RepeatBand  # ε′ + σ_eff means with 95% CI
    params: ParamSummary


class SpectrumDiff(BaseModel):
    frequency_hz: list[float]
    delta_eps_real: list[float]
    se_eps_real: list[float]
    significant_eps: list[bool]
    delta_sigma: list[float]
    se_sigma: list[float]
    significant_sigma: list[bool]
    coverage_k: float
    notes: list[str]


class ParamDiff(BaseModel):
    name: str
    a: float
    ua: float
    b: float
    ub: float
    delta: float
    z: float
    significant: bool


class BatchDifference(BaseModel):
    sample_id: str  # batch A (vs the baseline)
    baseline: str  # batch B
    spectrum: SpectrumDiff
    params: list[ParamDiff]


class CompareRequest(BaseModel):
    baseline: str | None = None  # sample_id to use as the reference batch; default = first


class CompareOut(BaseModel):
    campaign_id: str
    baseline: str
    batches: list[BatchSummary]
    differences: list[BatchDifference]  # one per non-baseline batch, vs the baseline


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
