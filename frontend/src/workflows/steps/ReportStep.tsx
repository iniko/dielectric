import * as api from "../../api";
import type { AnalysisResult } from "../../types";
import { Button, Card } from "../../components/ui";
import { useAnalysis } from "../AnalysisContext";
import { ErrorMsg, Loading, PanelLabel, StepIntro } from "./common";
import { useAsync } from "./common";

export default function ReportStep() {
  const { ensureAnalysis, fitReq, measurements, validations, temperature } = useAnalysis();
  const key = JSON.stringify([
    fitReq,
    measurements.map((m) => m.id),
    validations.map((v) => v.id),
    temperature,
  ]);
  const { data: analysis, loading, error } = useAsync(() => ensureAnalysis(), [key]);

  return (
    <div>
      <StepIntro title="7 · Report">
        A reproducible, paper-ready report: the methods paragraph (paste-ready), fit and selection
        tables, figures, references, and a reproducibility manifest. Download <b>one combined campaign
        report</b> (every batch's analysis + the comparison, when there are ≥2 batches), or each batch
        individually — as self-contained HTML, PDF, or Word.
      </StepIntro>

      {loading && <Loading what="Assembling analysis…" />}
      {error && <ErrorMsg error={error} />}
      {analysis && (
        <>
          <div
            className={`mb-6 rounded-xl border px-5 py-3 text-sm font-medium ${
              analysis.validation.validated
                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
                : "border-amber-500/30 bg-amber-500/10 text-amber-200"
            }`}
          >
            {analysis.validation.validated ? "✓ " : "⚠ "}
            {analysis.validation.status}
          </div>

          <Card title="Full campaign report" hint="every batch + comparison, one file">
            <div className="flex flex-wrap gap-2">
              {(["html", "pdf", "docx"] as const).map((fmt) => (
                <a
                  key={fmt}
                  href={api.campaignReportUrl(analysis.campaign_id, fmt)}
                  target="_blank"
                  rel="noreferrer"
                >
                  <Button>{fmt.toUpperCase()}</Button>
                </a>
              ))}
            </div>
          </Card>

          <PanelLabel>
            <span className="mt-6 block">Or download each batch on its own:</span>
          </PanelLabel>
          <div className="space-y-6">
            {analysis.results.map((r) => (
              <ReportPanel key={r.sample_id} r={r} campaignId={analysis.campaign_id} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function ReportPanel({ r, campaignId }: { r: AnalysisResult; campaignId: string }) {
  return (
    <Card title={`Sample: ${r.sample_id}`} hint={r.chosen_model}>
      <PanelLabel>Methods paragraph (paste-ready)</PanelLabel>
      <p className="rounded-lg border border-[var(--color-line)] bg-[var(--color-ink-850)] p-3 text-xs leading-relaxed text-slate-300">
        {r.methods_paragraph}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <a href={api.reportUrl(campaignId, r.sample_id, "html")} target="_blank" rel="noreferrer">
          <Button variant="ghost">Download HTML report</Button>
        </a>
        <a href={api.reportUrl(campaignId, r.sample_id, "pdf")} target="_blank" rel="noreferrer">
          <Button variant="ghost">Download PDF report</Button>
        </a>
        <a href={api.reportUrl(campaignId, r.sample_id, "docx")} target="_blank" rel="noreferrer">
          <Button variant="ghost">Download Word report</Button>
        </a>
        <Button variant="subtle" onClick={() => navigator.clipboard?.writeText(r.methods_paragraph)}>
          Copy methods
        </Button>
      </div>
    </Card>
  );
}
