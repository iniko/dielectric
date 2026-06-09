import type {
  BudgetComponentIn,
  BudgetResult,
  CampaignAnalysis,
  CompareOut,
  FitOut,
  KKDetailOut,
  MaterialOut,
  ReferenceMatchOut,
  RepeatsOut,
  SalineSweepOut,
  ScreeningRequest,
  SetSummary,
  ValidationConfigRequest,
  ValidationDetailOut,
} from "./types";

async function postJson<T>(url: string, body: unknown): Promise<T> {
  return json(
    await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

async function json<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      detail = (await resp.json()).detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return resp.json() as Promise<T>;
}

export async function getMaterials(): Promise<MaterialOut[]> {
  return json(await fetch("/api/materials"));
}

export async function uploadSet(
  files: File[] | FileList,
  role: "measurement" | "validation",
  opts: {
    name: string;
    reference?: string;
    molarity?: number;
    salinity_psu?: number;
    temperature_c: number;
    operator?: string;
    instrument?: string;
    measurement_date?: string;
  },
): Promise<SetSummary> {
  const form = new FormData();
  Array.from(files).forEach((f) => form.append("files", f));
  form.append("role", role);
  form.append("name", opts.name);
  form.append("temperature_c", String(opts.temperature_c));
  if (opts.reference) form.append("reference", opts.reference);
  if (opts.molarity != null) form.append("molarity", String(opts.molarity));
  if (opts.salinity_psu != null) form.append("salinity_psu", String(opts.salinity_psu));
  if (opts.operator) form.append("operator", opts.operator);
  if (opts.instrument) form.append("instrument", opts.instrument);
  if (opts.measurement_date) form.append("measurement_date", opts.measurement_date);
  return json(await fetch("/api/sets", { method: "POST", body: form }));
}

export async function createCampaign(body: {
  measurement_set_ids: string[];
  validation_set_ids: string[];
  temperature_c: number;
  title?: string;
}): Promise<{ id: string }> {
  return json(
    await fetch("/api/campaigns", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function analyze(
  campaignId: string,
  body: { model?: string | null; n_poles?: number | null },
): Promise<CampaignAnalysis> {
  return json(
    await fetch(`/api/campaigns/${campaignId}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function getRepeats(setId: string, frequenciesGhz: number[]): Promise<RepeatsOut> {
  const q = frequenciesGhz.length ? `?frequencies=${frequenciesGhz.join(",")}` : "";
  return json(await fetch(`/api/sets/${setId}/repeats${q}`));
}

export async function setScreening(setId: string, req: ScreeningRequest): Promise<RepeatsOut> {
  return postJson(`/api/sets/${setId}/screening`, req);
}

export async function getValidation(setId: string): Promise<ValidationDetailOut> {
  return json(await fetch(`/api/sets/${setId}/validation`));
}

export async function setValidationConfig(
  setId: string,
  req: ValidationConfigRequest,
): Promise<ValidationDetailOut> {
  return postJson(`/api/sets/${setId}/validation`, req);
}

export async function fitCampaign(
  campaignId: string,
  body: { model?: string | null; n_poles?: number | null; dc_sigma?: boolean | null },
): Promise<FitOut> {
  return postJson(`/api/campaigns/${campaignId}/fit`, body);
}

export async function getKK(campaignId: string): Promise<KKDetailOut> {
  return json(await fetch(`/api/campaigns/${campaignId}/kk`));
}

export async function referenceMatch(
  setId: string,
  body: { reference: string; temperature_c: number; molarity?: number; salinity_psu?: number },
): Promise<ReferenceMatchOut> {
  return postJson(`/api/sets/${setId}/reference-match`, body);
}

export async function salineSweep(setId: string): Promise<SalineSweepOut> {
  return postJson(`/api/sets/${setId}/saline-sweep`, {});
}

export async function compareCampaign(
  campaignId: string,
  baseline?: string,
): Promise<CompareOut> {
  return postJson(`/api/campaigns/${campaignId}/compare`, { baseline: baseline ?? null });
}

export function reportUrl(campaignId: string, sample: string, fmt: "pdf" | "docx" | "html"): string {
  return `/api/campaigns/${campaignId}/report?sample=${encodeURIComponent(sample)}&fmt=${fmt}`;
}

export function compareReportUrl(
  campaignId: string,
  baseline: string,
  fmt: "pdf" | "docx" | "html",
): string {
  return `/api/campaigns/${campaignId}/compare/report?baseline=${encodeURIComponent(baseline)}&fmt=${fmt}`;
}

export function campaignReportUrl(campaignId: string, fmt: "pdf" | "docx" | "html"): string {
  return `/api/campaigns/${campaignId}/campaign-report?fmt=${fmt}`;
}

export async function computeBudget(body: {
  measurand: string;
  nominal_value: number;
  unit: string;
  components: BudgetComponentIn[];
  coverage_level: number;
}): Promise<BudgetResult> {
  return json(
    await fetch("/api/budget", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}
