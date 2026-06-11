"""Pydantic request/response schemas — the API contract.

The backend is a thin orchestrator: these schemas mirror library outputs as JSON, and never contain
any numerics of their own.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class SetSummary(BaseModel):
    id: str
    role: str  # "measurement" | "validation"
    name: str
    n_repeats: int
    n_used: int
    excluded_indices: list[int]
    excluded_filenames: list[str] = Field(default_factory=list)
    band_ghz: tuple[float, float]
    eps_real_range: tuple[float, float]
    sigma_low_s_per_m: float
    quality_warnings: list[str]
    reference: str | None = None
    molarity: float | None = None
    notes: list[str] = Field(default_factory=list)
    # instrument: operator-supplied, else vendor+model lifted from the file header
    instrument: str | None = None
    detected_format: str | None = None  # "agilent_csv" | "csv" | "touchstone" | "hdf5"


class CampaignCreate(BaseModel):
    measurement_set_ids: list[str]
    validation_set_ids: list[str] = Field(default_factory=list)
    temperature_c: float = 25.0
    title: str = ""
    operator: str = ""
    date: str = ""


class CampaignSummary(BaseModel):
    id: str
    measurement_set_ids: list[str]
    validation_set_ids: list[str]
    temperature_c: float


class AnalyzeRequest(BaseModel):
    model: str | None = None  # force a model label
    n_poles: int | None = Field(default=None, ge=1, le=3)  # force the number of poles (1-3)
    dc_sigma: bool | None = None  # constrain auto-selection to families with(out) a DC-σ term


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
    recommended: bool = False  # the parsimony-aware automatic pick (≠ chosen after an override)
    excluded_reason: str = ""  # why it is not the recommendation ("" = it is the recommendation)


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
    linked_batches: list[str] = Field(default_factory=list)  # measurement sample names it validates


class ValidationOut(BaseModel):
    validated: bool
    status: str
    verdicts: list[ValidationVerdictOut]


class AnalysisResult(BaseModel):
    sample_id: str
    chosen_model: str
    overridden: bool
    structure: str = ""  # plain-language model structure (family + pole count)
    equation: str = ""  # unicode model equation
    rationale: str = ""  # why the recommendation was chosen
    params: list[ParamOut]
    r_squared: float
    chi2_reduced: float
    aicc: float
    msp_real: float = float("nan")  # mean squared pull, ε' component
    msp_imag: float = float("nan")  # mean squared pull, ε'' component
    r_squared_real: float = float("nan")  # per-component R² (may be negative)
    r_squared_imag: float = float("nan")
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


class RepeatDetail(BaseModel):
    index: int
    filename: str
    zscore: float  # robust MAD z-score of consensus distance
    kept: bool
    reason: str  # "kept" | "excluded (k·MAD rule)" | "excluded (manual)" | "kept (manual override)"


class ScreeningInfo(BaseModel):
    outlier_k: float | None  # threshold applied (None = screening disabled / keep all)
    n_total: int
    n_used: int
    n_excluded: int
    manual_exclude: list[int]
    manual_keep: list[int]
    method: str
    citation: str


class ScreeningImpact(BaseModel):
    """How the Type A mean shifts if the excluded repeats were kept (with vs without)."""

    frequency_ref_hz: float
    eps_real_with: float  # screened (as used)
    eps_real_without: float  # all repeats kept
    sigma_with: float
    sigma_without: float
    max_abs_d_eps_real: float
    max_abs_d_sigma: float


class ScreeningRequest(BaseModel):
    outlier_k: float | None = 3.5
    manual_exclude: list[int] = Field(default_factory=list)
    manual_keep: list[int] = Field(default_factory=list)


class RepeatsOut(BaseModel):
    set_id: str
    name: str
    n_repeats: int
    n_used: int
    excluded_indices: list[int]
    coverage_k: float
    band: RepeatBand
    distributions: list[RepeatDistributionOut] = Field(default_factory=list)
    repeats: list[RepeatDetail] = Field(default_factory=list)
    screening: ScreeningInfo | None = None
    impact: ScreeningImpact | None = None


class FitRequest(BaseModel):
    model: str | None = None  # force a candidate label
    n_poles: int | None = Field(default=None, ge=1, le=3)  # force the number of poles (1-3)
    dc_sigma: bool | None = None  # prefer a model family carrying a DC-σ term
    fixed_params: dict[str, float] = Field(default_factory=dict)  # name -> fixed value


class ResidualSeries(BaseModel):
    frequency_hz: list[float]
    residual_eps_real: list[float]  # Re(ε_model − ε_data)
    residual_loss: list[float]  # (−Im ε_model) − (−Im ε_data): positive-loss residual
    # standardized (dimensionless) residuals = raw ÷ per-point Type A σ; Σ(·²) == χ²
    norm_eps_real: list[float]
    norm_loss: list[float]


class FitResultOut(BaseModel):
    sample_id: str
    chosen_model: str
    overridden: bool
    structure: str = ""  # plain-language model structure
    equation: str = ""  # unicode model equation
    rationale: str = ""  # why the recommendation was chosen
    params: list[ParamOut]
    r_squared: float
    chi2_reduced: float
    aicc: float
    msp_real: float = float("nan")  # mean squared pull, ε' component
    msp_imag: float = float("nan")  # mean squared pull, ε'' component
    r_squared_real: float = float("nan")  # per-component R² (may be negative)
    r_squared_imag: float = float("nan")
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


# ---- editable, batch-linked validation --------------------------------------------------------


class ValidationConfigRequest(BaseModel):
    reference: str = "saline"
    molarity: float | None = None  # saline, mol/L (one of molarity/mass_percent)
    mass_percent: float | None = None  # saline, % w/w NaCl
    salinity_psu: float | None = None  # seawater
    temperature_c: float = 25.0
    # measurement batch ids this validation validates
    measurement_set_ids: list[str] = Field(default_factory=list)


class ValidationConfigOut(BaseModel):
    reference: str
    molarity: float | None = None
    mass_percent: float | None = None
    salinity_psu: float | None = None
    temperature_c: float


class ValidationDetailOut(BaseModel):
    set_id: str
    name: str
    reference_label: str
    confidence: str
    config: ValidationConfigOut
    verdict: ValidationVerdictOut
    overlay: RefOverlay
    saline_sweep: list[SalineSweepRow] | None = None
    linked_batches: list[str]  # measurement set ids


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
    name: str = Field(min_length=1)
    standard_uncertainty: float = Field(ge=0, allow_inf_nan=False)
    sensitivity: float = Field(default=1.0, allow_inf_nan=False)
    dof: float | None = Field(default=None, gt=0)  # None = infinite (JSON has no inf)
    kind: Literal["A", "B"] = "B"

    @model_validator(mode="after")
    def _type_a_needs_dof(self) -> BudgetComponentIn:
        if self.kind == "A" and self.dof is None:
            raise ValueError(
                f"Type A component {self.name!r} must state finite dof (n_repeats - 1)"
            )
        return self


class TypeASummaryOut(BaseModel):
    """A measurement set's Type A statistics reduced to one budget term (median over the band)."""

    set_id: str
    name: str
    n_used: int
    dof: float  # n_used - 1
    eps_real_median: float
    eps_real_sem_median: float
    band_ghz: tuple[float, float]


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
    dof: float | None  # None = infinite
    percent: float


class BudgetResult(BaseModel):
    combined_standard_uncertainty: float
    effective_dof: float | None  # None = infinite
    coverage_factor: float
    expanded_uncertainty: float
    relative_expanded: float | None  # None when nominal == 0 (undefined)
    contributions: list[BudgetContribution]
    table: str
