import { useState } from "react";
import type { FitResultOut } from "../../types";
import { Badge, Card, Field, Input, Stat } from "../../components/ui";
import { BodePlot, ColeColePlot, ResidualPlot } from "../../components/Plots";
import { usePreferences } from "../../preferences";
import { useAnalysis } from "../AnalysisContext";
import { ErrorMsg, Loading, Note, PanelLabel, StepIntro, useAsync } from "./common";

const MODEL_OPTIONS = [
  "",
  "Debye",
  "Cole-Cole",
  "Cole-Davidson",
  "Havriliak-Negami",
  "Jonscher",
  "Cole-Cole + DC σ",
  "MultiPole(N=2) + DC σ",
  "MultiPole(N=3) + DC σ",
];

export default function FitStep() {
  const { fitReq, setFitReq, ensureFit, measurements, validations, temperature } = useAnalysis();
  const key = JSON.stringify([
    fitReq,
    measurements.map((m) => m.id),
    validations.map((v) => v.id),
    temperature,
  ]);
  const { data, loading, error } = useAsync(() => ensureFit(), [key]);

  const selectCls =
    "w-full rounded-lg border border-[var(--color-line)] bg-[var(--color-ink-850)] px-3 py-2 text-sm text-slate-100";

  return (
    <div>
      <StepIntro title="3 · Model fit">
        Candidates are fit by weighted non-linear least squares and ranked by AICc/BIC on N = 2·n_freq.
        The most parsimonious model that fits comparably well and stays identifiable is recommended —
        you can override the family, pole count, or DC-σ term. Degenerate/over-parameterised fits are
        flagged rather than silently chosen.
      </StepIntro>

      <Card title="Customize the model">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Field label="model family">
            <select
              value={fitReq.model}
              onChange={(e) => setFitReq({ ...fitReq, model: e.target.value })}
              className={selectCls}
            >
              {MODEL_OPTIONS.map((m) => (
                <option key={m} value={m}>
                  {m || "auto-select (recommended)"}
                </option>
              ))}
            </select>
          </Field>
          <Field label="relaxation poles">
            <Input
              type="number"
              min={1}
              max={3}
              placeholder="auto"
              value={fitReq.poles}
              onChange={(e) => setFitReq({ ...fitReq, poles: e.target.value })}
            />
          </Field>
          <Field label="DC conductivity term">
            <select
              value={fitReq.dcSigma}
              onChange={(e) =>
                setFitReq({ ...fitReq, dcSigma: e.target.value as "" | "on" | "off" })
              }
              className={selectCls}
            >
              <option value="">model default</option>
              <option value="on">include DC σ</option>
              <option value="off">exclude DC σ</option>
            </select>
          </Field>
        </div>
        <Note>
          An explicit model family overrides the DC-σ toggle. Add poles only when a one-pole fit leaves
          visible residual structure — most saline/tissue spectra at 0.2–20 GHz need a single
          (water-relaxation) pole.
        </Note>
      </Card>

      <div className="mt-6 space-y-6">
        {loading && <Loading what="Fitting candidate models…" />}
        {error && <ErrorMsg error={error} />}
        {data?.results.map((r) => <FitPanel key={r.sample_id} r={r} />)}
      </div>
    </div>
  );
}

function FitPanel({ r }: { r: FitResultOut }) {
  const { lossMode } = usePreferences();
  const [residNorm, setResidNorm] = useState(true);
  return (
    <Card
      title={`Sample: ${r.sample_id}`}
      hint={r.overridden ? "model overridden" : "auto-selected"}
    >
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Badge tone="signal">{r.chosen_model}</Badge>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div>
          <PanelLabel>Bode (data + fit)</PanelLabel>
          <BodePlot data={r.plot} mode={lossMode} />
        </div>
        <div>
          <PanelLabel>Cole-Cole</PanelLabel>
          <ColeColePlot data={r.plot} />
        </div>
      </div>

      <div className="mt-4">
        <div className="mb-2 flex items-center justify-between">
          <PanelLabel>Residuals</PanelLabel>
          <div className="flex gap-0.5 rounded-lg border border-[var(--color-line)] bg-[var(--color-ink-900)] p-0.5">
            {[
              { k: true, label: "normalized" },
              { k: false, label: "raw" },
            ].map((o) => (
              <button
                key={o.label}
                type="button"
                onClick={() => setResidNorm(o.k)}
                className={`rounded-md px-2.5 py-1 text-xs font-semibold transition ${
                  residNorm === o.k
                    ? "bg-[var(--color-signal)] text-ink-950"
                    : "text-slate-400 hover:text-slate-100"
                }`}
              >
                {o.label}
              </button>
            ))}
          </div>
        </div>
        <ResidualPlot residual={r.residual} mode={lossMode} normalized={residNorm} />
        {residNorm && (
          <p className="mt-1 text-xs text-slate-500">
            Standardized residuals (residual ÷ per-point Type A σ); a good weighted fit scatters within
            the ±2σ band, and Σ(pull²) equals the reduced χ² shown above × dof.
          </p>
        )}
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
        <PanelLabel>Model selection ranking</PanelLabel>
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
        {r.selection_warnings.map((w, i) => (
          <p key={i} className="mt-2 text-xs text-amber-300">
            ⚠ {w}
          </p>
        ))}
      </div>
    </Card>
  );
}
