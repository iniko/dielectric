import { useState } from "react";
import * as api from "../../api";
import type { SetSummary } from "../../types";
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
        (mean ± 1.96·SEM). Repeats flagged by the k·MAD outlier screen are excluded from the mean and
        listed. Use the distribution inspector to check whether the scatter at a frequency is Gaussian
        before quoting a Type A uncertainty.
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
  const { lossMode } = usePreferences();
  const { data, loading, error } = useAsyncRepeats(set.id, freqs);

  function applyFreqs() {
    const parsed = freqText
      .split(",")
      .map((x) => Number(x.trim()))
      .filter((x) => Number.isFinite(x) && x > 0);
    setFreqs(parsed);
  }

  return (
    <Card title={`Sample: ${set.name}`} hint={`${set.n_used}/${set.n_repeats} repeats kept`}>
      {loading && <Loading what="Combining repeats…" />}
      {error && <ErrorMsg error={error} />}
      {data && (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Badge tone="signal">k = {data.coverage_k} (≈95%)</Badge>
            {data.excluded_indices.length > 0 ? (
              <Badge tone="caution">excluded repeats: {data.excluded_indices.join(", ")}</Badge>
            ) : (
              <Badge tone="good">no outlier repeats</Badge>
            )}
          </div>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
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
        </>
      )}
    </Card>
  );
}

function fmtP(p: number): string {
  return Number.isFinite(p) ? p.toFixed(3) : "–";
}

function useAsyncRepeats(setId: string, freqs: number[]) {
  const key = freqs.join(",");
  return useAsync(() => api.getRepeats(setId, freqs), [setId, key]);
}
