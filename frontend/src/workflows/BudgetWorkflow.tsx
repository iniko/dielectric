import { useEffect, useRef, useState } from "react";
// The factory entry's types are declared in shims.d.ts.
import createPlotlyComponent from "react-plotly.js/factory";
import Plotly from "plotly.js-dist-min";
import * as api from "../api";
import type { BudgetComponentIn, BudgetResult, SetSummary } from "../types";
import { Badge, Button, Card, Field, Input, Stat } from "../components/ui";

const Plot = createPlotlyComponent(Plotly);

// How a row's value is interpreted: a standard uncertainty u directly, or a half-width ±a
// converted with the GUM Type B divisor (rectangular a/√3, triangular a/√6).
type EntryMode = "standard" | "rectangular" | "triangular";

interface BudgetRow {
  name: string;
  mode: EntryMode;
  value: string; // string state so blank/invalid entries are representable (and rejected)
  c: string; // sensitivity coefficient cᵢ = ∂(measurand)/∂xᵢ
  dof: string; // "" = ∞
  kind: "A" | "B";
}

const DIVISOR: Record<EntryMode, number> = {
  standard: 1,
  rectangular: Math.sqrt(3),
  triangular: Math.sqrt(6),
};
const DIVISOR_LABEL: Record<EntryMode, string> = {
  standard: "u",
  rectangular: "a/√3",
  triangular: "a/√6",
};

// Tolerate a comma decimal separator (some OS locales render/type "0,67").
function parseNum(s: string): number | null {
  const t = s.trim().replace(",", ".");
  if (t === "") return null;
  const v = Number(t);
  return Number.isFinite(v) ? v : null;
}

function standardU(r: BudgetRow): number | null {
  const v = parseNum(r.value);
  return v !== null && v >= 0 ? v / DIVISOR[r.mode] : null;
}

function rowError(r: BudgetRow): string | null {
  if (standardU(r) === null) return "enter a finite value ≥ 0 (absolute ε′ units)";
  if (parseNum(r.c) === null) return "c must be a finite number";
  if (r.dof.trim() === "") {
    if (r.kind === "A") return "Type A must state finite ν (n repeats − 1)";
  } else {
    const nu = parseNum(r.dof);
    if (nu === null || nu <= 0) return "ν must be > 0 — leave blank for ∞";
  }
  return null;
}

function toComponent(r: BudgetRow): BudgetComponentIn {
  return {
    name: r.name,
    standard_uncertainty: standardU(r) ?? 0,
    sensitivity: parseNum(r.c) ?? 1,
    dof: r.dof.trim() === "" ? null : parseNum(r.dof),
    kind: r.kind,
  };
}

const DEFAULT_NOMINAL = "58";
const DEFAULT_MEASURAND = "ε'";
const DEFAULT_ROWS: BudgetRow[] = [
  { name: "repeatability (Type A)", mode: "standard", value: "0.67", c: "1", dof: "13", kind: "A" },
  { name: "model-fit uncertainty", mode: "standard", value: "0.8", c: "1", dof: "", kind: "B" },
  { name: "probe calibration", mode: "standard", value: "1.16", c: "1", dof: "", kind: "B" },
  { name: "temperature", mode: "standard", value: "0.42", c: "1", dof: "", kind: "B" },
  { name: "data inversion (instrument/probe software)", mode: "standard", value: "1.74", c: "1", dof: "", kind: "B" },
];
const EXAMPLE_SIG = JSON.stringify([DEFAULT_NOMINAL, DEFAULT_MEASURAND, DEFAULT_ROWS]);

interface BudgetFile {
  version: number;
  measurand: string;
  nominal: string;
  rows: BudgetRow[];
}

function parseBudgetFile(text: string): BudgetFile | null {
  try {
    const o = JSON.parse(text) as Partial<BudgetFile>;
    if (o.version !== 1 || typeof o.measurand !== "string" || typeof o.nominal !== "string")
      return null;
    if (!Array.isArray(o.rows)) return null;
    const rows: BudgetRow[] = o.rows.map((r: Partial<BudgetRow>) => ({
      name: String(r.name ?? ""),
      mode: r.mode === "rectangular" || r.mode === "triangular" ? r.mode : "standard",
      value: String(r.value ?? ""),
      c: String(r.c ?? "1"),
      dof: String(r.dof ?? ""),
      kind: r.kind === "A" ? "A" : "B",
    }));
    return { version: 1, measurand: o.measurand, nominal: o.nominal, rows };
  } catch {
    return null;
  }
}

const selectCls =
  "rounded bg-[var(--color-ink-800)] px-1 py-1 text-xs text-slate-200 outline-none";
