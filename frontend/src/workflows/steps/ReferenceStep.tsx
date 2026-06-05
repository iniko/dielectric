import { useEffect, useState } from "react";
import * as api from "../../api";
import type { AnalysisResult, MaterialOut, SetSummary } from "../../types";
import { Badge, Card, Stat } from "../../components/ui";
import { ReferenceOverlayPlot, SeriesPlot } from "../../components/Plots";
import { usePreferences } from "../../preferences";
import { useAnalysis } from "../AnalysisContext";
import { ErrorMsg, Loading, Note, PanelLabel, StepIntro, useAsync } from "./common";

const LIQUIDS = ["saline", "water", "seawater", "methanol", "ethanol"];

export default function ReferenceStep() {
  const { measurements, temperature, ensureAnalysis, fitReq } = useAnalysis();
  const [materials, setMaterials] = useState<MaterialOut[]>([]);
  useEffect(() => {
    api.getMaterials().then(setMaterials).catch(() => setMaterials([]));
  }, []);

  const key = JSON.stringify([fitReq, measurements.map((m) => m.id), temperature]);
  const { data: analysis, loading, error } = useAsync(() => ensureAnalysis(), [key]);

  const tissues = materials.filter((m) => m.material_class === "tissue").map((m) => m.name);
  const options = [...LIQUIDS, ...tissues];

  // analysis results are keyed by sample name (set.name), not the upload UUID (set.id).
  const resultFor = (name: string): AnalysisResult | undefined =>
    analysis?.results.find((r) => r.sample_id === name);

  return (
    <div>
      <StepIntro title="6 · Reference match">
        Descriptive goodness-of-match of each sample against the literature database. The closest
        materials are ranked by relative-RMS distance; pick any reference to overlay it and inspect the
        per-frequency error. A low error does <b>not</b> validate the measurement — a literature model
        is a population average at a fixed temperature, not ground truth.
      </StepIntro>

      {loading && <Loading what="Ranking reference materials…" />}
      {error && <ErrorMsg error={error} />}
      <div className="space-y-6">
        {measurements.map((s) => (
          <ReferencePanel
            key={s.id}
            set={s}
            temperature={temperature}
            options={options}
            result={resultFor(s.name)}
          />
        ))}
      </div>
    </div>
  );
}

function ReferencePanel({
  set,
  temperature,
  options,
  result,
}: {
  set: SetSummary;
  temperature: number;
  options: string[];
  result?: AnalysisResult;
}) {
  const { lossMode } = usePreferences();
  const closest = result?.closest_materials ?? [];
  const [reference, setReference] = useState<string>("");

  // Default the picker to the closest material once the analysis arrives.
  useEffect(() => {
    if (!reference && closest[0]) setReference(closest[0].material);
  }, [closest, reference]);

  const { data, loading, error } = useAsync(
    () =>
      reference
        ? api.referenceMatch(set.id, { reference, temperature_c: temperature })
        : Promise.resolve(null),
    [set.id, reference, temperature],
  );

  const selectCls =
    "w-full rounded-lg border border-[var(--color-line)] bg-[var(--color-ink-850)] px-3 py-2 text-sm text-slate-100";

  return (
    <Card title={`Sample: ${set.name}`}>
      {closest.length > 0 && (
        <div className="mb-4">
          <PanelLabel>Closest materials</PanelLabel>
          <div className="flex flex-wrap gap-2">
            {closest.map((c, i) => (
              <Badge key={c.material} tone={i === 0 ? "signal" : "neutral"}>
                {c.material} · d={c.distance.toFixed(3)}
                {c.confidence === "VERIFY" ? " · VERIFY" : ""}
              </Badge>
            ))}
          </div>
        </div>
      )}

      <div className="max-w-xs">
        <PanelLabel>Compare against</PanelLabel>
        <select value={reference} onChange={(e) => setReference(e.target.value)} className={selectCls}>
          {!reference && <option value="">select a reference…</option>}
          {options.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      </div>

      {loading && <Loading what="Comparing…" />}
      {error && <ErrorMsg error={error} />}
      {data && (
        <div className="mt-4">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Stat label="combined RMS" value={data.rms.toFixed(3)} />
            <Stat label="mean rel error" value={data.mean_rel_error_pct.toFixed(1)} unit="%" />
            <Stat label="NRMSE" value={data.nrmse.toFixed(3)} />
            <Stat label="confidence" value={data.confidence} />
          </div>
          <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
            <div>
              <PanelLabel>Measured vs {data.reference_label}</PanelLabel>
              <ReferenceOverlayPlot overlay={data.overlay} mode={lossMode} />
            </div>
            <div>
              <PanelLabel>Per-frequency relative error</PanelLabel>
              <SeriesPlot
                x={data.overlay.frequency_hz}
                y={data.overlay.rel_error_pct}
                yTitle="relative error (%)"
              />
            </div>
          </div>
          {data.notes.map((n, i) => (
            <p key={i} className="mt-2 text-xs text-amber-300">
              ⚠ {n}
            </p>
          ))}
          {data.confidence === "VERIFY" && (
            <Note>
              This reference is VERIFY-confidence (assembled offline). Confirm its parameters against
              IFAC/IT'IS before citing the comparison.
            </Note>
          )}
        </div>
      )}
    </Card>
  );
}
