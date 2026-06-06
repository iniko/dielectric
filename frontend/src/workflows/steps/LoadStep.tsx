import { useRef, useState } from "react";
import * as api from "../../api";
import type { SetSummary } from "../../types";
import { Badge, Button, Card, Field, Input } from "../../components/ui";
import { useAnalysis } from "../AnalysisContext";
import { ErrorMsg, Note, PanelLabel, StepIntro } from "./common";

const REFERENCES = ["saline", "water", "seawater", "methanol", "ethanol"];

export default function LoadStep() {
  const { measurements, validations, temperature, setTemperature, addSet, removeSet } =
    useAnalysis();
  return (
    <div>
      <StepIntro title="1 · Load data">
        Stage a sample's repeat CSVs (Agilent 85070 exports), drop any bad file with its ×, then load
        them as a set. The toolkit averages the repeats, screens outliers (k·MAD), and auto-detects the
        positive-loss sign convention at the I/O boundary. Add a validation set of a known reference
        liquid for QC.
      </StepIntro>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card title="Measurement set" hint="repeats of one sample">
          <SetLoader role="measurement" temperature={temperature} onLoaded={addSet} />
          <LoadedList role="measurement" sets={measurements} onRemove={removeSet} />
        </Card>

        <Card title="Validation set" hint="optional — known-reference QC">
          <SetLoader role="validation" temperature={temperature} onLoaded={addSet} />
          <LoadedList role="validation" sets={validations} onRemove={removeSet} />
        </Card>
      </div>

      <div className="mt-6 max-w-xs">
        <Field label="measurement temperature (°C)">
          <Input
            type="number"
            value={temperature}
            onChange={(e) => setTemperature(Number(e.target.value))}
          />
        </Field>
        <Note>
          The temperature is recorded with the campaign and used to flag reference-temperature
          mismatches downstream (water/saline ε_s drifts ≈ −0.4/°C).
        </Note>
      </div>
    </div>
  );
}

function SetLoader({
  role,
  temperature,
  onLoaded,
}: {
  role: "measurement" | "validation";
  temperature: number;
  onLoaded: (s: SetSummary) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [staged, setStaged] = useState<File[]>([]);
  const [name, setName] = useState("");
  const [reference, setReference] = useState("saline");
  const [molarity, setMolarity] = useState(0.154);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function add(files: FileList | null) {
    if (!files || files.length === 0) return;
    const incoming = Array.from(files);
    setStaged((cur) => {
      const seen = new Set(cur.map((f) => f.name));
      const merged = [...cur, ...incoming.filter((f) => !seen.has(f.name))];
      if (!name && merged[0]) setName(merged[0].name.replace(/\d*\.csv$/i, "") || role);
      return merged;
    });
    setError(null);
  }

  async function load() {
    if (staged.length === 0) {
      setError("Stage at least one CSV first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const summary = await api.uploadSet(staged, role, {
        name: name || role,
        temperature_c: temperature,
        reference: role === "validation" ? reference : undefined,
        molarity: role === "validation" ? molarity : undefined,
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
      {role === "validation" && (
        <div className="mb-3 grid grid-cols-2 gap-2">
          <Field label="reference">
            <select
              value={reference}
              onChange={(e) => setReference(e.target.value)}
              className="w-full rounded-lg border border-[var(--color-line)] bg-[var(--color-ink-850)] px-3 py-2 text-sm text-slate-100"
            >
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
        </div>
      )}

      <div
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          add(e.dataTransfer.files);
        }}
        className="cursor-pointer rounded-lg border border-dashed border-[var(--color-line)] bg-[var(--color-ink-850)]/50 px-4 py-5 text-center text-sm text-slate-400 transition hover:border-[var(--color-signal)]"
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".csv"
          className="hidden"
          onChange={(e) => add(e.target.files)}
        />
        Drop {role} repeat CSVs or click to browse
      </div>

      {staged.length > 0 && (
        <div className="mt-3">
          <PanelLabel>Staged files ({staged.length})</PanelLabel>
          <div className="overflow-hidden rounded-lg border border-[var(--color-line)]">
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
          <div className="mt-3 flex items-center gap-2">
            <div className="flex-1">
              <Input
                value={name}
                placeholder="set name"
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <Button onClick={load} disabled={busy}>
              {busy ? "Loading…" : `Load ${role} set`}
            </Button>
          </div>
        </div>
      )}
      {error && <div className="mt-3">{error && <ErrorMsg error={error} />}</div>}
    </div>
  );
}

function LoadedList({
  role,
  sets,
  onRemove,
}: {
  role: "measurement" | "validation";
  sets: SetSummary[];
  onRemove: (role: "measurement" | "validation", id: string) => void;
}) {
  if (sets.length === 0) {
    return (
      <p className="mt-3 text-xs text-slate-600">
        {role === "measurement"
          ? "No measurement set loaded yet."
          : "No validation set → results are labeled “not validated”."}
      </p>
    );
  }
  return (
    <div className="mt-3 space-y-2">
      {sets.map((s) => (
        <div
          key={s.id}
          className="rounded-lg border border-[var(--color-line)] bg-[var(--color-ink-850)] px-3 py-2 text-xs"
        >
          <div className="flex items-center justify-between">
            <span className="font-semibold text-slate-200">{s.name}</span>
            <div className="flex items-center gap-2">
              <Badge tone="signal">
                {s.n_used}/{s.n_repeats} repeats
              </Badge>
              <button
                type="button"
                aria-label={`unload ${s.name}`}
                onClick={() => onRemove(role, s.id)}
                className="rounded px-1.5 text-slate-500 hover:bg-rose-500/10 hover:text-rose-300"
              >
                ✕
              </button>
            </div>
          </div>
          <div className="tabular mt-1 text-slate-400">
            ε′ {s.eps_real_range[0].toFixed(1)}→{s.eps_real_range[1].toFixed(1)} · σ{" "}
            {s.sigma_low_s_per_m.toFixed(2)} S/m · {s.band_ghz[0].toFixed(2)}–
            {s.band_ghz[1].toFixed(0)} GHz
          </div>
          {s.excluded_indices.length > 0 && (
            <div className="mt-1 text-amber-300">
              auto-excluded: {(s.excluded_filenames.length ? s.excluded_filenames : s.excluded_indices.map((i) => `#${i + 1}`)).join(", ")}{" "}
              <span className="text-slate-500">(see Repeats step to review/override)</span>
            </div>
          )}
          {s.notes.map((n, i) => (
            <div key={i} className="mt-1 text-teal-300/80">
              ⚠ {n}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