const numCls =
  "tabular rounded bg-[var(--color-ink-800)] px-2 py-1 text-sm text-slate-100 outline-none";

const ROW_GRID = "grid grid-cols-[1fr_84px_104px_52px_70px_56px_24px] items-center gap-2";

export default function BudgetWorkflow() {
  const [nominal, setNominal] = useState(DEFAULT_NOMINAL);
  const [measurand, setMeasurand] = useState(DEFAULT_MEASURAND);
  const [rows, setRows] = useState<BudgetRow[]>(DEFAULT_ROWS);
  const [result, setResult] = useState<BudgetResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [computedSig, setComputedSig] = useState<string | null>(null);
  // import-from-batch UI
  const [batches, setBatches] = useState<SetSummary[] | null>(null);
  const [importId, setImportId] = useState("");
  const [importMsg, setImportMsg] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const signature = JSON.stringify([nominal, measurand, rows]);
  const isExample = signature === EXAMPLE_SIG;
  const stale = result !== null && computedSig !== signature;
  const canCompute =
    rows.length > 0 && rows.every((r) => rowError(r) === null) && parseNum(nominal) !== null;

  async function compute() {
    const sig = signature; // capture before the await
    setError(null);
    try {
      const res = await api.computeBudget({
        measurand,
        nominal_value: parseNum(nominal) ?? 0,
        unit: "",
        coverage_level: 0.95,
        components: rows.map(toComponent),
      });
      setResult(res);
      setComputedSig(sig);
    } catch (e) {
      setResult(null);
      setComputedSig(null);
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    void compute();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function update(i: number, patch: Partial<BudgetRow>) {
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  }
  function remove(i: number) {
    setRows((rs) => rs.filter((_, j) => j !== i));
  }
  function add() {
    setRows((rs) => [
      ...rs,
      { name: "new component", mode: "standard", value: "", c: "1", dof: "", kind: "B" },
    ]);
  }
  function reset() {
    setRows(DEFAULT_ROWS);
    setNominal(DEFAULT_NOMINAL);
    setMeasurand(DEFAULT_MEASURAND);
  }

  async function openImport() {
    setImportMsg(null);
    try {
      const sets = (await api.listSets()).filter((s) => s.role === "measurement");
      setBatches(sets);
      setImportId(sets[0]?.id ?? "");
    } catch (e) {
      setBatches([]);
      setImportMsg((e as Error).message);
    }
  }

  async function applyImport() {
    if (!importId) return;
    setImportMsg(null);
    try {
      const s = await api.getTypeASummary(importId);
      const row: BudgetRow = {
        name: `repeatability (Type A) — ${s.name}`,
        mode: "standard",
        value: s.eps_real_sem_median.toPrecision(3),
        c: "1",
        dof: String(s.dof),
        kind: "A",
      };
      setRows((rs) => {
        const i = rs.findIndex((r) => r.kind === "A");
        return i === -1 ? [row, ...rs] : rs.map((r, j) => (j === i ? row : r));
      });
      setNominal(s.eps_real_median.toPrecision(4));
      setMeasurand(
        `ε' (median over ${s.band_ghz[0].toFixed(1)}–${s.band_ghz[1].toFixed(1)} GHz, ${s.name})`,
      );
      setImportMsg(
        `imported median ε′ SEM of ${s.n_used} repeats (ν = ${s.dof}) — nominal set to the band median`,
      );
      setBatches(null);
    } catch (e) {
      setImportMsg((e as Error).message);
    }
  }

  function exportJson() {
    const payload: BudgetFile = { version: 1, measurand, nominal, rows };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "uncertainty-budget.json";
    a.click();
    URL.revokeObjectURL(a.href);
  }

  async function importJson(file: File) {
    const parsed = parseBudgetFile(await file.text());
    if (!parsed) {
      setError("not a budget file — expected JSON with {version: 1, measurand, nominal, rows}");
      return;
    }
    setError(null);
    setMeasurand(parsed.measurand);
    setNominal(parsed.nominal);
    setRows(parsed.rows);
  }

  async function copyTable() {
    if (!result) return;
    await navigator.clipboard.writeText(result.table);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_420px]">
      <Card title="Uncertainty components" hint="GUM / JCGM-100">
        {isExample && (
          <div className="mb-3 flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2">
            <Badge tone="caution">example values</Badge>
            <span className="text-xs text-slate-400">
              these are illustrative, not your measurement — replace them with your own budget
            </span>
            <button
              onClick={() => setRows([])}
              className="ml-auto whitespace-nowrap text-xs text-slate-400 underline hover:text-slate-200"
            >
              clear all
            </button>
          </div>
        )}
        <div className="mb-3 flex gap-3">
          <div className="grow">
            <Field label="measurand (state frequency / temperature)">
              <Input
                type="text"
                value={measurand}
                placeholder="e.g. ε′ at 2.45 GHz, 25 °C"
                onChange={(e) => setMeasurand(e.target.value)}
              />
            </Field>
          </div>
          <div className="max-w-[140px]">
            <Field label={<>nominal <span className="normal-case">ε′</span></>}>
              <Input
                type="text"
                inputMode="decimal"
                value={nominal}
                onChange={(e) => setNominal(e.target.value)}
              />
            </Field>
          </div>
        </div>
        <div className={`${ROW_GRID} px-2 text-[10px] uppercase tracking-wider text-slate-500`}>
          <span>component</span>
          <span>
            value (<span className="normal-case">ε′</span>)
          </span>
          <span>entry</span>
          <span title="sensitivity coefficient cᵢ = ∂(measurand)/∂xᵢ" className="normal-case">
            cᵢ
          </span>
          <span>type</span>
          <span title="degrees of freedom" className="normal-case">
            ν
          </span>
          <span />
        </div>
        <p className="mb-2 px-2 text-[10px] text-slate-600">
          standard uncertainties in absolute ε′ units · contribution = |cᵢ|·uᵢ · ν blank = ∞
        </p>
        <div className="space-y-2">
          {rows.map((r, i) => {
            const u = standardU(r);
            const c = parseNum(r.c);
            const err = rowError(r);
            const showDerived = err === null && u !== null && (r.mode !== "standard" || c !== 1);
            return (
              <div
                key={i}
                className="rounded-lg border border-[var(--color-line)] bg-[var(--color-ink-850)] px-2 py-1.5"
              >
                <div className={ROW_GRID}>
                  <input
                    value={r.name}
                    onChange={(e) => update(i, { name: e.target.value })}
                    className="bg-transparent text-sm text-slate-100 outline-none"
                  />
                  <input
                    type="text"
                    inputMode="decimal"
                    value={r.value}
                    placeholder={r.mode === "standard" ? "u" : "±a"}
                    onChange={(e) => update(i, { value: e.target.value })}
                    className={numCls}
                  />
                  <select
                    value={r.mode}
                    onChange={(e) => update(i, { mode: e.target.value as EntryMode })}
                    className={selectCls}
                  >
                    <option value="standard">standard u</option>
                    <option value="rectangular">±a rectangular</option>
                    <option value="triangular">±a triangular</option>
                  </select>
                  <input
                    type="text"
                    inputMode="decimal"
                    value={r.c}
                    title="sensitivity coefficient cᵢ = ∂(measurand)/∂xᵢ"
                    onChange={(e) => update(i, { c: e.target.value })}
                    className={numCls}
                  />
                  <select
                    value={r.kind}
                    onChange={(e) => update(i, { kind: e.target.value as "A" | "B" })}
                    className={selectCls}
                  >
                    <option value="A">Type A</option>
                    <option value="B">Type B</option>
                  </select>
                  <input
                    type="text"
                    inputMode="decimal"
                    value={r.dof}
                    placeholder="∞"
                    onChange={(e) => update(i, { dof: e.target.value })}
                    className={numCls}
                  />
                  <button onClick={() => remove(i)} className="text-slate-500 hover:text-rose-300">
                    ✕
                  </button>
                </div>
                {err ? (
                  <p className="mt-1 text-[11px] text-rose-300">{err}</p>
                ) : (
                  showDerived &&
                  u !== null &&
                  c !== null && (
                    <p className="tabular mt-1 text-[11px] text-slate-500">
                      → uᵢ·|cᵢ| = {DIVISOR_LABEL[r.mode]}
                      {c !== 1 ? ` · |${r.c}|` : ""} = {(u * Math.abs(c)).toFixed(4)}
                    </p>
                  )
                )}
              </div>
            );
          })}
          {rows.length === 0 && (
            <p className="text-xs text-slate-600">no components — add at least one to compute</p>
          )}
        </div>
        <div className="mt-3 flex items-center gap-2">
          <Button variant="subtle" onClick={add}>
            + Add component
          </Button>
          <Button onClick={compute} disabled={!canCompute}>
            Compute budget
          </Button>
          {!isExample && (
            <button
              onClick={reset}
              className="ml-auto text-xs text-slate-500 underline hover:text-slate-300"
            >
              reset to example
            </button>
          )}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-[var(--color-line)] pt-3">
          {batches === null ? (
            <Button variant="ghost" onClick={openImport}>
              Import Type A from a loaded batch…
            </Button>
          ) : batches.length === 0 ? (
            <span className="text-xs text-slate-500">
              no measurement batches loaded — upload them in the Dielectric Analysis tab first{" "}
              <button
                onClick={() => setBatches(null)}
                className="text-slate-400 underline hover:text-slate-200"
              >
                dismiss
              </button>
            </span>
          ) : (
            <>
              <select
                value={importId}
                onChange={(e) => setImportId(e.target.value)}
                className={selectCls}
              >
                {batches.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name} ({b.n_used} repeats)
                  </option>
                ))}
              </select>
              <Button variant="subtle" onClick={applyImport}>
                Import
              </Button>
              <button
                onClick={() => setBatches(null)}
                className="text-xs text-slate-500 underline hover:text-slate-300"
              >
                cancel
              </button>
            </>
          )}
          <span className="ml-auto flex gap-2">
            <button
              onClick={exportJson}
              className="text-xs text-slate-500 underline hover:text-slate-300"
            >
              export .json
            </button>
            <button
              onClick={() => fileRef.current?.click()}
              className="text-xs text-slate-500 underline hover:text-slate-300"
            >
              import .json
            </button>
            <input
              ref={fileRef}
              type="file"
              accept="application/json,.json"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void importJson(f);
                e.target.value = "";
              }}
            />
          </span>
        </div>
        {importMsg && <p className="mt-2 text-xs text-teal-300/90">{importMsg}</p>}
        <p className="mt-3 text-xs text-slate-500">
          All uncertainties are in <span className="text-teal-300">absolute ε′ units</span> (not %).
          Enter a standard uncertainty u directly, or a half-width ±a with a distribution —
          rectangular gives u = a/√3, triangular u = a/√6. cᵢ scales an input quantity's u into the
          measurand (e.g. ∂ε′/∂T for a temperature term). Keep the{" "}
          <span className="text-teal-300">input/inversion</span> term: without it the budget is
          silently optimistic about the out-of-scope probe-software inversion step.
        </p>
        {error && <p className="mt-2 text-sm text-rose-300">{error}</p>}
      </Card>

      <div className="space-y-4">
        {stale && (
          <div>
            <Badge tone="caution">inputs changed — recompute</Badge>
          </div>
        )}
        {result && (
          <div className={stale ? "space-y-4 opacity-40 transition-opacity" : "space-y-4"}>
            <div className="grid grid-cols-2 gap-2">
              <Stat
                label={<>combined <span className="normal-case">u_c</span></>}
                value={result.combined_standard_uncertainty.toPrecision(3)}
              />
              <Stat label="coverage k (95%)" value={result.coverage_factor.toFixed(2)} />
              <Stat label="expanded U" value={result.expanded_uncertainty.toPrecision(3)} />
              <Stat
                label="relative U"
                value={
                  result.relative_expanded == null
                    ? "—"
                    : (result.relative_expanded * 100).toFixed(1)
                }
                unit={result.relative_expanded == null ? undefined : "%"}
              />
            </div>
            <Card title="Contributions" hint="% of variance">
              <Plot
                data={[
                  {
                    type: "bar",
                    orientation: "h",
                    x: result.contributions.map((c) => c.percent),
                    y: result.contributions.map((c) => c.name),
                    marker: {
                      color: result.contributions.map((c) =>
                        c.name.includes("input/inversion") ? "#2dd4bf" : "#3a4a63",
                      ),
                    },
                    hovertemplate: "%{y}: %{x:.1f}%<extra></extra>",
                  },
                ]}
                layout={{
                  paper_bgcolor: "rgba(0,0,0,0)",
                  plot_bgcolor: "rgba(0,0,0,0)",
                  font: { color: "#9fb0c8", size: 10 },
                  margin: { l: 160, r: 16, t: 8, b: 30 },
                  xaxis: { title: { text: "% of variance" }, gridcolor: "#1e2a3d" },
                  yaxis: { automargin: true },
                  height: 220,
                }}
                config={{ displayModeBar: false, responsive: true }}
                style={{ width: "100%" }}
                useResizeHandler
              />
              <div className="mt-2 flex flex-wrap gap-1">
                {result.contributions
                  .slice()
                  .sort((a, b) => b.percent - a.percent)
                  .slice(0, 1)
                  .map((c) => (
                    <Badge key={c.name} tone="signal">
                      largest: {c.name} ({c.percent.toFixed(0)}%)
                    </Badge>
                  ))}
              </div>
            </Card>
            <Card title="Budget table">
              <pre className="tabular overflow-x-auto whitespace-pre text-[11px] leading-relaxed text-slate-300">
                {result.table}
              </pre>
              <div className="mt-2">
                <button
                  onClick={copyTable}
                  className="text-xs text-slate-500 underline hover:text-slate-300"
                >
                  {copied ? "copied ✓" : "copy table"}
                </button>
              </div>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}
