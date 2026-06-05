// Mirrors the backend Pydantic schemas (the API contract).

export interface SetSummary {
  id: string;
  role: "measurement" | "validation";
  name: string;
  n_repeats: number;
  n_used: number;
  excluded_indices: number[];
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
