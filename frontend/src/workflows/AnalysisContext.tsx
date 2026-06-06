import { createContext, useCallback, useContext, useRef, useState } from "react";
import type { ReactNode } from "react";
import * as api from "../api";
import type { CampaignAnalysis, FitOut, SetSummary } from "../types";

// The constrained "customize the model" controls: explicit family, pole count, and a DC-σ toggle.
// (Per-parameter fixing is intentionally out of scope to keep the fit hard to misuse.)
export interface FitReq {
  model: string; // "" = auto-select
  poles: string; // "" = auto
  dcSigma: "" | "on" | "off"; // "" = let the model choice decide
}

export function resolveModel(r: FitReq): string | null {
  if (r.model) return r.model;
  if (r.dcSigma === "on") return "Cole-Cole + DC σ";
  if (r.dcSigma === "off") return "Cole-Cole";
  return null;
}

interface AnalysisState {
  measurements: SetSummary[];
  validations: SetSummary[];
  temperature: number;
  setTemperature: (n: number) => void;
  addSet: (s: SetSummary) => void;
  removeSet: (role: "measurement" | "validation", id: string) => void;
  fitReq: FitReq;
  setFitReq: (r: FitReq) => void;
  fit: FitOut | null;
  analysis: CampaignAnalysis | null;
  screeningVersion: number; // bumped when a set's repeat screening changes (invalidates downstream)
  bumpScreening: () => void;
  ensureCampaign: () => Promise<string>;
  ensureFit: () => Promise<FitOut>;
  ensureAnalysis: (force?: boolean) => Promise<CampaignAnalysis>;
}

const Ctx = createContext<AnalysisState | null>(null);

export function useAnalysis(): AnalysisState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAnalysis must be used inside <AnalysisProvider>");
  return v;
}

export function AnalysisProvider({ children }: { children: ReactNode }) {
  const [measurements, setMeasurements] = useState<SetSummary[]>([]);
  const [validations, setValidations] = useState<SetSummary[]>([]);
  const [temperature, setTemperature] = useState(25);
  const [fitReq, setFitReq] = useState<FitReq>({ model: "", poles: "", dcSigma: "" });
  const [fit, setFit] = useState<FitOut | null>(null);
  const [analysis, setAnalysis] = useState<CampaignAnalysis | null>(null);
  const [screeningVersion, setScreeningVersion] = useState(0);

  // Cache keys guard against recreating the campaign / refitting when nothing relevant changed.
  const cache = useRef({ cid: null as string | null, campaignSig: "", fitSig: "", analysisSig: "" });

  const addSet = useCallback((s: SetSummary) => {
    if (s.role === "measurement") setMeasurements((x) => [...x, s]);
    else setValidations((x) => [...x, s]);
  }, []);

  const removeSet = useCallback((role: "measurement" | "validation", id: string) => {
    if (role === "measurement") setMeasurements((x) => x.filter((m) => m.id !== id));
    else setValidations((x) => x.filter((v) => v.id !== id));
  }, []);

  const ensureCampaign = useCallback(async () => {
    const sig = JSON.stringify([
      measurements.map((m) => m.id),
      validations.map((v) => v.id),
      temperature,
    ]);
    if (cache.current.cid && cache.current.campaignSig === sig) return cache.current.cid;
    const { id } = await api.createCampaign({
      measurement_set_ids: measurements.map((m) => m.id),
      validation_set_ids: validations.map((v) => v.id),
      temperature_c: temperature,
    });
    cache.current = { cid: id, campaignSig: sig, fitSig: "", analysisSig: "" };
    setFit(null);
    setAnalysis(null);
    return id;
  }, [measurements, validations, temperature]);

  const reqSig = useCallback(
    (cid: string) =>
      JSON.stringify([
        cid,
        resolveModel(fitReq),
        fitReq.poles ? Number(fitReq.poles) : null,
        screeningVersion, // screening change → new mean → refetch fit/analysis/compare
      ]),
    [fitReq, screeningVersion],
  );

  const ensureFit = useCallback(async () => {
    const cid = await ensureCampaign();
    const sig = reqSig(cid);
    if (fit && cache.current.fitSig === sig) return fit;
    const res = await api.fitCampaign(cid, {
      model: resolveModel(fitReq),
      n_poles: fitReq.poles ? Number(fitReq.poles) : null,
    });
    cache.current.fitSig = sig;
    setFit(res);
    return res;
  }, [ensureCampaign, reqSig, fitReq, fit]);

  const ensureAnalysis = useCallback(
    async (force = false) => {
      const cid = await ensureCampaign();
      const sig = reqSig(cid);
      if (!force && analysis && cache.current.analysisSig === sig) return analysis;
      const res = await api.analyze(cid, {
        model: resolveModel(fitReq),
        n_poles: fitReq.poles ? Number(fitReq.poles) : null,
      });
      cache.current.analysisSig = sig;
      setAnalysis(res);
      return res;
    },
    [ensureCampaign, reqSig, fitReq, analysis],
  );

  const value: AnalysisState = {
    measurements,
    validations,
    temperature,
    setTemperature,
    addSet,
    removeSet,
    fitReq,
    setFitReq,
    fit,
    analysis,
    screeningVersion,
    bumpScreening: () => setScreeningVersion((v) => v + 1),
    ensureCampaign,
    ensureFit,
    ensureAnalysis,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
