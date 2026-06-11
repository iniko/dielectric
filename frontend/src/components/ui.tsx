import type { ReactNode } from "react";

export function Card({
  children,
  className = "",
  title,
  hint,
}: {
  children: ReactNode;
  className?: string;
  title?: string;
  hint?: string;
}) {
  return (
    <div
      className={`rounded-xl border border-[var(--color-line)] bg-[var(--color-ink-900)]/80 backdrop-blur ${className}`}
    >
      {title && (
        <div className="flex items-baseline justify-between border-b border-[var(--color-line)] px-5 py-3">
          <h3 className="text-sm font-semibold tracking-wide text-slate-200">{title}</h3>
          {hint && <span className="text-xs text-slate-500">{hint}</span>}
        </div>
      )}
      <div className="p-5">{children}</div>
    </div>
  );
}

export function Button({
  children,
  onClick,
  disabled,
  variant = "primary",
  type = "button",
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  variant?: "primary" | "ghost" | "subtle";
  type?: "button" | "submit";
}) {
  const styles = {
    primary:
      "bg-[var(--color-signal)] text-ink-950 hover:bg-[var(--color-signal-dim)] disabled:opacity-40",
    ghost:
      "border border-[var(--color-line)] text-slate-200 hover:border-[var(--color-signal)] hover:text-[var(--color-signal)]",
    subtle: "bg-[var(--color-ink-800)] text-slate-200 hover:bg-[var(--color-ink-700)]",
  }[variant];
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition disabled:cursor-not-allowed ${styles}`}
    >
      {children}
    </button>
  );
}

export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "good" | "caution" | "danger" | "signal";
}) {
  const tones = {
    neutral: "bg-ink-800 text-slate-300 border-[var(--color-line)]",
    good: "bg-emerald-500/10 text-emerald-300 border-emerald-500/30",
    caution: "bg-amber-500/10 text-amber-300 border-amber-500/30",
    danger: "bg-rose-500/10 text-rose-300 border-rose-500/30",
    signal: "bg-teal-500/10 text-teal-300 border-teal-500/30",
  }[tone];
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${tones}`}
    >
      {children}
    </span>
  );
}

export function Stat({ label, value, unit }: { label: ReactNode; value: string; unit?: string }) {
  return (
    <div className="rounded-lg border border-[var(--color-line)] bg-[var(--color-ink-850)] px-4 py-3">
      <div className="text-xs uppercase tracking-wider text-slate-500">{label}</div>
      <div className="tabular mt-1 text-lg font-semibold text-slate-100">
        {value}
        {unit && <span className="ml-1 text-sm font-normal text-slate-400">{unit}</span>}
      </div>
    </div>
  );
}

export function Field({ label, children }: { label: ReactNode; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium uppercase tracking-wider text-slate-500">
        {label}
      </span>
      {children}
    </label>
  );
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className="tabular w-full rounded-lg border border-[var(--color-line)] bg-[var(--color-ink-850)] px-3 py-2 text-sm text-slate-100 outline-none focus:border-[var(--color-signal)]"
    />
  );
}
