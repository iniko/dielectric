import { useEffect, useState } from "react";
import * as api from "../../api";
import type { SetSummary, ValidationDetailOut } from "../../types";
import { Badge, Card, Field, Input, Stat } from "../../components/ui";
import { ReferenceOverlayPlot } from "../../components/Plots";
import { massPercentFromMolarity, molarityFromMassPercent } from "../../saline";
import { usePreferences } from "../../preferences";
import { useAnalysis } from "../AnalysisContext";
import { ErrorMsg, Loading, Note, PanelLabel, StepIntro, useAsync } from "./common";

const REFERENCES = ["saline", "water", "seawater", "methanol", "ethanol"];

export default function ValidationStep() {
  const { measurements, validations, validationLinks, ensureAnalysis, fitReq, temperature, validationVersion } =
    useAnalysis();
  const key = JSON.stringify([
    fitReq,
    measurements.map((m) => m.id),
    validations.map((v) => v.id),
    temperature,
    validationVersion,
  ]);
  const { data: analysis, loading, error } = useAsync(() => ensureAnalysis(), [key]);

  return (
    <div>
      <StepIntro title="5 · Validation (QC)">
        Each batch's attached validation set is compared to its reference's literature model
        (ε′ and σ_DC separately). The reference is editable here — switch standard, or enter saline by
        molarity or mass % — and the verdict, overlay, banner, and report update live. The campaign is
        validated only if every linked QC set passes.
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
        {measurements.map((batch) => (
          <BatchValidation
            key={batch.id}
            batch={batch}
            linked={validations.filter((v) => validationLinks[v.id] === batch.id)}
          />
        ))}
      </div>
    </div>
  );
}

function BatchValidation({ batch, linked }: { batch: SetSummary; linked: SetSummary[] }) {
  return (
    <Card title={`Batch: ${batch.name}`} hint={linked.length ? `${linked.length} validation(s)` : ""}>
      {linked.length === 0 ? (
        <p className="text-sm text-slate-400">
          No validation attached to this batch. Go to step 1 to attach repeats of a known reference
          liquid — the campaign is reported <b>not validated</b> until every batch's QC passes.
        </p>
      ) : (
        <div className="space-y-6">
          {linked.map((v) => (
            <ValidationCard key={v.id} set={v} batchId={batch.id} />
          ))}
        </div>
      )}
    </Card>
  );
}

interface Form {
  reference: string;
  temperature_c: number;
  molarity: number;
  salinity_psu: number;
  salineMode: "molarity" | "percent";
}

