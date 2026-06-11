import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";

export function PanelLabel({ children }: { children: ReactNode }) {
  return (
    <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
      {children}
    </div>
  );
}

export function StepIntro({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mb-5">
      <h2 className="text-lg font-semibold text-slate-100">{title}</h2>
      <p className="mt-1 max-w-3xl text-sm text-slate-400">{children}</p>
    </div>
  );
}

export function Loading({ what = "Computing…" }: { what?: string }) {
  return (
    <div className="flex items-center gap-2 py-10 text-sm text-slate-500">
      <span className="h-3 w-3 animate-pulse rounded-full bg-[var(--color-signal)]" />
      {what}
    </div>
  );
}

export function ErrorMsg({ error }: { error: string }) {
  return (
    <p className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
      {error}
    </p>
  );
}

export function Note({ children }: { children: ReactNode }) {
  return <p className="mt-3 text-xs leading-relaxed text-slate-500">{children}</p>;
}

interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

// Returns `value` after it has been stable for `ms`. Initializes to `value`, so the first
// render (mount) is NOT delayed — only subsequent changes are debounced.
export function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

// Run an async fetch whenever `deps` change; expose data/loading/error and a manual reload.
// NB: `data` persists across a re-run that errors (setData fires only on success) — steps rely
// on this to keep showing the last successful result, marked stale, when a request fails.
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(fn, deps);

  useEffect(() => {
    let live = true;
    setLoading(true);
    setError(null);
    run()
      .then((d) => live && setData(d))
      .catch((e) => live && setError((e as Error).message))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [run, tick]);

  return { data, loading, error, reload: () => setTick((t) => t + 1) };
}
