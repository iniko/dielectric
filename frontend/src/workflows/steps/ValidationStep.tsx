import * as api from "../../api";
import type { SetSummary, ValidationVerdict } from "../../types";
import { Badge, Card, Stat } from "../../components/ui";
import { ReferenceOverlayPlot } from "../../components/Plots";
import { usePreferences } from "../../preferences";
import { useAnalysis } from "../AnalysisContext";
import { ErrorMsg, Loading, Note, PanelLabel, StepIntro, useAsync } from "./common";

export default function ValidationStep() {
  const { validations, temperature, ensureAnalysis, fitReq, measurements } = useAnalysis();
  const key = JSON.stringify([fitReq, measurements.map((m) => m.id), validations.map((v) => v.id)]);
  const { data: analysis, loading, error } = useAsync(() => ensureAnalysis(), [key]);

  if (validations.length === 0) {
    return (
      <div>
        <StepIntro title="5 · Validation (QC)">Known-reference quality control.</StepIntro>
        <Card>
          <p className="text-sm text-slate-400">
            No validation set was loaded, so the campaign is reported <b>not validated</b>. Go back to
            step 1 to add repeat measurements of a known reference liquid (e.g. 0.154 M saline) to
            confirm the probe/inversion chain.
          </p>
        </Card>
      </div>
    );
  }

  // verdicts are keyed by the validation set's sample name (set.name), not the upload UUID.
  const verdictFor = (name: string): ValidationVerdict | undefined =>
    analysis?.validation.verdicts.find((v) => v.set_id === name);

  return (
    <div>
      <StepIntro title="5 · Validation (QC)">
        Each validation set's Type A mean is compared to its declared reference's literature model,
        assessing ε′ and σ_DC separately. The campaign is validated only if every QC set passes. The
        saline sweep helps confirm which standard the data actually match.
      </StepIntro>

      {loading && <Loading what="Validating…" />}
      {error && <ErrorMsg error={error} />}
      {analysis && (
        <div
          className={`mb-6 rounded-xl border px-5 py-3 text-sm font-medium ${
            analysis.validation.validated
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
              : "border-amber-500/30 bg-amber-500/10 text-amber-200"
          }`}
        >
          {analysis.validation.validated ? "✓ " : "⚠ "}
          {analysis.validation.status}
        </div>
      )}

      <div className="space-y-6">
        {validations.map((s) => (
          <ValidationPanel key={s.id} set={s} temperature={temperature} verdict={verdictFor(s.name)} />
        ))}
      </div>
    </div>
  );
}

function ValidationPanel({
  set,
  temperature,
  verdict,
}: {
  set: SetSummary;
  temperature: number;
  verdict?: ValidationVerdict;
}) {
  const { lossMode } = usePreferences();
  const reference = set.reference ?? "saline";
  const isSaline = reference === "saline";
  const { data, loading, error } = useAsync(
    () =>
      api.referenceMatch(set.id, {
        reference,
        temperature_c: temperature,
        molarity: set.molarity ?? undefined,
      }),
    [set.id, reference, temperature, set.molarity],
  );
  const sweep = useAsync(() => (isSaline ? api.salineSweep(set.id) : Promise.resolve(null)), [
    set.id,
    isSaline,
  ]);

  return (
    <Card title={`Validation: ${set.name}`} hint={reference}>
      {verdict && (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Badge tone={verdict.passed ? "good" : "danger"}>
            {verdict.passed ? "PASS" : "FAIL"}
          </Badge>
          <Badge>{verdict.reference}</Badge>
        </div>
      )}
      {loading && <Loading what="Comparing to reference…" />}
      {error && <ErrorMsg error={error} />}
      {data && (
        <>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Stat label="ε′ rel RMS" value={(data.eps_real_rms * 100).toFixed(2)} unit="%" />
            <Stat label="max |Δε′|" value={data.max_abs_d_eps_real.toFixed(2)} />
            <Stat label="max |Δε″|" value={data.max_abs_d_loss.toFixed(2)} />
            <Stat label="combined RMS" value={data.rms.toFixed(3)} />
          </div>
          <div className="mt-4">
            <PanelLabel>Measured vs reference</PanelLabel>
            <ReferenceOverlayPlot overlay={data.overlay} mode={lossMode} />
          </div>
          {data.notes.map((n, i) => (
            <p key={i} className="mt-2 text-xs text-amber-300">
              ⚠ {n}
            </p>
          ))}
        </>
      )}

      {isSaline && sweep.data && (
        <div className="mt-5">
          <PanelLabel>Saline best-match sweep (molarity × temperature)</PanelLabel>
          <div className="overflow-x-auto rounded-lg border border-[var(--color-line)]">
            <table className="tabular w-full text-xs">
              <thead className="bg-[var(--color-ink-850)] text-slate-400">
                <tr>
                  {["molarity (M)", "T (°C)", "combined RMS", "ε′ rel RMS"].map((h) => (
                    <th key={h} className="px-3 py-2 text-left font-medium">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sweep.data.rows.slice(0, 6).map((row, i) => (
                  <tr
                    key={`${row.molarity}-${row.temperature_c}`}
                    className={`border-t border-[var(--color-line)] ${i === 0 ? "bg-teal-500/5" : ""}`}
                  >
                    <td className="px-3 py-1.5">
                      {i === 0 && <span className="mr-1 text-[var(--color-signal)]">▸</span>}
                      {row.molarity}
                    </td>
                    <td className="px-3 py-1.5">{row.temperature_c}</td>
                    <td className="px-3 py-1.5">{row.rms.toFixed(4)}</td>
                    <td className="px-3 py-1.5">{(row.eps_real_rms * 100).toFixed(2)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Note>
            The closest (molarity, temperature) pair is highlighted — useful for confirming a
            validation liquid was prepared as intended rather than, say, 0.1 M instead of 0.154 M.
          </Note>
        </div>
      )}
    </Card>
  );
}