function ValidationCard({ set, batchId }: { set: SetSummary; batchId: string }) {
  const { lossMode } = usePreferences();
  const { bumpValidation, validationVersion } = useAnalysis();
  const { data, loading, error } = useAsync(
    () => api.getValidation(set.id),
    [set.id, validationVersion],
  );
  const [form, setForm] = useState<Form | null>(null);
  const [busy, setBusy] = useState(false);

  // seed the form from the stored config (keep the UI-only saline mode across refetches)
  useEffect(() => {
    if (!data) return;
    setForm((prev) => ({
      reference: data.config.reference,
      temperature_c: data.config.temperature_c,
      molarity: data.config.molarity ?? 0.154,
      salinity_psu: data.config.salinity_psu ?? 35,
      salineMode: prev?.salineMode ?? "molarity",
    }));
  }, [data]);

  async function apply(next: Form) {
    setForm(next);
    setBusy(true);
    try {
      await api.setValidationConfig(set.id, {
        reference: next.reference,
        molarity: next.reference === "saline" ? next.molarity : null,
        salinity_psu: next.reference === "seawater" ? next.salinity_psu : null,
        temperature_c: next.temperature_c,
        measurement_set_ids: [batchId],
      });
      bumpValidation(); // refetch this card + banner/report
    } finally {
      setBusy(false);
    }
  }

  const selectCls =
    "w-full rounded-lg border border-[var(--color-line)] bg-[var(--color-ink-850)] px-3 py-2 text-sm text-slate-100";

  return (
    <div className="rounded-lg border border-[var(--color-line)] bg-[var(--color-ink-850)]/50 p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="font-semibold text-slate-200">{set.name}</span>
        {data && (
          <Badge tone={data.verdict.passed ? "good" : "danger"}>
            {data.verdict.passed ? "PASS" : "FAIL"}
          </Badge>
        )}
        {data && <Badge>{data.reference_label}</Badge>}
        {data?.confidence === "VERIFY" && <Badge tone="caution">VERIFY ref</Badge>}
      </div>

      {form && (
        <div className="mb-4 grid grid-cols-1 gap-2 sm:grid-cols-3">
          <Field label="reference">
            <select
              value={form.reference}
              disabled={busy}
              onChange={(e) => apply({ ...form, reference: e.target.value })}
              className={selectCls}
            >
              {REFERENCES.map((r) => (
                <option key={r}>{r}</option>
              ))}
            </select>
          </Field>
          {form.reference === "saline" && <SalineInput form={form} busy={busy} apply={apply} />}
          {form.reference === "seawater" && (
            <Field label="salinity (PSU)">
              <Input
                type="number"
                disabled={busy}
                value={form.salinity_psu}
                onChange={(e) => apply({ ...form, salinity_psu: Number(e.target.value) })}
              />
            </Field>
          )}
          <Field label="temperature (°C)">
            <Input
              type="number"
              disabled={busy}
              value={form.temperature_c}
              onChange={(e) => apply({ ...form, temperature_c: Number(e.target.value) })}
            />
          </Field>
        </div>
      )}

      {loading && !data && <Loading what="Comparing to reference…" />}
      {error && <ErrorMsg error={error} />}
      {data && <ValidationResult data={data} mode={lossMode} />}
    </div>
  );
}

function SalineInput({
  form,
  busy,
  apply,
}: {
  form: Form;
  busy: boolean;
  apply: (f: Form) => void;
}) {
  const isPct = form.salineMode === "percent";
  const value = isPct ? massPercentFromMolarity(form.molarity) : form.molarity;
  return (
    <Field label={isPct ? "NaCl (% w/w)" : "molarity (mol/L)"}>
      <div className="flex gap-1">
        <Input
          type="number"
          step={isPct ? "0.1" : "0.01"}
          disabled={busy}
          value={Number(value.toFixed(4))}
          onChange={(e) => {
            const v = Number(e.target.value);
            apply({ ...form, molarity: isPct ? molarityFromMassPercent(v) : v });
          }}
        />
        <button
          type="button"
          onClick={() =>
            apply({ ...form, salineMode: isPct ? "molarity" : "percent" })
          }
          className="shrink-0 rounded-lg border border-[var(--color-line)] px-2 text-xs text-slate-300 hover:border-[var(--color-signal)]"
          title="toggle molarity / mass %"
        >
          {isPct ? "%" : "M"}
        </button>
      </div>
    </Field>
  );
}

function ValidationResult({ data, mode }: { data: ValidationDetailOut; mode: "sigma" | "loss" }) {
  return (
    <>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <Stat label="ε′ rel RMS" value={(data.verdict.eps_real_rms * 100).toFixed(2)} unit="%" />
        <Stat label="σ measured" value={data.verdict.sigma_measured.toFixed(3)} unit="S/m" />
        <Stat label="σ reference" value={data.verdict.sigma_reference.toFixed(3)} unit="S/m" />
      </div>
      <div className="mt-4">
        <PanelLabel>Measured vs {data.reference_label}</PanelLabel>
        <ReferenceOverlayPlot overlay={data.overlay} mode={mode} />
      </div>
      {data.verdict.notes.map((n, i) => (
        <p key={i} className="mt-2 text-xs text-amber-300">
          ⚠ {n}
        </p>
      ))}
      {data.saline_sweep && data.saline_sweep.length > 0 && (
        <div className="mt-4">
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
                {data.saline_sweep.slice(0, 6).map((row, i) => (
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
          <Note>The closest (molarity, temperature) pair is highlighted — confirms the standard used.</Note>
        </div>
      )}
    </>
  );
}
