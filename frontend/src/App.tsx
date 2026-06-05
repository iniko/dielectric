import { useState } from "react";
import AnalysisWorkflow from "./workflows/AnalysisWorkflow";
import BudgetWorkflow from "./workflows/BudgetWorkflow";
import { PreferencesProvider, usePreferences } from "./preferences";

type Tab = "analysis" | "budget";

export default function App() {
  return (
    <PreferencesProvider>
      <AppInner />
    </PreferencesProvider>
  );
}

function AppInner() {
  const [tab, setTab] = useState<Tab>("analysis");

  return (
    <div className="mx-auto min-h-full max-w-[1400px] px-6 py-6">
      <header className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-2xl text-[var(--color-signal)]">⌁</span>
            <h1 className="text-xl font-bold tracking-tight text-slate-100">dielectric</h1>
            <span className="rounded bg-[var(--color-ink-800)] px-2 py-0.5 text-[10px] uppercase tracking-widest text-slate-400">
              spectroscopy
            </span>
          </div>
          <p className="mt-1 text-sm text-slate-500">
            Already-inverted ε*(f) → fit → verify → uncertainty → publication-ready report.
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <LossModeToggle />
          <nav className="flex gap-1 rounded-xl border border-[var(--color-line)] bg-[var(--color-ink-900)] p-1">
            <TabButton active={tab === "analysis"} onClick={() => setTab("analysis")}>
              Dielectric Analysis
            </TabButton>
            <TabButton active={tab === "budget"} onClick={() => setTab("budget")}>
              Uncertainty Budget
            </TabButton>
          </nav>
        </div>
      </header>

      {tab === "analysis" ? <AnalysisWorkflow /> : <BudgetWorkflow />}

      <footer className="mt-10 border-t border-[var(--color-line)] pt-4 text-xs text-slate-600">
        Engineering e^{"{jωt}"} convention (Im ε* &lt; 0). Reference tissue data is VERIFY-confidence
        — confirm against IFAC/IT'IS before citing. A thin UI over the validated{" "}
        <span className="text-slate-400">dielectric</span> Python library.
      </footer>
    </div>
  );
}

function LossModeToggle() {
  const { lossMode, setLossMode } = usePreferences();
  const opts: { key: "sigma" | "loss"; label: string }[] = [
    { key: "sigma", label: "σ (S/m)" },
    { key: "loss", label: "ε″" },
  ];
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] uppercase tracking-widest text-slate-500">loss axis</span>
      <div className="flex gap-0.5 rounded-lg border border-[var(--color-line)] bg-[var(--color-ink-900)] p-0.5">
        {opts.map((o) => (
          <button
            key={o.key}
            type="button"
            onClick={() => setLossMode(o.key)}
            className={`rounded-md px-2.5 py-1 text-xs font-semibold transition ${
              lossMode === o.key
                ? "bg-[var(--color-signal)] text-ink-950"
                : "text-slate-400 hover:text-slate-100"
            }`}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`rounded-lg px-4 py-2 text-sm font-semibold transition ${
        active
          ? "bg-[var(--color-signal)] text-ink-950"
          : "text-slate-400 hover:text-slate-100"
      }`}
    >
      {children}
    </button>
  );
}
