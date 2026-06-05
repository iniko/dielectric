export interface StepDef {
  key: string;
  label: string;
  enabled: boolean;
}

// Free-navigation stepper: numbered pills, click any enabled step to jump there.
export function Stepper({
  steps,
  current,
  onSelect,
}: {
  steps: StepDef[];
  current: number;
  onSelect: (index: number) => void;
}) {
  return (
    <nav className="flex flex-wrap items-center gap-1 rounded-xl border border-[var(--color-line)] bg-[var(--color-ink-900)] p-1.5">
      {steps.map((s, i) => {
        const active = i === current;
        const disabled = !s.enabled;
        return (
          <button
            key={s.key}
            type="button"
            disabled={disabled}
            onClick={() => onSelect(i)}
            className={`inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium transition ${
              active
                ? "bg-[var(--color-signal)] text-ink-950"
                : disabled
                  ? "cursor-not-allowed text-slate-600"
                  : "text-slate-400 hover:text-slate-100"
            }`}
          >
            <span
              className={`flex h-5 w-5 items-center justify-center rounded-full text-[11px] ${
                active
                  ? "bg-ink-950/20 text-ink-950"
                  : "border border-[var(--color-line)] text-slate-500"
              }`}
            >
              {i + 1}
            </span>
            {s.label}
          </button>
        );
      })}
    </nav>
  );
}
