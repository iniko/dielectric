import { useRef, useState } from "react";
import * as api from "../api";
import type { AnalysisResult, CampaignAnalysis, SetSummary } from "../types";
import { BodePlot, ColeColePlot } from "../components/Plots";
import { Badge, Button, Card, Field, Input, Stat } from "../components/ui";

const MODEL_OPTIONS = [
  "", "Debye", "Cole-Cole", "Cole-Davidson", "Havriliak-Negami", "Jonscher",
  "Cole-Cole + DC σ", "MultiPole(N=2) + DC σ", "MultiPole(N=3) + DC σ",
];

export default function AnalysisWorkflow() {
  const [measurements, setMeasurements] = useState<SetSummary[]>([]);
  const [validations, setValidations] = useState<SetSummary[]>([]);
  const [temperature, setTemperature] = useState(25);
  const [reference, setReference] = useState("saline");
  const [molarity, setMolarity] = useState(0.154);
  const [model, setModel] = useState("");
  const [poles, setPoles] = useState("");
  const [analysis, setAnalysis] = useState<CampaignAnalysis | null>(null);
  const [campaignId, setCampaignId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function upload(files: FileList | null, role: "measurement" | "validation") {
    if (!files || files.length === 0) return;
    setError(null);
    try {
      const name = files[0].name.replace(/\d*\.csv$/i, "") || role;
      const summary = await api.uploadSet(files, role, {
        name,
        temperature_c: temperature,
        reference: role === "validation" ? reference : undefined,
        molarity: role === "validation" ? molarity : undefined,
      });
      if (role === "measurement") setMeasurements((s) => [...s, summary]);
      else setValidations((s) => [...s, summary]);
    } catch (e) {
      setError(`Upload failed: ${(e as Error).message}`);
    }
  }

  async function run() {
    if (measurements.length === 0) {
      setError("Upload at least one measurement set.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const { id } = await api.createCampaign({
        measurement_set_ids: measurements.map((m) => m.id),
        validation_set_ids: validations.map((v) => v.id),
        temperature_c: temperature,
      });
      setCampaignId(id);
      const result = await api.analyze(id, {
        model: model || null,
        n_poles: poles ? Number(poles) : null,
      });
      setAnalysis(result);
    } catch (e) {
      setError(`Analysis failed: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[360px_1fr]">
      <div className="space-y-6">
        <Card title="Measurement sets" hint="repeats of one sample">
          <SetUploader role="measurement" onFiles={(f) => upload(f, "measurement")} />
          <div className="mt-3 space-y-2">
            {measurements.map((s) => (
              <SetCard key={s.id} s={s} />
            ))}
            {measurements.length === 0 && <Empty>Drop a sample's repeat CSVs here.</Empty>}
          </div>
        </Card>

        <Card title="Validation sets" hint="optional — known reference QC">
          <div className="mb-3 grid grid-cols-2 gap-2">
            <Field label="reference">
              <select
                value={reference}
                onChange={(e) => setReference(e.target.value)}
                className="w-full rounded-lg border border-[var(--color-line)] bg-[var(--color-ink-850)] px-3 py-2 text-sm text-slate-100"
              >
                {["saline", "water", "seawater", "methanol", "ethanol"].map((r) => (
                  <option key={r}>{r}</option>
                ))}
              </select>
            </Field>
            <Field label="molarity (mol/L)">
              <Input
                type="number"
                step="0.01"
                value={molarity}
                onChange={(e) => setMolarity(Number(e.target.value))}
              />
            </Field>
          </div>
          <SetUploader role="validation" onFiles={(f) => upload(f, "validation")} />
          <div className="mt-3 space-y-2">
            {validations.map((s) => (
              <SetCard key={s.id} s={s} />
            ))}
            {validations.length === 0 && (
              <Empty>No validation set → results are labeled “not validated”.</Empty>
            )}
          </div>
        </Card>

        <Card title="Run">
          <div className="grid grid-cols-2 gap-2">
            <Field label="temperature (°C)">
              <Input
                type="number"
                value={temperature}
                onChange={(e) => setTemperature(Number(e.target.value))}
              />
            </Field>
            <Field label="poles (override)">
              <Input
                type="number"
                placeholder="auto"
                value={poles}
                onChange={(e) => setPoles(e.target.value)}
              />
            </Field>
          </div>
          <div className="mt-2">
            <Field label="model (override)">
              <select
                value={model}
                onChange={(e) => setModel(e.target.value)}
                className="w-full rounded-lg border border-[var(--color-line)] bg-[var(--color-ink-850)] px-3 py-2 text-sm text-slate-100"
              >
                {MODEL_OPTIONS.map((m) => (
                  <option key={m} value={m}>
                    {m || "auto-select (recommended)"}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <div className="mt-4">
            <Button onClick={run} disabled={busy}>
              {busy ? "Analysing…" : "Run analysis"}
            </Button>
          </div>
          {error && <p className="mt-3 text-sm text-rose-300">{error}</p>}
        </Card>
      </div>

      <div className="space-y-6">
        {!analysis && <Placeholder />}
        {analysis && (
          <>
            <ValidationBanner status={analysis.validation.status} ok={analysis.validation.validated} />
            {analysis.results.map((r) => (
              <ResultPanel key={r.sample_id} r={r} campaignId={campaignId!} />
            ))}
          </>
        )}
      </div>
    </div>
  );
}

function SetUploader({
  role,
  onFiles,
}: {
  role: string;
  onFiles: (f: FileList | null) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <div
      onClick={() => ref.current?.click()}
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault();
        onFiles(e.dataTransfer.files);
      }}
      className="cursor-pointer rounded-lg border border-dashed border-[var(--color-line)] bg-[var(--color-ink-850)]/50 px-4 py-5 text-center text-sm text-slate-400 transition hover:border-[var(--color-signal)]"
    >
      <input
        ref={ref}
        type="file"
        multiple
        accept=".csv"
        className="hidden"
        onChange={(e) => onFiles(e.target.files)}
      />
      Drop {role} repeat CSVs or click to browse
    </div>
  );
}

function SetCard({ s }: { s: SetSummary }) {
  return (
    <div className="rounded-lg border border-[var(--color-line)] bg-[var(--color-ink-850)] px-3 py-2 text-xs">
      <div className="flex items-center justify-between">
        <span className="font-semibold text-slate-200">{s.name}</span>
        <Badge tone="signal">
          {s.n_used}/{s.n_repeats} repeats
        </Badge>
      </div>
      <div className="tabular mt-1 text-slate-400">
        ε′ {s.eps_real_range[0].toFixed(1)}→{s.eps_real_range[1].toFixed(1)} · σ
        {s.sigma_low_s_per_m.toFixed(2)} S/m · {s.band_ghz[0].toFixed(2)}–{s.band_ghz[1].toFixed(0)} GHz
      </div>
      {s.excluded_indices.length > 0 && (
        <div className="mt-1 text-amber-300">excluded repeat(s): {s.excluded_indices.join(", ")}</div>
      )}
      {s.notes.map((n, i) => (
        <div key={i} className="mt-1 text-teal-300/80">
          ⚠ {n}
        </div>
      ))}
    </div>
  );
}

function ResultPanel({ r, campaignId }: { r: AnalysisResult; campaignId: string }) {
  return (
    <Card
      title={`Sample: ${r.sample_id}`}
      hint={r.overridden ? "model overridden" : "auto-selected"}
    >
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Badge tone="signal">{r.chosen_model}</Badge>
        <Badge tone={r.kk.consistent ? "good" : "danger"}>
          KK {r.kk.consistent ? "consistent" : "inconsistent"} · {(r.kk.residual_rms * 100).toFixed(1)}%
        </Badge>
        {r.closest_materials[0] && (
          <Badge>closest: {r.closest_materials[0].material}</Badge>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div>
          <PanelLabel>Bode</PanelLabel>
          <BodePlot data={r.plot} />
        </div>
        <div>
          <PanelLabel>Cole-Cole</PanelLabel>
          <ColeColePlot data={r.plot} />
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="R²" value={r.r_squared.toFixed(4)} />
        <Stat label="reduced χ²" value={r.chi2_reduced.toPrecision(3)} />
        <Stat label="AICc" value={r.aicc.toPrecision(4)} />
        <Stat label="params" value={String(r.params.length)} />
      </div>

      <div className="mt-4">
        <PanelLabel>Fitted parameters (value ± u)</PanelLabel>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {r.params.map((p) => (
            <div
              key={p.name}
              className="rounded-md border border-[var(--color-line)] bg-[var(--color-ink-850)] px-3 py-2"
            >
              <div className="text-xs text-slate-500">{p.name}</div>
              <div className="tabular text-sm font-semibold text-slate-100">{p.formatted}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-4">
        <PanelLabel>Model selection</PanelLabel>
        <RankingTable r={r} />
        {r.selection_warnings.map((w, i) => (
          <p key={i} className="mt-2 text-xs text-amber-300">
            ⚠ {w}
          </p>
        ))}
      </div>

      <div className="mt-4">
        <PanelLabel>Methods paragraph (paste-ready)</PanelLabel>
        <p className="rounded-lg border border-[var(--color-line)] bg-[var(--color-ink-850)] p-3 text-xs leading-relaxed text-slate-300">
          {r.methods_paragraph}
        </p>
        <div className="mt-3 flex gap-2">
          <a href={api.reportUrl(campaignId, r.sample_id, "pdf")} target="_blank" rel="noreferrer">
            <Button variant="ghost">Download PDF report</Button>
          </a>
          <a href={api.reportUrl(campaignId, r.sample_id, "docx")} target="_blank" rel="noreferrer">
            <Button variant="ghost">Download Word report</Button>
          </a>
          <Button
            variant="subtle"
            onClick={() => navigator.clipboard?.writeText(r.methods_paragraph)}
          >
            Copy methods
          </Button>
        </div>
      </div>
    </Card>
  );
}

function RankingTable({ r }: { r: AnalysisResult }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-[var(--color-line)]">
      <table className="tabular w-full text-xs">
        <thead className="bg-[var(--color-ink-850)] text-slate-400">
          <tr>
            {["model", "k", "χ²ᵣ", "AICc", "ΔAICc", "R²", ""].map((h) => (
              <th key={h} className="px-3 py-2 text-left font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {r.ranking.map((rf) => (
            <tr
              key={rf.label}
              className={`border-t border-[var(--color-line)] ${rf.chosen ? "bg-teal-500/5" : ""}`}
            >
              <td className="px-3 py-1.5 text-slate-200">
                {rf.chosen && <span className="mr-1 text-[var(--color-signal)]">▸</span>}
                {rf.label}
              </td>
              <td className="px-3 py-1.5">{rf.n_params}</td>
              <td className="px-3 py-1.5">{rf.chi2_reduced.toPrecision(3)}</td>
              <td className="px-3 py-1.5">{rf.aicc.toPrecision(4)}</td>
              <td className="px-3 py-1.5">{rf.delta_aicc.toFixed(1)}</td>
              <td className="px-3 py-1.5">{rf.r_squared.toFixed(4)}</td>
              <td className="px-3 py-1.5">
                {rf.flag && (
                  <Badge tone={rf.flag === "degenerate" ? "caution" : "neutral"}>{rf.flag}</Badge>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ValidationBanner({ status, ok }: { status: string; ok: boolean }) {
  return (
    <div
      className={`rounded-xl border px-5 py-3 text-sm font-medium ${
        ok
          ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
          : "border-amber-500/30 bg-amber-500/10 text-amber-200"
      }`}
    >
      {ok ? "✓ " : "⚠ "}
      {status}
    </div>
  );
}

function PanelLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
      {children}
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="text-xs text-slate-600">{children}</p>;
}

function Placeholder() {
  return (
    <Card>
      <div className="flex h-64 flex-col items-center justify-center text-center text-slate-500">
        <div className="text-4xl">⌁</div>
        <p className="mt-3 max-w-sm text-sm">
          Upload a measurement set (and optionally a validation set), then run the analysis. The
          toolkit averages repeats, auto-selects a model, checks Kramers-Kronig causality, compares
          to the literature, and writes a paper-ready report.
        </p>
      </div>
    </Card>
  );
}
