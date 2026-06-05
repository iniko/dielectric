import * as api from "../../api";
import type { KKDetail } from "../../types";
import { Badge, Card, Stat } from "../../components/ui";
import { KKPlot, SeriesPlot } from "../../components/Plots";
import { useAnalysis } from "../AnalysisContext";
import { ErrorMsg, Loading, Note, PanelLabel, StepIntro, useAsync } from "./common";

export default function KKStep() {
  const { ensureFit, fitReq, measurements, temperature } = useAnalysis();
  const key = JSON.stringify([fitReq, measurements.map((m) => m.id), temperature]);
  const { data, loading, error } = useAsync(async () => {
    const fit = await ensureFit();
    return api.getKK(fit.campaign_id);
  }, [key]);

  return (
    <div>
      <StepIntro title="4 · Kramers-Kronig consistency">
        A singly-subtractive KK relation predicts ε′ from the measured loss, using the fitted model to
        supply the out-of-band tail (so the check is not corrupted by finite-band truncation).
        Overlapping predicted and measured ε′ curves indicate a causal, internally consistent spectrum;
        the residual and truncation estimate quantify the agreement.
      </StepIntro>

      {loading && <Loading what="Running KK check…" />}
      {error && <ErrorMsg error={error} />}
      <div className="space-y-6">
        {data?.results.map((kk) => <KKPanel key={kk.sample_id} kk={kk} />)}
      </div>
    </div>
  );
}

function KKPanel({ kk }: { kk: KKDetail }) {
  return (
    <Card title={`Sample: ${kk.sample_id}`}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Badge tone={kk.consistent ? "good" : "danger"}>
          {kk.consistent ? "KK consistent" : "KK inconsistent"}
        </Badge>
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        <Stat label="ε′ residual RMS" value={(kk.residual_rms * 100).toFixed(2)} unit="%" />
        <Stat label="truncation estimate" value={(kk.truncation_estimate * 100).toFixed(1)} unit="%" />
        <Stat label="tolerance" value="5" unit="%" />
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div>
          <PanelLabel>KK-predicted vs measured ε′</PanelLabel>
          <KKPlot kk={kk} />
        </div>
        <div>
          <PanelLabel>Relative residual |Δε′| / |ε′|</PanelLabel>
          <SeriesPlot
            x={kk.frequency_hz}
            y={kk.relative_residual.map((v) => v * 100)}
            yTitle="relative residual (%)"
          />
        </div>
      </div>

      {kk.warnings.map((w, i) => (
        <p key={i} className="mt-2 text-xs text-amber-300">
          ⚠ {w}
        </p>
      ))}
      <Note>
        Tissue spectra can show a larger residual near the band edges (water relaxation peak + the
        low-frequency ionic tail); the model-supplied tail makes this a physics check rather than a
        truncation artifact.
      </Note>
    </Card>
  );
}
