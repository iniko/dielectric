import { useEffect, useState } from "react";
import * as api from "../../api";
import type { BatchDifference, BatchSummary, ParamDiff } from "../../types";
import { Badge, Button, Card } from "../../components/ui";
import { BatchOverlayPlot, DiffPlot, type OverlaySeries } from "../../components/Plots";
import { toLoss, usePreferences } from "../../preferences";
import { useAnalysis } from "../AnalysisContext";
import { ErrorMsg, Loading, Note, PanelLabel, StepIntro, useAsync } from "./common";

export default function CompareStep() {
  const { measurements, ensureFit, fitReq, temperature } = useAnalysis();
  const { lossMode } = usePreferences();
  const [baseline, setBaseline] = useState("");

  const key = JSON.stringify([fitReq, measurements.map((m) => m.id), temperature, baseline]);
  const { data, loading, error } = useAsync(async () => {
    const fit = await ensureFit(); // ensure every batch is fit + cached before comparing
    return api.compareCampaign(fit.campaign_id, baseline || undefined);
  }, [key]);

  // Sync the selector to the resolved baseline once the first response lands.
  useEffect(() => {
    if (!baseline && data) setBaseline(data.baseline);
  }, [data, baseline]);

  const selectCls =
    "rounded-lg border border-[var(--color-line)] bg-[var(--color-ink-850)] px-3 py-2 text-sm text-slate-100";

  const series: OverlaySeries[] = (data?.batches ?? []).map((b: BatchSummary) => ({
    name: b.sample_id,
    frequency_hz: b.band.frequency_hz,
    eps_real: b.band.eps_real,
    loss: b.band.sigma.map((s, i) => toLoss(s, b.band.frequency_hz[i])),
  }));

  return (
    <div>
      <StepIntro title="7 · Compare batches">
        Overlay the loaded batches and test whether they differ — the "normal vs diseased" question.
        Differences are computed against a baseline batch: per-frequency Δε′ and Δσ with a 95%-CI
        significance band, and z-scores on robust derived parameters (ε_s, ε∞, dominant τ, σ_DC). This
        is descriptive — many points are tested, so read the significance as a guide, not a corrected
        test.
      </StepIntro>

      <div className="mb-5 flex items-center gap-3">
        <span className="text-xs uppercase tracking-wider text-slate-500">baseline batch</span>
        <select value={baseline} onChange={(e) => setBaseline(e.target.value)} className={selectCls}>
          {measurements.map((m) => (
            <option key={m.id} value={m.name}>
              {m.name}
            </option>
          ))}
        </select>
      </div>

      {loading && <Loading what="Comparing batches…" />}
      {error && <ErrorMsg error={error} />}

      {data && (
        <>
          <div className="mb-5 flex flex-wrap items-center gap-2">
            <span className="text-xs uppercase tracking-wider text-slate-500">
              comparison report
            </span>
            {(["html", "pdf", "docx"] as const).map((fmt) => (
              <a
                key={fmt}
                href={api.compareReportUrl(data.campaign_id, data.baseline, fmt)}
                target="_blank"
                rel="noreferrer"
              >
                <Button variant="ghost">{fmt.toUpperCase()}</Button>
              </a>
            ))}
          </div>

          <Card title="Overlay" hint={`${data.batches.length} batches`}>
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
              <div>
                <PanelLabel>Real permittivity ε′</PanelLabel>
                <BatchOverlayPlot series={series} field="eps" />
              </div>
              <div>
                <PanelLabel>{lossMode === "sigma" ? "Conductivity σ" : "Loss ε″"}</PanelLabel>
                <BatchOverlayPlot series={series} field="lossy" mode={lossMode} />
              </div>
              <div>
                <PanelLabel>Cole-Cole</PanelLabel>
                <BatchOverlayPlot series={series} field="argand" />
              </div>
            </div>
            <ParamMatrix batches={data.batches} />
          </Card>

          {data.differences.map((d) => (
            <DifferencePanel key={d.sample_id} diff={d} lossMode={lossMode} />
          ))}
        </>
      )}
    </div>
  );
}

