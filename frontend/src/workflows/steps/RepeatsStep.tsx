import { useState } from "react";
import * as api from "../../api";
import type { RepeatsOut, ScreeningRequest, SetSummary } from "../../types";
import { Badge, Card, Input } from "../../components/ui";
import { RepeatBandPlot } from "../../components/Plots";
import { usePreferences } from "../../preferences";
import { useAnalysis } from "../AnalysisContext";
import { ErrorMsg, Loading, Note, PanelLabel, StepIntro, useAsync } from "./common";

export default function RepeatsStep() {
  const { measurements } = useAnalysis();
  return (
    <div>
      <StepIntro title="2 · Repeat statistics">
        Type A combination of the repeats into a complex mean with a per-frequency 95% confidence band
        (mean ± 1.96·SEM). Every repeat's outlier z-score is shown so the exclusion is fully transparent
        — you can adjust the threshold, keep all repeats, or override the decision per repeat.
      </StepIntro>
      <div className="space-y-6">
        {measurements.map((s) => (
          <RepeatPanel key={s.id} set={s} />
        ))}
      </div>
    </div>
  );
}

function RepeatPanel({ set }: { set: SetSummary }) {
  const [freqText, setFreqText] = useState("");
  const [freqs, setFreqs] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const { lossMode } = usePreferences();
  const { screeningVersion, bumpScreening } = useAnalysis();
  const { data, loading, error } = useAsync(
    () => api.getRepeats(set.id, freqs),
    [set.id, freqs.join(","), screeningVersion],
  );

  function applyFreqs() {
    setFreqs(
      freqText
        .split(",")
        .map((x) => Number(x.trim()))
        .filter((x) => Number.isFinite(x) && x > 0),
    );
  }

  async function apply(next: ScreeningRequest) {
    setBusy(true);
    try {
      await api.setScreening(set.id, next);
      bumpScreening(); // refetch this panel + invalidate downstream fit/compare/report
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title={`Sample: ${set.name}`} hint={`${set.n_used}/${set.n_repeats} repeats kept`}>
      {loading && <Loading what="Combining repeats…" />}
      {error && <ErrorMsg error={error} />}
      {data && data.screening && (
        <>
          <ScreeningControls data={data} busy={busy} onApply={apply} />
          <RepeatTable data={data} busy={busy} onApply={apply} />
          {data.impact && <ImpactReadout data={data} />}

          <div className="mt-5 grid grid-cols-1 gap-4 xl:grid-cols-2">
            <div>
              <PanelLabel>Real permittivity ε′ (mean + 95% band)</PanelLabel>
              <RepeatBandPlot band={data.band} quantity="eps" />
            </div>
            <div>
              <PanelLabel>
                {lossMode === "sigma"
                  ? "Effective conductivity σ (mean + 95% band)"
                  : "Dielectric loss ε″ (mean + 95% band)"}
              </PanelLabel>
              <RepeatBandPlot band={data.band} quantity={lossMode === "sigma" ? "sigma" : "loss"} />
            </div>
          </div>

          <DistributionInspector
            data={data}
            freqText={freqText}
            setFreqText={setFreqText}
            applyFreqs={applyFreqs}
          />
        </>
      )}
    </Card>
  );
}

function ScreeningControls({
  data,
  busy,
  onApply,
}: {
  data: RepeatsOut;
  busy: boolean;
  onApply: (r: ScreeningRequest) => void;
}) {
  const sc = data.screening!;
  const keepAll = sc.outlier_k === null;
  const base = (): ScreeningRequest => ({
    outlier_k: sc.outlier_k,
    manual_exclude: sc.manual_exclude,
    manual_keep: sc.manual_keep,
  });
  return (
    <div className="mb-4 rounded-lg border border-[var(--color-line)] bg-[var(--color-ink-850)] p-4">
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-2">
          <span className="text-xs uppercase tracking-wider text-slate-500">threshold k</span>
          <div className="w-24">
            <Input
              type="number"
              step="0.5"
              min="1"
              disabled={keepAll || busy}
              value={keepAll ? "" : String(sc.outlier_k ?? 3.5)}
              placeholder="3.5"
              onChange={(e) => onApply({ ...base(), outlier_k: Number(e.target.value) || 3.5 })}
            />
          </div>
        </div>
        <label className="flex items-center gap-2 text-sm text-slate-300">
          <input
            type="checkbox"
            checked={keepAll}
            disabled={busy}
            onChange={(e) =>
              onApply({ ...base(), outlier_k: e.target.checked ? null : 3.5 })
            }
          />
          keep all repeats (disable screening)
        </label>
        <Badge tone={sc.n_excluded > 0 ? "caution" : "good"}>
          {sc.n_used}/{sc.n_total} kept · {sc.n_excluded} excluded
        </Badge>
      </div>
      {keepAll && (
        <p className="mt-2 rounded border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-xs text-amber-200">
          ⚠ Outlier screening is OFF — a bad probe contact or mis-calibrated repeat will bias the mean
          and shrink the SEM. Re-enable unless you have inspected every repeat.
        </p>
      )}
      <Note>
        Method: {sc.method}. Citation: {sc.citation}.
      </Note>
    </div>
  );
}

function RepeatTable({
  data,
  busy,
  onApply,
}: {
  data: RepeatsOut;
  busy: boolean;
  onApply: (r: ScreeningRequest) => void;
}) {
  const sc = data.screening!;
  const k = sc.outlier_k ?? 3.5;
  const without = (xs: number[], i: number) => xs.filter((x) => x !== i);

  function toggleExclude(i: number) {
    const has = sc.manual_exclude.includes(i);
    onApply({
      outlier_k: sc.outlier_k,
      manual_exclude: has ? without(sc.manual_exclude, i) : [...sc.manual_exclude, i],
      manual_keep: without(sc.manual_keep, i),
    });
  }
  function toggleKeep(i: number) {
    const has = sc.manual_keep.includes(i);
    onApply({
      outlier_k: sc.outlier_k,
      manual_keep: has ? without(sc.manual_keep, i) : [...sc.manual_keep, i],
      manual_exclude: without(sc.manual_exclude, i),
    });
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-[var(--color-line)]">
      <table className="tabular w-full text-xs">
        <thead className="bg-[var(--color-ink-850)] text-slate-400">
          <tr>
            {["#", "file", "z-score", "", "status", "override"].map((h) => (
              <th key={h} className="px-3 py-2 text-left font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.repeats.map((r) => {
            const frac = Math.min(Math.abs(r.zscore) / (k * 1.2), 1);
            return (
              <tr
                key={r.index}
                className={`border-t border-[var(--color-line)] ${r.kept ? "" : "bg-rose-500/5"}`}
              >
                <td className="px-3 py-1.5 text-slate-500">{r.index + 1}</td>
                <td className="px-3 py-1.5 text-slate-200">{r.filename}</td>
                <td className="px-3 py-1.5">{r.zscore.toFixed(2)}</td>
                <td className="px-3 py-1.5" style={{ width: 90 }}>
                  <div className="h-1.5 w-20 rounded bg-[var(--color-ink-800)]">
                    <div
                      className={`h-1.5 rounded ${r.kept ? "bg-teal-400/70" : "bg-rose-400/80"}`}
                      style={{ width: `${frac * 100}%` }}
                    />
                  </div>
                </td>
                <td className="px-3 py-1.5">
                  <span className={r.kept ? "text-slate-300" : "text-rose-300"}>{r.reason}</span>
                </td>
                <td className="px-3 py-1.5">
                  <div className="flex gap-1">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => toggleKeep(r.index)}
                      className={`rounded px-1.5 py-0.5 text-[11px] ${
                        sc.manual_keep.includes(r.index)
                          ? "bg-teal-500/20 text-teal-200"
                          : "border border-[var(--color-line)] text-slate-400 hover:text-slate-100"
                      }`}
                    >
                      keep
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => toggleExclude(r.index)}
                      className={`rounded px-1.5 py-0.5 text-[11px] ${
                        sc.manual_exclude.includes(r.index)
                          ? "bg-rose-500/20 text-rose-200"
                          : "border border-[var(--color-line)] text-slate-400 hover:text-slate-100"
                      }`}
                    >
                      exclude
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ImpactReadout({ data }: { data: RepeatsOut }) {
  const im = data.impact!;
  const dEps = im.eps_real_with - im.eps_real_without;
  const dSig = im.sigma_with - im.sigma_without;
  const f = (im.frequency_ref_hz / 1e9).toFixed(2);
  return (
    <div className="mt-3 rounded-lg border border-[var(--color-line)] bg-[var(--color-ink-850)] px-4 py-2 text-xs text-slate-300">
      <span className="font-semibold text-slate-200">Impact of exclusion</span> (at {f} GHz): ε′{" "}
      {im.eps_real_without.toFixed(2)} → {im.eps_real_with.toFixed(2)} (Δ {dEps.toFixed(2)}), σ{" "}
      {im.sigma_without.toFixed(3)} → {im.sigma_with.toFixed(3)} S/m (Δ {dSig.toFixed(3)}); max |Δε′|
      over the band {im.max_abs_d_eps_real.toFixed(2)}.
    </div>
  );
}

function DistributionInspector({
  data,
  freqText,
  setFreqText,
  applyFreqs,
}: {
  data: RepeatsOut;
  freqText: string;
  setFreqText: (s: string) => void;
  applyFreqs: () => void;
}) {
  return (
    <div className="mt-5">
      <PanelLabel>Distribution inspector</PanelLabel>
      <div className="flex items-center gap-2">
        <div className="flex-1">
          <Input
            value={freqText}
            placeholder="frequencies in GHz, e.g. 1, 5, 10"
            onChange={(e) => setFreqText(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && applyFreqs()}
          />
        </div>
        <button
          type="button"
          onClick={applyFreqs}
          className="rounded-lg border border-[var(--color-line)] px-3 py-2 text-sm text-slate-200 hover:border-[var(--color-signal)]"
        >
          Inspect
        </button>
      </div>
      {data.distributions.length > 0 && (
        <div className="mt-3 overflow-x-auto rounded-lg border border-[var(--color-line)]">
          <table className="tabular w-full text-xs">
            <thead className="bg-[var(--color-ink-850)] text-slate-400">
              <tr>
                {["f (GHz)", "ε′ mean", "ε′ std", "Shapiro p (ε′)", "ε″ mean", "ε″ std", "Shapiro p (ε″)"].map(
                  (h) => (
                    <th key={h} className="px-3 py-2 text-left font-medium">
                      {h}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {data.distributions.map((d) => (
                <tr key={d.frequency_hz} className="border-t border-[var(--color-line)]">
                  <td className="px-3 py-1.5">{(d.frequency_hz / 1e9).toFixed(2)}</td>
                  <td className="px-3 py-1.5">{d.eps_real_mean.toFixed(3)}</td>
                  <td className="px-3 py-1.5">{d.eps_real_std.toFixed(3)}</td>
                  <td className={`px-3 py-1.5 ${d.shapiro_p_real < 0.05 ? "text-amber-300" : ""}`}>
                    {fmtP(d.shapiro_p_real)}
                  </td>
                  <td className="px-3 py-1.5">{d.eps_imag_mean.toFixed(3)}</td>
                  <td className="px-3 py-1.5">{d.eps_imag_std.toFixed(3)}</td>
                  <td className={`px-3 py-1.5 ${d.shapiro_p_imag < 0.05 ? "text-amber-300" : ""}`}>
                    {fmtP(d.shapiro_p_imag)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Note>
        A Shapiro-Wilk p below 0.05 (amber) suggests the repeat scatter is not Gaussian at that
        frequency — interpret the SEM-based band with care there.
      </Note>
    </div>
  );
}

function fmtP(p: number): string {
  return Number.isFinite(p) ? p.toFixed(3) : "–";
}
