// Mirrors the backend Pydantic schemas (the API contract).

export interface SetSummary {
  id: string;
  role: "measurement" | "validation";
  name: string;
  n_repeats: number;
  n_used: number;
  excluded_indices: number[];
  excluded_filenames: string[];
  band_ghz: [number, number];
  eps_real_range: [number, number];
  sigma_low_s_per_m: number;
  quality_warnings: string[];
  reference?: string | null;
  molarity?: number | null;
  notes: string[];
}

export interface ParamOut {
  name: string;
  value: number;
  uncertainty: number;
  formatted: string;
}

export interface RankedOut {
  label: string;
  n_params: number;
  chi2_reduced: number;
  aicc: number;
  delta_aicc: number;
  bic: number;
  r_squared: number;
  flag: "" | "overparam" | "degenerate";
  chosen: boolean;
}

export interface KKOut {
  residual_rms: number;
  consistent: boolean;
  truncation_estimate: number;
}

export interface MaterialMatch {
  material: string;
  distance: number;
  eps_real_rms: number;
  loss_rms: number;
  confidence: string;
}

export interface SpectrumPlot {
  frequency_hz: number[];
  eps_real: number[];
  loss: number[];
  fit_frequency_hz: number[];
  fit_eps_real: number[];
  fit_loss: number[];
}

export interface AnalysisResult {
  sample_id: string;
  chosen_model: string;
  overridden: boolean;
  params: ParamOut[];
  r_squared: number;
  chi2_reduced: number;
  aicc: number;
  ranking: RankedOut[];
  selection_warnings: string[];
  kk: KKOut;
  closest_materials: MaterialMatch[];
  methods_paragraph: string;
  plot: SpectrumPlot;
}

export interface ValidationVerdict {
  set_id: string;
  reference: string;
  passed: boolean;
  eps_real_rms: number;
  sigma_measured: number;
  sigma_reference: number;
  notes: string[];
}

export interface ValidationOut {
  validated: boolean;
  status: string;
  verdicts: ValidationVerdict[];
}

export interface CampaignAnalysis {
  campaign_id: string;
  results: AnalysisResult[];
  validation: ValidationOut;
}

export interface MaterialOut {
  name: string;
  material_class: string;
  confidence: string;
  temperature_c: number;
}

// ---- step endpoints (stepwise UX) ----

export interface RepeatBand {
  frequency_hz: number[];
  eps_real: number[];
  eps_real_lo: number[];
  eps_real_hi: number[];
  sigma: number[];
  sigma_lo: number[];
  sigma_hi: number[];
}

export interface RepeatDistributionOut {
  frequency_hz: number;
  eps_real_samples: number[];
  eps_imag_samples: number[];
  eps_real_mean: number;
  eps_real_std: number;
  eps_imag_mean: number;
  eps_imag_std: number;
  shapiro_p_real: number;
  shapiro_p_imag: number;
}

export interface RepeatDetail {
  index: number;
  filename: string;
  zscore: number;
  kept: boolean;
  reason: string;
}

export interface ScreeningInfo {
  outlier_k: number | null;
  n_total: number;
  n_used: number;
  n_excluded: number;
  manual_exclude: number[];
  manual_keep: number[];
  method: string;
  citation: string;
}

export interface ScreeningImpact {
  frequency_ref_hz: number;
  eps_real_with: number;
  eps_real_without: number;
  sigma_with: number;
  sigma_without: number;
  max_abs_d_eps_real: number;
  max_abs_d_sigma: number;
}

export interface ScreeningRequest {
  outlier_k: number | null;
  manual_exclude: number[];
  manual_keep: number[];
}

export interface RepeatsOut {
  set_id: string;
  name: string;
  n_repeats: number;
  n_used: number;
  excluded_indices: number[];
  coverage_k: number;
  band: RepeatBand;
  distributions: RepeatDistributionOut[];
  repeats: RepeatDetail[];
  screening: ScreeningInfo | null;
  impact: ScreeningImpact | null;
}

export interface ResidualSeries {
  frequency_hz: number[];
  residual_eps_real: number[];
  residual_loss: number[];
  norm_eps_real: number[];
  norm_loss: number[];
}

export interface FitResultOut {
  sample_id: string;
  chosen_model: string;
  overridden: boolean;
  params: ParamOut[];
  r_squared: number;
  chi2_reduced: number;
  aicc: number;
  ranking: RankedOut[];
  selection_warnings: string[];
  plot: SpectrumPlot;
  residual: ResidualSeries;
}

export interface FitOut {
  campaign_id: string;
  results: FitResultOut[];
}

export interface KKDetail {
  sample_id: string;
  frequency_hz: number[];
  predicted_eps_real: number[];
  measured_eps_real: number[];
  relative_residual: number[];
  residual_rms: number;
  truncation_estimate: number;
  consistent: boolean;
  warnings: string[];
}

export interface KKDetailOut {
  campaign_id: string;
  results: KKDetail[];
}

export interface RefOverlay {
  frequency_hz: number[];
  meas_eps_real: number[];
  meas_loss: number[];
  ref_eps_real: number[];
  ref_loss: number[];
  rel_error_pct: number[];
}

export interface ReferenceMatchOut {
  set_id: string;
  reference_label: string;
  confidence: string;
  rms: number;
  eps_real_rms: number;
  loss_rms: number;
  mean_rel_error_pct: number;
  nrmse: number;
  max_abs_d_eps_real: number;
  max_abs_d_loss: number;
  in_band_fraction: number;
  temperature_delta_c: number | null;
  notes: string[];
  overlay: RefOverlay;
}

export interface SalineSweepRow {
  molarity: number;
  temperature_c: number;
  rms: number;
  eps_real_rms: number;
}

export interface SalineSweepOut {
  set_id: string;
  rows: SalineSweepRow[];
}

// ---- batch comparison ----

export interface ParamSummary {
  eps_static: number;
  eps_static_u: number;
  eps_inf: number;
  eps_inf_u: number;
  tau_dominant_s: number;
  tau_dominant_u: number;
  sigma_dc?: number | null;
  sigma_dc_u?: number | null;
}

export interface BatchSummary {
  sample_id: string;
  model: string;
  band: RepeatBand;
  params: ParamSummary;
}

export interface SpectrumDiff {
  frequency_hz: number[];
  delta_eps_real: number[];
  se_eps_real: number[];
  significant_eps: boolean[];
  delta_sigma: number[];
  se_sigma: number[];
  significant_sigma: boolean[];
  coverage_k: number;
  notes: string[];
}

export interface ParamDiff {
  name: string;
  a: number;
  ua: number;
  b: number;
  ub: number;
  delta: number;
  z: number;
  significant: boolean;
}

export interface BatchDifference {
  sample_id: string;
  baseline: string;
  spectrum: SpectrumDiff;
  params: ParamDiff[];
}

export interface CompareOut {
  campaign_id: string;
  baseline: string;
  batches: BatchSummary[];
  differences: BatchDifference[];
}

export interface BudgetComponentIn {
  name: string;
  standard_uncertainty: number;
  sensitivity: number;
  dof: number;
  kind: string;
}

export interface BudgetContribution {
  name: string;
  kind: string;
  contribution: number;
  dof: number;
  percent: number;
}

export interface BudgetResult {
  combined_standard_uncertainty: number;
  effective_dof: number;
  coverage_factor: number;
  expanded_uncertainty: number;
  relative_expanded: number;
  contributions: BudgetContribution[];
  table: string;
}
