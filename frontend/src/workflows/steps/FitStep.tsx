import { useRef, useState } from "react";
import type { FitResultOut } from "../../types";
import { Badge, Card, Field, Input, Stat } from "../../components/ui";
import { BodePlot, ColeColePlot, ResidualPlot } from "../../components/Plots";
import { usePreferences } from "../../preferences";
import { useAnalysis } from "../AnalysisContext";
import { ErrorMsg, Loading, Note, PanelLabel, StepIntro, useAsync, useDebounced } from "./common";

// Unit of a fitted parameter by name prefix (tau_1, sigma_dc, …); "" = dimensionless.
function paramUnit(name: string): string {
  if (name === "tau" || name.startsWith("tau_")) return "s";
  if (name.startsWith("sigma")) return "S/m";
  return "";
}

// Model family is chosen on its own; pole count and the DC-σ term compose with it. The dropdown
// lists pure families (value = family name, "" = auto) annotated with their shape.
const FAMILY_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "auto-select (recommended)" },
  { value: "Debye", label: "Debye — unbroadened single relaxation" },
  { value: "Cole-Cole", label: "Cole-Cole — symmetric broadening" },
  { value: "Cole-Davidson", label: "Cole-Davidson — asymmetric broadening" },
  { value: "Havriliak-Negami", label: "Havriliak-Negami — general broadening" },
  { value: "Jonscher", label: "Jonscher — universal power law" },
];
// Only these families support a pole ladder (N>1) and a composable DC-σ term ("" = auto).
const LADDER = ["", "Debye", "Cole-Cole"];