function ParamMatrix({ batches }: { batches: BatchSummary[] }) {
  const rows: { label: string; get: (b: BatchSummary) => string }[] = [
    { label: "model", get: (b) => b.model },
    { label: "ε_s", get: (b) => `${b.params.eps_static.toFixed(2)} ± ${b.params.eps_static_u.toFixed(2)}` },
    { label: "ε∞", get: (b) => `${b.params.eps_inf.toFixed(2)} ± ${b.params.eps_inf_u.toFixed(2)}` },
    {
      label: "τ (ps)",
      get: (b) =>
        `${(b.params.tau_dominant_s * 1e12).toFixed(2)} ± ${(b.params.tau_dominant_u * 1e12).toFixed(2)}`,
    },
    {
      label: "σ_DC (S/m)",
      get: (b) =>
        b.params.sigma_dc != null
          ? `${b.params.sigma_dc.toFixed(3)} ± ${(b.params.sigma_dc_u ?? 0).toFixed(3)}`
          : "–",
    },
  ];
  return (
    <div className="mt-4 overflow-x-auto rounded-lg border border-[var(--color-line)]">
      <table className="tabular w-full text-xs">
        <thead className="bg-[var(--color-ink-850)] text-slate-400">
          <tr>
            <th className="px-3 py-2 text-left font-medium">parameter</th>
            {batches.map((b) => (
              <th key={b.sample_id} className="px-3 py-2 text-left font-medium">
                {b.sample_id}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label} className="border-t border-[var(--color-line)]">
              <td className="px-3 py-1.5 text-slate-400">{r.label}</td>
              {batches.map((b) => (
                <td key={b.sample_id} className="px-3 py-1.5 text-slate-200">
                  {r.get(b)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DifferencePanel({
  diff,
  lossMode,
}: {
  diff: BatchDifference;
  lossMode: "sigma" | "loss";
}) {
  const f = diff.spectrum.frequency_hz;
  const lossyDelta =
    lossMode === "sigma" ? diff.spectrum.delta_sigma : diff.spectrum.delta_sigma.map((v, i) => toLoss(v, f[i]));
  const lossySe =
    lossMode === "sigma" ? diff.spectrum.se_sigma : diff.spectrum.se_sigma.map((v, i) => toLoss(v, f[i]));
  const fracEps = diff.spectrum.significant_eps.filter(Boolean).length / (f.length || 1);

  return (
    <Card
      className="mt-6"
      title={`${diff.sample_id} − ${diff.baseline}`}
      hint="A − baseline"
    >
      <Verdict diff={diff} fracEps={fracEps} />

      <div className="mt-3 grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div>
          <PanelLabel>Δε′ (with 95% CI; significant points marked)</PanelLabel>
          <DiffPlot
            frequency={f}
            delta={diff.spectrum.delta_eps_real}
            se={diff.spectrum.se_eps_real}
            significant={diff.spectrum.significant_eps}
            yTitle="Δε′"
          />
        </div>
        <div>
          <PanelLabel>{lossMode === "sigma" ? "Δσ (S/m)" : "Δε″"}</PanelLabel>
          <DiffPlot
            frequency={f}
            delta={lossyDelta}
            se={lossySe}
            significant={diff.spectrum.significant_sigma}
            yTitle={lossMode === "sigma" ? "Δσ (S/m)" : "Δε″"}
          />
        </div>
      </div>

      <div className="mt-4">
        <PanelLabel>Parameter differences (z = |Δ| / √(uₐ²+u_b²))</PanelLabel>
        <ParamDiffTable params={diff.params} />
      </div>

      {diff.spectrum.notes.map((n, i) => (
        <p key={i} className="mt-2 text-xs text-amber-300">
          ⚠ {n}
        </p>
      ))}
      <Note>
        Significance is per-frequency (95% CI of the two means separating) and per-parameter
        (z ≥ 1.96); with many frequencies tested, treat it as a guide, not a multiplicity-corrected
        test.
      </Note>
    </Card>
  );
}

const PARAM_LABEL: Record<string, string> = {
  eps_static: "ε_s",
  eps_inf: "ε∞",
  tau_dominant: "τ (ps)",
  sigma_dc: "σ_DC (S/m)",
};

function fmtParam(p: ParamDiff): { a: string; b: string; delta: string } {
  const scale = p.name === "tau_dominant" ? 1e12 : 1;
  const dp = p.name === "sigma_dc" ? 3 : 2;
  return {
    a: `${(p.a * scale).toFixed(dp)} ± ${(p.ua * scale).toFixed(dp)}`,
    b: `${(p.b * scale).toFixed(dp)} ± ${(p.ub * scale).toFixed(dp)}`,
    delta: (p.delta * scale).toFixed(dp),
  };
}

function ParamDiffTable({ params }: { params: ParamDiff[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-[var(--color-line)]">
      <table className="tabular w-full text-xs">
        <thead className="bg-[var(--color-ink-850)] text-slate-400">
          <tr>
            {["parameter", "batch A", "baseline", "Δ", "z", ""].map((h) => (
              <th key={h} className="px-3 py-2 text-left font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {params.map((p) => {
            const v = fmtParam(p);
            return (
              <tr
                key={p.name}
                className={`border-t border-[var(--color-line)] ${p.significant ? "bg-rose-500/5" : ""}`}
              >
                <td className="px-3 py-1.5 text-slate-400">{PARAM_LABEL[p.name] ?? p.name}</td>
                <td className="px-3 py-1.5 text-slate-200">{v.a}</td>
                <td className="px-3 py-1.5 text-slate-200">{v.b}</td>
                <td className="px-3 py-1.5">{v.delta}</td>
                <td className="px-3 py-1.5">{Number.isFinite(p.z) ? p.z.toFixed(2) : "–"}</td>
                <td className="px-3 py-1.5">
                  {p.significant && <Badge tone="danger">differs</Badge>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Verdict({ diff, fracEps }: { diff: BatchDifference; fracEps: number }) {
  const sig = diff.params.filter((p) => p.significant).map((p) => PARAM_LABEL[p.name] ?? p.name);
  const pct = Math.round(fracEps * 100);
  const ok = sig.length > 0 || fracEps > 0.1;
  return (
    <div
      className={`rounded-lg border px-4 py-2 text-sm ${
        ok
          ? "border-rose-500/30 bg-rose-500/10 text-rose-200"
          : "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
      }`}
    >
      {ok ? (
        <>
          Difference detected: {sig.length > 0 ? `${sig.join(", ")} differ` : "parameters comparable"}
          {`; ε′ separates over ${pct}% of the band.`}
        </>
      ) : (
        <>No significant difference: parameters comparable and ε′ separates over only {pct}% of the band.</>
      )}
    </div>
  );
}
