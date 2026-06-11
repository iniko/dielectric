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

// The wire shape of the customize controls. The DC-σ toggle is NOT a forced family — it
// constrains the backend's auto-selection panel to families with(out) a DC term, and is
// ignored (greyed out in the UI) when an explicit family is forced.
export function toFitBody(r: FitReq): {
  model: string | null;
  n_poles: number | null;
  dc_sigma: boolean | null;
} {
  return {
    model: r.model || null,
    n_poles: r.poles ? Number(r.poles) : null,
    dc_sigma: r.model || r.dcSigma === "" ? null : r.dcSigma === "on",
  };
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
  validationVersion: number; // bumped when a validation set's reference config changes
  bumpValidation: () => void;
  validationLinks: Record<string, string>; // validation set id -> measurement batch id
  attachValidation: (v: SetSummary, batchId: string) => void;
  detachValidation: (id: string) => void;
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
  const [validationVersion, setValidationVersion] = useState(0);
  const [validationLinks, setValidationLinks] = useState<Record<string, string>>({});

  // Cache keys guard against recreating the campaign / refitting when nothing relevant changed.
  const cache = useRef({ cid: null as string | null, campaignSig: "", fitSig: "", analysisSig: "" });

  const addSet = useCallback((s: SetSummary) => {
    if (s.role === "measurement") setMeasurements((x) => [...x, s]);
    else setValidations((x) => [...x, s]);
  }, []);

  const removeSet = useCallback((role: "measurement" | "validation", id: string) => {
    if (role === "measurement") setMeasurements((x) => x.filter((m) => m.id !== id));
    else setValidations((x) => x.filter((v) => v.id !== id));
    // Also forget it server-side, so the name doesn't feed batch-name disambiguation forever.
    void api.deleteSet(id).catch(() => undefined);
  }, []);

  const attachValidation = useCallback((v: SetSummary, batchId: string) => {
    setValidations((x) => [...x, v]);
    setValidationLinks((m) => ({ ...m, [v.id]: batchId }));
  }, []);

  const detachValidation = useCallback((id: string) => {
    setValidations((x) => x.filter((v) => v.id !== id));
    setValidationLinks((m) => {
      const next = { ...m };
      delete next[id];
      return next;
    });
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
        toFitBody(fitReq),
        screeningVersion, // screening change → new mean → refetch fit/analysis/compare
        validationVersion, // validation reference edit → refetch the banner/report
      ]),
    [fitReq, screeningVersion, validationVersion],
  );

  const ensureFit = useCallback(async () => {
    const cid = await ensureCampaign();
    const sig = reqSig(cid);
    if (fit && cache.current.fitSig === sig) return fit;
    const res = await api.fitCampaign(cid, toFitBody(fitReq));
    cache.current.fitSig = sig;
    setFit(res);
    return res;
  }, [ensureCampaign, reqSig, fitReq, fit]);

  const ensureAnalysis = useCallback(
    async (force = false) => {
      const cid = await ensureCampaign();
      const sig = reqSig(cid);
      if (!force && analysis && cache.current.analysisSig === sig) return analysis;
      const res = await api.analyze(cid, toFitBody(fitReq));
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
    validationVersion,
    bumpValidation: () => setValidationVersion((v) => v + 1),
    validationLinks,
    attachValidation,
    detachValidation,
    ensureCampaign,
    ensureFit,
    ensureAnalysis,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
