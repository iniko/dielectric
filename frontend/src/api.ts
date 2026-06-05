import type {
  BudgetComponentIn,
  BudgetResult,
  CampaignAnalysis,
  MaterialOut,
  SetSummary,
} from "./types";

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
  files: FileList,
  role: "measurement" | "validation",
  opts: { name: string; reference?: string; molarity?: number; temperature_c: number },
): Promise<SetSummary> {
  const form = new FormData();
  Array.from(files).forEach((f) => form.append("files", f));
  form.append("role", role);
  form.append("name", opts.name);
  form.append("temperature_c", String(opts.temperature_c));
  if (opts.reference) form.append("reference", opts.reference);
  if (opts.molarity != null) form.append("molarity", String(opts.molarity));
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

export function reportUrl(campaignId: string, sample: string, fmt: "pdf" | "docx"): string {
  return `/api/campaigns/${campaignId}/report?sample=${encodeURIComponent(sample)}&fmt=${fmt}`;
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
