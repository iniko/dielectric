import { useRef, useState } from "react";
import * as api from "../../api";
import type { SetSummary } from "../../types";
import { Badge, Button, Card, Field, Input } from "../../components/ui";
import { useAnalysis } from "../AnalysisContext";
import { ErrorMsg, Note, PanelLabel, StepIntro } from "./common";

const REFERENCES = ["saline", "water", "seawater", "methanol", "ethanol"];

export default function LoadStep() {
  const { measurements, temperature, setTemperature, addSet } = useAnalysis();
  return (
    <div>
      <StepIntro title="1 · Load batches">
        Each <b>batch</b> is one sample's repeat CSVs (Agilent 85070 exports). Load a batch, then
        optionally attach a validation set (repeats of a known reference liquid) to it — the validation
        then belongs to that batch. Load two or more batches to compare them later.
      </StepIntro>

      <Card title="New batch" hint="measurement repeats of one sample">
        <BatchLoader temperature={temperature} onLoaded={addSet} />
      </Card>

      <div className="mt-6 space-y-4">
        {measurements.map((b) => (
          <BatchCard key={b.id} batch={b} temperature={temperature} />
        ))}
        {measurements.length === 0 && (
          <p className="text-xs text-slate-600">No batch loaded yet.</p>
        )}
      </div>

      <div className="mt-6 max-w-xs">
        <Field label="measurement temperature (°C)">
          <Input
            type="number"
            value={temperature}
            onChange={(e) => setTemperature(Number(e.target.value))}
          />
        </Field>
        <Note>Recorded with the campaign and used to flag reference-temperature mismatches.</Note>
      </div>
    </div>
  );
}

