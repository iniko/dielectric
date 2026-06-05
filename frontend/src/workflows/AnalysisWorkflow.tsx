import { useState } from "react";
import { Stepper } from "../components/Stepper";
import type { StepDef } from "../components/Stepper";
import { Button } from "../components/ui";
import { AnalysisProvider, useAnalysis } from "./AnalysisContext";
import LoadStep from "./steps/LoadStep";
import RepeatsStep from "./steps/RepeatsStep";
import FitStep from "./steps/FitStep";
import KKStep from "./steps/KKStep";
import ValidationStep from "./steps/ValidationStep";
import ReferenceStep from "./steps/ReferenceStep";
import CompareStep from "./steps/CompareStep";
import ReportStep from "./steps/ReportStep";

const STEPS = [
  { key: "load", label: "Load", Component: LoadStep },
  { key: "repeats", label: "Repeats", Component: RepeatsStep },
  { key: "fit", label: "Model fit", Component: FitStep },
  { key: "kk", label: "Kramers-Kronig", Component: KKStep },
  { key: "validation", label: "Validation", Component: ValidationStep },
  { key: "reference", label: "Reference match", Component: ReferenceStep },
  { key: "compare", label: "Compare", Component: CompareStep },
  { key: "report", label: "Report", Component: ReportStep },
];

export default function AnalysisWorkflow() {
  return (
    <AnalysisProvider>
      <Shell />
    </AnalysisProvider>
  );
}

function Shell() {
  const { measurements } = useAnalysis();
  const [current, setCurrent] = useState(0);
  const ready = measurements.length > 0;
  const canCompare = measurements.length >= 2; // comparison needs at least two batches

  const stepEnabled = (key: string, i: number) =>
    i === 0 || (ready && (key !== "compare" || canCompare));

  const steps: StepDef[] = STEPS.map((s, i) => ({
    key: s.key,
    label: s.label,
    enabled: stepEnabled(s.key, i),
  }));

  const Current = STEPS[current].Component;

  function go(delta: number) {
    let next = current + delta;
    // skip over a disabled step (e.g. Compare with <2 batches) in the travel direction
    while (next > 0 && next < STEPS.length && !stepEnabled(STEPS[next].key, next)) next += delta;
    if (next >= 0 && next < STEPS.length && stepEnabled(STEPS[next].key, next)) setCurrent(next);
  }

  return (
    <div className="space-y-6">
      <Stepper steps={steps} current={current} onSelect={setCurrent} />

      <div className="min-h-[400px]">
        <Current />
      </div>

      <div className="flex items-center justify-between border-t border-[var(--color-line)] pt-4">
        <Button variant="ghost" onClick={() => go(-1)} disabled={current === 0}>
          ← Back
        </Button>
        {!ready && current === 0 && (
          <span className="text-xs text-slate-500">Load a measurement set to continue.</span>
        )}
        <Button onClick={() => go(1)} disabled={current === STEPS.length - 1 || !ready}>
          Next →
        </Button>
      </div>
    </div>
  );
}
