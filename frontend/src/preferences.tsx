import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";

// Display preference for the lossy quantity. The group plots effective conductivity σ rather than
// dielectric loss ε″; the two are interconvertible per frequency (σ = 2π·f·ε₀·ε″), so this is a
// pure display choice with no backend round-trip.
export type LossMode = "sigma" | "loss";

export const EPSILON_0 = 8.8541878128e-12; // [F/m], CODATA 2018 — matches dielectric/constants.py

export function toSigma(loss: number, fHz: number): number {
  return 2 * Math.PI * fHz * EPSILON_0 * loss;
}

export function toLoss(sigma: number, fHz: number): number {
  return sigma / (2 * Math.PI * fHz * EPSILON_0);
}

export function lossAxisTitle(mode: LossMode): string {
  return mode === "sigma" ? "σ_eff (S/m)" : "ε″";
}

interface Prefs {
  lossMode: LossMode;
  setLossMode: (m: LossMode) => void;
}

const Ctx = createContext<Prefs | null>(null);
const STORAGE_KEY = "dielectric.lossMode";

export function usePreferences(): Prefs {
  const v = useContext(Ctx);
  if (!v) throw new Error("usePreferences must be used inside <PreferencesProvider>");
  return v;
}

export function PreferencesProvider({ children }: { children: ReactNode }) {
  const [lossMode, setLossMode] = useState<LossMode>(() => {
    const saved = typeof localStorage !== "undefined" ? localStorage.getItem(STORAGE_KEY) : null;
    return saved === "loss" ? "loss" : "sigma"; // default: conductivity
  });
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, lossMode);
    } catch {
      /* localStorage may be unavailable; preference is still honoured for the session */
    }
  }, [lossMode]);
  return <Ctx.Provider value={{ lossMode, setLossMode }}>{children}</Ctx.Provider>;
}