// A drag/drop + click staging zone with a per-file × table.
function Staging({
  role,
  staged,
  setStaged,
}: {
  role: string;
  staged: File[];
  setStaged: (f: File[] | ((c: File[]) => File[])) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  function add(files: FileList | null) {
    if (!files) return;
    const incoming = Array.from(files);
    setStaged((cur) => {
      const seen = new Set(cur.map((f) => f.name));
      return [...cur, ...incoming.filter((f) => !seen.has(f.name))];
    });
  }
  return (
    <div>
      <div
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          add(e.dataTransfer.files);
        }}
        className="cursor-pointer rounded-lg border border-dashed border-[var(--color-line)] bg-[var(--color-ink-850)]/50 px-4 py-4 text-center text-sm text-slate-400 transition hover:border-[var(--color-signal)]"
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".csv"
          className="hidden"
          onChange={(e) => add(e.target.files)}
        />
        Drop {role} CSVs or click to browse
      </div>
      {staged.length > 0 && (
        <div className="mt-2 overflow-hidden rounded-lg border border-[var(--color-line)]">
          <table className="w-full text-xs">
            <tbody>
              {staged.map((f) => (
                <tr key={f.name} className="border-b border-[var(--color-line)] last:border-0">
                  <td className="px-3 py-1.5 text-slate-200">{f.name}</td>
                  <td className="tabular px-3 py-1.5 text-right text-slate-500">
                    {(f.size / 1024).toFixed(1)} kB
                  </td>
                  <td className="px-2 py-1.5 text-right">
                    <button
                      type="button"
                      aria-label={`remove ${f.name}`}
                      onClick={() => setStaged((cur) => cur.filter((g) => g.name !== f.name))}
                      className="rounded px-1.5 text-slate-500 hover:bg-rose-500/10 hover:text-rose-300"
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function BatchLoader({
  temperature,
  onLoaded,
}: {
  temperature: number;
  onLoaded: (s: SetSummary) => void;
}) {
  const [staged, setStaged] = useState<File[]>([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    if (staged.length === 0) {
      setError("Stage at least one CSV first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const auto = staged[0].name.replace(/\d*\.csv$/i, "") || "batch";
      const summary = await api.uploadSet(staged, "measurement", {
        name: name || auto,
        temperature_c: temperature,
      });
      onLoaded(summary);
      setStaged([]);
      setName("");
    } catch (e) {
      setError(`Load failed: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <Staging role="measurement" staged={staged} setStaged={setStaged} />
      {staged.length > 0 && (
        <div className="mt-3 flex items-center gap-2">
          <div className="flex-1">
            <Input value={name} placeholder="batch name" onChange={(e) => setName(e.target.value)} />
          </div>
          <Button onClick={load} disabled={busy}>
            {busy ? "Loading…" : "Load batch"}
          </Button>
        </div>
      )}
      {error && <div className="mt-2">{<ErrorMsg error={error} />}</div>}
    </div>
  );
}

function SetMeta({ s }: { s: SetSummary }) {
  return (
    <div className="tabular mt-1 text-slate-400">
      ε′ {s.eps_real_range[0].toFixed(1)}→{s.eps_real_range[1].toFixed(1)} · σ{" "}
      {s.sigma_low_s_per_m.toFixed(2)} S/m · {s.band_ghz[0].toFixed(2)}–
      {s.band_ghz[1].toFixed(0)} GHz · {s.n_used}/{s.n_repeats} repeats
    </div>
  );
}

function BatchCard({ batch, temperature }: { batch: SetSummary; temperature: number }) {
  const { removeSet, validations, validationLinks, detachValidation } = useAnalysis();
  const attached = validations.filter((v) => validationLinks[v.id] === batch.id);
  return (
    <Card title={`Batch: ${batch.name}`} hint={`${batch.n_used}/${batch.n_repeats} repeats`}>
      <div className="flex items-start justify-between">
        <SetMeta s={batch} />
        <button
          type="button"
          aria-label={`remove ${batch.name}`}
          onClick={() => removeSet("measurement", batch.id)}
          className="rounded px-1.5 text-slate-500 hover:bg-rose-500/10 hover:text-rose-300"
        >
          ✕
        </button>
      </div>
      {batch.excluded_indices.length > 0 && (
        <div className="mt-1 text-xs text-amber-300">
          auto-excluded:{" "}
          {(batch.excluded_filenames.length
            ? batch.excluded_filenames
            : batch.excluded_indices.map((i) => `#${i + 1}`)
          ).join(", ")}
        </div>
      )}
      {batch.notes.map((n, i) => (
        <div key={i} className="mt-1 text-xs text-teal-300/80">
          ⚠ {n}
        </div>
      ))}

      {attached.length > 0 && (
        <div className="mt-3 space-y-1">
          <PanelLabel>Attached validation</PanelLabel>
          {attached.map((v) => (
            <div
              key={v.id}
              className="flex items-center justify-between rounded-md border border-[var(--color-line)] bg-[var(--color-ink-850)] px-3 py-1.5 text-xs"
            >
              <span className="text-slate-200">
                {v.name} <Badge tone="signal">{v.reference ?? "saline"}</Badge>
              </span>
              <button
                type="button"
                aria-label={`detach ${v.name}`}
                onClick={() => detachValidation(v.id)}
                className="rounded px-1.5 text-slate-500 hover:bg-rose-500/10 hover:text-rose-300"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}

      <AttachValidation batch={batch} temperature={temperature} />
    </Card>
  );
}

function AttachValidation({ batch, temperature }: { batch: SetSummary; temperature: number }) {
  const { attachValidation } = useAnalysis();
  const [open, setOpen] = useState(false);
  const [staged, setStaged] = useState<File[]>([]);
  const [reference, setReference] = useState("saline");
  const [molarity, setMolarity] = useState(0.154);
  const [salinity, setSalinity] = useState(35);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectCls =
    "w-full rounded-lg border border-[var(--color-line)] bg-[var(--color-ink-850)] px-3 py-2 text-sm text-slate-100";

  async function attach() {
    if (staged.length === 0) {
      setError("Stage validation CSVs first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const v = await api.uploadSet(staged, "validation", {
        name: `${batch.name} · ${reference}`,
        temperature_c: temperature,
        reference,
        molarity: reference === "saline" ? molarity : undefined,
        salinity_psu: reference === "seawater" ? salinity : undefined,
      });
      await api.setValidationConfig(v.id, {
        reference,
        molarity: reference === "saline" ? molarity : null,
        salinity_psu: reference === "seawater" ? salinity : null,
        temperature_c: temperature,
        measurement_set_ids: [batch.id],
      });
      attachValidation(v, batch.id);
      setStaged([]);
      setOpen(false);
    } catch (e) {
      setError(`Attach failed: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="mt-3 rounded-lg border border-dashed border-[var(--color-line)] px-3 py-1.5 text-xs text-slate-400 hover:border-[var(--color-signal)] hover:text-slate-100"
      >
        + Attach validation (optional)
      </button>
    );
  }

  return (
    <div className="mt-3 rounded-lg border border-[var(--color-line)] bg-[var(--color-ink-850)]/60 p-3">
      <PanelLabel>Attach validation to this batch</PanelLabel>
      <div className="mb-2 grid grid-cols-2 gap-2">
        <Field label="reference">
          <select value={reference} onChange={(e) => setReference(e.target.value)} className={selectCls}>
            {REFERENCES.map((r) => (
              <option key={r}>{r}</option>
            ))}
          </select>
        </Field>
        {reference === "saline" && (
          <Field label="molarity (mol/L)">
            <Input
              type="number"
              step="0.01"
              value={molarity}
              onChange={(e) => setMolarity(Number(e.target.value))}
            />
          </Field>
        )}
        {reference === "seawater" && (
          <Field label="salinity (PSU)">
            <Input
              type="number"
              value={salinity}
              onChange={(e) => setSalinity(Number(e.target.value))}
            />
          </Field>
        )}
      </div>
      <Staging role="validation" staged={staged} setStaged={setStaged} />
      <div className="mt-2 flex gap-2">
        <Button onClick={attach} disabled={busy}>
          {busy ? "Attaching…" : "Attach validation"}
        </Button>
        <Button variant="subtle" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>
      {error && <div className="mt-2">{<ErrorMsg error={error} />}</div>}
    </div>
  );
}