export default function FitStep() {
  const { fitReq, setFitReq, ensureFit, measurements, validations, temperature } = useAnalysis();
  const polesValid = fitReq.poles.trim() === "" || /^[1-3]$/.test(fitReq.poles.trim());
  const rawKey = JSON.stringify([
    fitReq,
    measurements.map((m) => m.id),
    validations.map((v) => v.id),
    temperature,
  ]);
  const debouncedKey = useDebounced(rawKey, 500);
  // Advance the fetch key only once the inputs have settled AND are valid — the useAsync dep is
  // always a real request key (never an "invalid" sentinel), so invalid input never fetches.
  const fetchKeyRef = useRef(rawKey);
  if (debouncedKey === rawKey && polesValid) fetchKeyRef.current = rawKey;
  const { data, loading, error } = useAsync(() => ensureFit(), [fetchKeyRef.current]);
  const stale = loading || error !== null;
  const isLadder = LADDER.includes(fitReq.model); // family supports poles + a composable DC term

  // Choosing a non-ladder family clears poles/DC so a non-composable request is never sent.
  function setFamily(model: string) {
    setFitReq(
      LADDER.includes(model) ? { ...fitReq, model } : { ...fitReq, model, poles: "", dcSigma: "" },
    );
  }

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
              onChange={(e) => setFamily(e.target.value)}
              className={selectCls}
            >
              {FAMILY_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="relaxation poles">
            <Input
              type="number"
              min={1}
              max={3}
              placeholder="1 (auto ladders)"
              value={fitReq.poles}
              disabled={!isLadder}
              onChange={(e) => setFitReq({ ...fitReq, poles: e.target.value })}
              className="disabled:opacity-40"
            />
            {!polesValid && (
              <p className="mt-1 text-xs text-amber-300">1–3, blank = auto — fit not updated.</p>
            )}
          </Field>
          <Field label="DC conductivity term">
            <select
              value={fitReq.dcSigma}
              onChange={(e) =>
                setFitReq({ ...fitReq, dcSigma: e.target.value as "" | "on" | "off" })
              }
              disabled={!isLadder}
              className={`${selectCls} disabled:opacity-40`}
            >
              <option value="">auto (no constraint)</option>
              <option value="on">include DC σ</option>
              <option value="off">exclude DC σ</option>
            </select>
          </Field>
        </div>
        <Note>
          These settings apply to <b>all loaded batches</b> and <b>compose</b>: a family, a pole
          count, and the DC-σ term combine into one model (e.g. <i>Cole-Cole (2 poles) + DC σ</i>).
          Poles and the DC-σ term apply only to the Debye and Cole-Cole families (the others are
          single-pole shapes without a conductivity term). With the family on <i>auto</i>, a pole
          count ladders both Debye and Cole-Cole at that count, and the DC-σ choice constrains the
          candidate panel. Most saline/tissue spectra at 0.2–20 GHz need a single
          (water-relaxation) pole plus conductivity.
        </Note>
      </Card>

      <div className="mt-6 space-y-6">
        {loading && <Loading what="Fitting candidate models…" />}
        {error && <ErrorMsg error={error} />}
        {data && error && !loading && (
          <div>
            <Badge tone="caution">showing the last successful fit — the latest request failed</Badge>
          </div>
        )}
        {data && (
          <div className={stale ? "space-y-6 opacity-40 transition-opacity" : "space-y-6"}>
            {data.results.map((r) => (
              <FitPanel key={r.sample_id} r={r} />
            ))}
          </div>
        )}
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
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Badge tone="signal">{r.chosen_model}</Badge>
        {r.structure && <span className="text-xs text-slate-400">{r.structure}</span>}
      </div>
      {r.equation && (
        <p className="tabular mb-2 text-xs text-slate-500">{r.equation}</p>
      )}
      {!r.overridden && r.rationale && (
        <p className="mb-4 text-xs leading-relaxed text-slate-400">{r.rationale}</p>
      )}

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
            Standardized residuals (residual ÷ per-point Type A standard uncertainty u); a good
            weighted fit scatters within the ±2 band, and Σ(pull²) equals the reduced χ² shown
            below × dof. Quoted parameter uncertainties assume the model describes the data within
            u (they are not rescaled by χ²ᵣ).
            {r.chi2_reduced > 5 && (
              <span className="text-amber-300">
                {" "}Here reduced χ² = {r.chi2_reduced.toPrecision(3)} ≫ 1 — the model misfit
                exceeds the Type A uncertainty, so those uncertainties may be optimistic by ~√χ²ᵣ ≈{" "}
                {Math.sqrt(r.chi2_reduced).toFixed(1)}×.
              </span>
            )}
          </p>
        )}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="R²" value={r.r_squared.toFixed(4)} />
        <Stat label="reduced χ²" value={r.chi2_reduced.toPrecision(3)} />
        <Stat label="AICc" value={r.aicc.toPrecision(4)} />
        <Stat label="params" value={String(r.params.length)} />
      </div>
      <p className="mt-2 text-xs leading-relaxed text-slate-500">
        R² is computed on the stacked real + imaginary residuals (per-component ε′ / ε″:{" "}
        {r.r_squared_real.toFixed(3)} / {r.r_squared_imag.toFixed(3)}; component R² can be negative).
        It measures variance explained against the large structural variation in the data (dispersion
        amplitude in ε′, conduction tail in ε″), so values near 1 do <b>not</b> imply agreement
        within the measurement uncertainty — judge adequacy from the standardized residuals and the
        per-component mean squared pull (ε′ / ε″: {r.msp_real.toFixed(2)} / {r.msp_imag.toFixed(2)};
        ≈ 1 means a fit within Type A uncertainty).
      </p>

      <div className="mt-4">
        <PanelLabel>Fitted parameters (value ± standard uncertainty, k = 1)</PanelLabel>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {r.params.map((p) => (
            <div
              key={p.name}
              className="rounded-md border border-[var(--color-line)] bg-[var(--color-ink-850)] px-3 py-2"
            >
              <div className="text-xs text-slate-500">
                {p.name}
                {paramUnit(p.name) && <span className="text-slate-600"> ({paramUnit(p.name)})</span>}
              </div>
              <div className="tabular text-sm font-semibold text-slate-100">
                {p.formatted}
                {paramUnit(p.name) && (
                  <span className="ml-1 font-normal text-slate-400">{paramUnit(p.name)}</span>
                )}
              </div>
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
                {["model", "k", "χ²ᵣ", "AICc", "ΔAICc", "BIC", "R²", "flags"].map((h) => (
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
                  title={rf.excluded_reason || undefined}
                  className={`border-t border-[var(--color-line)] ${rf.chosen ? "bg-teal-500/5" : ""}`}
                >
                  <td className="px-3 py-1.5 text-slate-200">
                    {rf.chosen && <span className="mr-1 text-[var(--color-signal)]">▸</span>}
                    {rf.recommended && !rf.chosen && (
                      <span className="mr-1 text-slate-400" title="parsimony-aware auto-recommendation">
                        ○
                      </span>
                    )}
                    {rf.label}
                  </td>
                  <td className="px-3 py-1.5">{rf.n_params}</td>
                  <td className="px-3 py-1.5">{rf.chi2_reduced.toPrecision(3)}</td>
                  <td className="px-3 py-1.5">{rf.aicc.toPrecision(4)}</td>
                  <td className="px-3 py-1.5">{rf.delta_aicc.toFixed(1)}</td>
                  <td className="px-3 py-1.5">{rf.bic.toPrecision(4)}</td>
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
        <p className="mt-1 text-xs text-slate-600">
          ▸ chosen{r.ranking.some((rf) => rf.recommended && !rf.chosen) && " · ○ auto-recommendation"}
          {" · "}AICc/BIC on N = 2·n_freq = {2 * r.residual.frequency_hz.length}; dof = N − k
        </p>
        {r.selection_warnings.map((w, i) => (
          <p key={i} className="mt-2 text-xs text-amber-300">
            ⚠ {w}
          </p>
        ))}
      </div>
    </Card>
  );
}
