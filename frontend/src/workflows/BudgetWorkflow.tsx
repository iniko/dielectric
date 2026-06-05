import { useEffect, useState } from "react";
// The factory entry's types are declared in shims.d.ts.
import createPlotlyComponent from "react-plotly.js/factory";
import Plotly from "plotly.js-dist-min";
import * as api from "../api";
import type { BudgetComponentIn, BudgetResult } from "../types";
import { Badge, Button, Card, Field, Input, Stat } from "../components/ui";

const Plot = createPlotlyComponent(Plotly);

const DEFAULTS: BudgetComponentIn[] = [
  { name: "repeatability (Type A)", standard_uncertainty: 0.67, sensitivity: 1, dof: 13, kind: "A" },
  { name: "model-fit uncertainty", standard_uncertainty: 0.8, sensitivity: 1, dof: Infinity, kind: "B" },
  { name: "probe calibration", standard_uncertainty: 1.16, sensitivity: 1, dof: Infinity, kind: "B" },
  { name: "temperature", standard_uncertainty: 0.42, sensitivity: 1, dof: Infinity, kind: "B" },
  { name: "input/inversion (probe software)", standard_uncertainty: 1.74, sensitivity: 1, dof: Infinity, kind: "B" },
];

export default function BudgetWorkflow() {
  const [nominal, setNominal] = useState(58);
  const [components, setComponents] = useState<BudgetComponentIn[]>(DEFAULTS);
  const [result, setResult] = useState<BudgetResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function compute() {
    setError(null);
    try {
      const res = await api.computeBudget({
        measurand: "ε'",
        nominal_value: nominal,
        unit: "",
        coverage_level: 0.95,
        components: components.map((c) => ({
          ...c,
          dof: Number.isFinite(c.dof) ? c.dof : 1e9,
        })),
      });
      setResult(res);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    void compute();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function update(i: number, patch: Partial<BudgetComponentIn>) {
    setComponents((cs) => cs.map((c, j) => (j === i ? { ...c, ...patch } : c)));
  }
  function remove(i: number) {
    setComponents((cs) => cs.filter((_, j) => j !== i));
  }
  function add() {
    setComponents((cs) => [
      ...cs,
      { name: "new component", standard_uncertainty: 0.1, sensitivity: 1, dof: Infinity, kind: "B" },
    ]);
  }

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_420px]">
      <Card title="Uncertainty components" hint="GUM / JCGM-100">
        <div className="mb-3 max-w-[180px]">
          <Field label="measurand nominal ε′">
            <Input type="number" value={nominal} onChange={(e) => setNominal(Number(e.target.value))} />
          </Field>
        </div>
        <div className="space-y-2">
          {components.map((c, i) => (
            <div
              key={i}
              className="grid grid-cols-[1fr_90px_80px_60px_28px] items-center gap-2 rounded-lg border border-[var(--color-line)] bg-[var(--color-ink-850)] px-2 py-1.5"
            >
              <input
                value={c.name}
                onChange={(e) => update(i, { name: e.target.value })}
                className="bg-transparent text-sm text-slate-100 outline-none"
              />
              <input
                type="number"
                step="0.01"
                value={c.standard_uncertainty}
                onChange={(e) => update(i, { standard_uncertainty: Number(e.target.value) })}
                className="tabular rounded bg-[var(--color-ink-800)] px-2 py-1 text-sm text-slate-100 outline-none"
              />
              <select
                value={c.kind}
                onChange={(e) => update(i, { kind: e.target.value })}
                className="rounded bg-[var(--color-ink-800)] px-1 py-1 text-xs text-slate-200"
              >
                <option value="A">Type A</option>
                <option value="B">Type B</option>
              </select>
              <input
                type="number"
                value={Number.isFinite(c.dof) ? c.dof : ""}
                placeholder="∞"
                onChange={(e) =>
                  update(i, { dof: e.target.value ? Number(e.target.value) : Infinity })
                }
                className="tabular rounded bg-[var(--color-ink-800)] px-2 py-1 text-sm text-slate-100 outline-none"
              />
              <button onClick={() => remove(i)} className="text-slate-500 hover:text-rose-300">
                ✕
              </button>
            </div>
          ))}
        </div>
        <div className="mt-3 flex gap-2">
          <Button variant="subtle" onClick={add}>
            + Add component
          </Button>
          <Button onClick={compute}>Compute budget</Button>
        </div>
        <p className="mt-3 text-xs text-slate-500">
          Tip: the <span className="text-teal-300">input/inversion</span> term injects an explicit
          “trust the probe software ±X%” contribution — without it the budget is silently optimistic
          about the out-of-scope inversion step.
        </p>
        {error && <p className="mt-2 text-sm text-rose-300">{error}</p>}
      </Card>

      <div className="space-y-4">
        {result && (
          <>
            <div className="grid grid-cols-2 gap-2">
              <Stat label="combined u_c" value={result.combined_standard_uncertainty.toPrecision(3)} />
              <Stat label="coverage k (95%)" value={result.coverage_factor.toFixed(2)} />
              <Stat label="expanded U" value={result.expanded_uncertainty.toPrecision(3)} />
              <Stat label="relative U" value={(result.relative_expanded * 100).toFixed(1)} unit="%" />
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
            </Card>
          </>
        )}
      </div>
    </div>
  );
}
