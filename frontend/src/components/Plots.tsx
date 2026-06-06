// The factory entry's types are declared in shims.d.ts.
import createPlotlyComponent from "react-plotly.js/factory";
import Plotly from "plotly.js-dist-min";
import type { KKDetail, RefOverlay, RepeatBand, ResidualSeries, SpectrumPlot } from "../types";
import { type LossMode, lossAxisTitle, toLoss, toSigma } from "../preferences";

const Plot = createPlotlyComponent(Plotly);

const SIGNAL = "#2dd4bf";
const VIOLET = "#a78bfa";
const FIT = "#fbbf24";
const ROSE = "#fb7185";
const PAPER = "rgba(0,0,0,0)";
const GRID = "#1e2a3d";
const FONT = { color: "#9fb0c8", family: "Inter, sans-serif", size: 11 };

const baseLayout = {
  paper_bgcolor: PAPER,
  plot_bgcolor: PAPER,
  font: FONT,
  margin: { l: 56, r: 56, t: 16, b: 44 },
  showlegend: true,
  legend: { orientation: "h" as const, y: 1.12, x: 0, font: { size: 10 } },
  hovermode: "closest" as const,
};

const config = { displayModeBar: false, responsive: true };

export function ColeColePlot({ data }: { data: SpectrumPlot }) {
  return (
    <Plot
      data={[
        {
          x: data.eps_real,
          y: data.loss,
          mode: "markers",
          type: "scatter",
          name: "data",
          marker: { color: SIGNAL, size: 6, opacity: 0.85 },
        },
        {
          x: data.fit_eps_real,
          y: data.fit_loss,
          mode: "lines",
          type: "scatter",
          name: "fit",
          line: { color: FIT, width: 2 },
        },
      ]}
      layout={{
        ...baseLayout,
        xaxis: { title: { text: "ε′" }, gridcolor: GRID, zeroline: false },
        yaxis: { title: { text: "ε″ = −Im(ε*)" }, gridcolor: GRID, zeroline: false },
      }}
      config={config}
      style={{ width: "100%", height: "340px" }}
      useResizeHandler
    />
  );
}

function asLossy(loss: number[], freq: number[], mode: LossMode): number[] {
  return mode === "sigma" ? loss.map((v, i) => toSigma(v, freq[i])) : loss;
}

export function BodePlot({ data, mode = "loss" }: { data: SpectrumPlot; mode?: LossMode }) {
  const name = mode === "sigma" ? "σ" : "ε″";
  return (
    <Plot
      data={[
        {
          x: data.frequency_hz,
          y: data.eps_real,
          mode: "markers",
          type: "scatter",
          name: "ε′ data",
          marker: { color: SIGNAL, size: 5 },
        },
        {
          x: data.fit_frequency_hz,
          y: data.fit_eps_real,
          mode: "lines",
          type: "scatter",
          name: "ε′ fit",
          line: { color: SIGNAL, width: 2 },
        },
        {
          x: data.frequency_hz,
          y: asLossy(data.loss, data.frequency_hz, mode),
          mode: "markers",
          type: "scatter",
          name: `${name} data`,
          yaxis: "y2",
          marker: { color: VIOLET, size: 5 },
        },
        {
          x: data.fit_frequency_hz,
          y: asLossy(data.fit_loss, data.fit_frequency_hz, mode),
          mode: "lines",
          type: "scatter",
          name: `${name} fit`,
          yaxis: "y2",
          line: { color: VIOLET, width: 2, dash: "dot" },
        },
      ]}
      layout={{
        ...baseLayout,
        xaxis: { title: { text: "frequency (Hz)" }, type: "log", gridcolor: GRID },
        yaxis: { title: { text: "ε′" }, gridcolor: GRID, zeroline: false },
        yaxis2: {
          title: { text: lossAxisTitle(mode) },
          overlaying: "y",
          side: "right",
          showgrid: false,
          zeroline: false,
        },
      }}
      config={config}
      style={{ width: "100%", height: "340px" }}
      useResizeHandler
    />
  );
}

const PLOT_H = "320px";

// Type A confidence band: mean ± k·SEM as a translucent fill, for ε′ or σ_eff.
export function RepeatBandPlot({
  band,
  quantity,
}: {
  band: RepeatBand;
  quantity: "eps" | "sigma" | "loss";
}) {
  const isEps = quantity === "eps";
  const x = band.frequency_hz;
  // σ and ε″ differ by σ = 2πf·ε₀·ε″, so the loss band is the σ band converted point-by-point.
  const conv = (v: number, i: number) => (quantity === "loss" ? toLoss(v, x[i]) : v);
  const mean = isEps ? band.eps_real : band.sigma.map(conv);
  const lo = isEps ? band.eps_real_lo : band.sigma_lo.map(conv);
  const hi = isEps ? band.eps_real_hi : band.sigma_hi.map(conv);
  const color = isEps ? SIGNAL : VIOLET;
  const rgb = isEps ? "45,212,191" : "167,139,250";
  const label = isEps ? "ε′" : quantity === "loss" ? "ε″" : "σ";
  const yTitle = isEps ? "ε′" : lossAxisTitle(quantity === "loss" ? "loss" : "sigma");
  return (
    <Plot
      data={[
        { x, y: lo, mode: "lines", line: { width: 0 }, showlegend: false, hoverinfo: "skip" },
        {
          x,
          y: hi,
          mode: "lines",
          line: { width: 0 },
          fill: "tonexty",
          fillcolor: `rgba(${rgb},0.16)`,
          name: "95% band",
          hoverinfo: "skip",
        },
        {
          x,
          y: mean,
          mode: "lines+markers",
          name: `${label} mean`,
          line: { color, width: 2 },
          marker: { color, size: 4 },
        },
      ]}
      layout={{
        ...baseLayout,
        xaxis: { title: { text: "frequency (Hz)" }, type: "log", gridcolor: GRID },
        yaxis: { title: { text: yTitle }, gridcolor: GRID, zeroline: false },
      }}
      config={config}
      style={{ width: "100%", height: PLOT_H }}
      useResizeHandler
    />
  );
}

// Kramers-Kronig: KK-predicted ε′ (from measured ε″ + model tail) overlaid on measured ε′.
// Overlapping curves ⇒ a causal, internally consistent spectrum.
export function KKPlot({ kk }: { kk: KKDetail }) {
  return (
    <Plot
      data={[
        {
          x: kk.frequency_hz,
          y: kk.measured_eps_real,
          mode: "markers",
          name: "measured ε′",
          marker: { color: SIGNAL, size: 5 },
        },
        {
          x: kk.frequency_hz,
          y: kk.predicted_eps_real,
          mode: "lines",
          name: "KK-predicted ε′",
          line: { color: FIT, width: 2, dash: "dot" },
        },
      ]}
      layout={{
        ...baseLayout,
        xaxis: { title: { text: "frequency (Hz)" }, type: "log", gridcolor: GRID },
        yaxis: { title: { text: "ε′" }, gridcolor: GRID, zeroline: false },
      }}
      config={config}
      style={{ width: "100%", height: PLOT_H }}
      useResizeHandler
    />
  );
}

// Fit residuals vs frequency. Two views:
//  - normalized (default): standardized residuals (raw ÷ per-point σ), dimensionless "pulls" sharing
//    one axis, with ±1σ/±2σ guide bands — the weighted-fit diagnostic (Σ pull² = χ²).
//  - raw: the physical residuals on a dual axis with units (Δε′ left; Δε″ or Δσ right).
export function ResidualPlot({
  residual,
  mode = "loss",
  normalized = true,
}: {
  residual: ResidualSeries;
  mode?: LossMode;
  normalized?: boolean;
}) {
  const f = residual.frequency_hz;
  if (normalized) {
    const band = (y0: number, y1: number, fill: string) => ({
      type: "rect" as const, xref: "paper" as const, x0: 0, x1: 1,
      yref: "y" as const, y0, y1, fillcolor: fill, line: { width: 0 }, layer: "below" as const,
    });
    const line2 = (y: number) => ({
      type: "line" as const, xref: "paper" as const, x0: 0, x1: 1,
      yref: "y" as const, y0: y, y1: y, line: { color: "#64748b", width: 1, dash: "dot" as const },
    });
    return (
      <Plot
        data={[
          { x: f, y: residual.norm_eps_real, mode: "markers", name: "ε′ pull",
            marker: { color: SIGNAL, size: 5 } },
          { x: f, y: residual.norm_loss, mode: "markers", name: "ε″ pull",
            marker: { color: VIOLET, size: 5 } },
        ]}
        layout={{
          ...baseLayout,
          shapes: [band(-1, 1, "rgba(45,212,191,0.10)"), line2(2), line2(-2)],
          xaxis: { title: { text: "frequency (Hz)" }, type: "log", gridcolor: GRID },
          yaxis: {
            title: { text: "normalized residual (units of σ)" },
            gridcolor: GRID, zeroline: true, zerolinecolor: "#475569",
          },
        }}
        config={config}
        style={{ width: "100%", height: PLOT_H }}
        useResizeHandler
      />
    );
  }
  const lossyResid = asLossy(residual.residual_loss, f, mode);
  return (
    <Plot
      data={[
        { x: f, y: residual.residual_eps_real, mode: "markers", name: "Δε′",
          marker: { color: SIGNAL, size: 5 } },
        { x: f, y: lossyResid, mode: "markers", name: mode === "sigma" ? "Δσ" : "Δε″",
          yaxis: "y2", marker: { color: VIOLET, size: 5 } },
      ]}
      layout={{
        ...baseLayout,
        xaxis: { title: { text: "frequency (Hz)" }, type: "log", gridcolor: GRID },
        yaxis: { title: { text: "Δε′" }, gridcolor: GRID, zeroline: true, zerolinecolor: "#475569" },
        yaxis2: {
          title: { text: mode === "sigma" ? "Δσ (S/m)" : "Δε″" },
          overlaying: "y", side: "right", showgrid: false, zeroline: false,
        },
      }}
      config={config}
      style={{ width: "100%", height: PLOT_H }}
      useResizeHandler
    />
  );
}

// A simple semilog-x line trace — used for KK relative residual and reference relative error.
export function SeriesPlot({
  x,
  y,
  yTitle,
  color = ROSE,
}: {
  x: number[];
  y: number[];
  yTitle: string;
  color?: string;
}) {
  return (
    <Plot
      data={[{ x, y, mode: "lines+markers", line: { color, width: 2 }, marker: { color, size: 4 } }]}
      layout={{
        ...baseLayout,
        showlegend: false,
        xaxis: { title: { text: "frequency (Hz)" }, type: "log", gridcolor: GRID },
        yaxis: { title: { text: yTitle }, gridcolor: GRID, zeroline: false },
      }}
      config={config}
      style={{ width: "100%", height: PLOT_H }}
      useResizeHandler
    />
  );
}

// Measurement-vs-reference overlay (ε′ and ε″) for the validation / reference-match steps.
export function ReferenceOverlayPlot({
  overlay,
  mode = "loss",
}: {
  overlay: RefOverlay;
  mode?: LossMode;
}) {
  const name = mode === "sigma" ? "σ" : "ε″";
  return (
    <Plot
      data={[
        {
          x: overlay.frequency_hz,
          y: overlay.meas_eps_real,
          mode: "markers",
          name: "ε′ measured",
          marker: { color: SIGNAL, size: 5 },
        },
        {
          x: overlay.frequency_hz,
          y: overlay.ref_eps_real,
          mode: "lines",
          name: "ε′ reference",
          line: { color: SIGNAL, width: 2, dash: "dot" },
        },
        {
          x: overlay.frequency_hz,
          y: asLossy(overlay.meas_loss, overlay.frequency_hz, mode),
          mode: "markers",
          name: `${name} measured`,
          yaxis: "y2",
          marker: { color: VIOLET, size: 5 },
        },
        {
          x: overlay.frequency_hz,
          y: asLossy(overlay.ref_loss, overlay.frequency_hz, mode),
          mode: "lines",
          name: `${name} reference`,
          yaxis: "y2",
          line: { color: VIOLET, width: 2, dash: "dot" },
        },
      ]}
      layout={{
        ...baseLayout,
        xaxis: { title: { text: "frequency (Hz)" }, type: "log", gridcolor: GRID },
        yaxis: { title: { text: "ε′" }, gridcolor: GRID, zeroline: false },
        yaxis2: {
          title: { text: lossAxisTitle(mode) },
          overlaying: "y",
          side: "right",
          showgrid: false,
          zeroline: false,
        },
      }}
      config={config}
      style={{ width: "100%", height: PLOT_H }}
      useResizeHandler
    />
  );
}

const PALETTE = [
  "#2dd4bf", "#fbbf24", "#a78bfa", "#fb7185", "#60a5fa", "#34d399", "#f472b6", "#f59e0b",
];

export interface OverlaySeries {
  name: string;
  frequency_hz: number[];
  eps_real: number[];
  loss: number[];
}

// One trace per batch — ε′ vs f, σ/ε″ vs f, or a Cole-Cole (ε″ vs ε′, always −Im) overlay.
export function BatchOverlayPlot({
  series,
  field,
  mode = "loss",
}: {
  series: OverlaySeries[];
  field: "eps" | "lossy" | "argand";
  mode?: LossMode;
}) {
  const traces = series.map((s, i) => {
    const color = PALETTE[i % PALETTE.length];
    if (field === "argand") {
      return {
        x: s.eps_real, y: s.loss, mode: "lines+markers", name: s.name,
        line: { color, width: 2 }, marker: { color, size: 4 },
      };
    }
    const y = field === "eps" ? s.eps_real : asLossy(s.loss, s.frequency_hz, mode);
    return {
      x: s.frequency_hz, y, mode: "lines+markers", name: s.name,
      line: { color, width: 2 }, marker: { color, size: 4 },
    };
  });
  const layout =
    field === "argand"
      ? {
          ...baseLayout,
          xaxis: { title: { text: "ε′" }, gridcolor: GRID, zeroline: false },
          yaxis: { title: { text: "ε″ = −Im(ε*)" }, gridcolor: GRID, zeroline: false },
        }
      : {
          ...baseLayout,
          xaxis: { title: { text: "frequency (Hz)" }, type: "log", gridcolor: GRID },
          yaxis: {
            title: { text: field === "eps" ? "ε′" : lossAxisTitle(mode) },
            gridcolor: GRID,
            zeroline: false,
          },
        };
  return (
    <Plot
      data={traces}
      layout={layout}
      config={config}
      style={{ width: "100%", height: PLOT_H }}
      useResizeHandler
    />
  );
}

// Batch-difference Δ(f) with its 95% CI band and the significant points highlighted.
export function DiffPlot({
  frequency,
  delta,
  se,
  significant,
  yTitle,
}: {
  frequency: number[];
  delta: number[];
  se: number[];
  significant: boolean[];
  yTitle: string;
}) {
  const hi = delta.map((d, i) => d + 1.96 * se[i]);
  const lo = delta.map((d, i) => d - 1.96 * se[i]);
  const sigX = frequency.filter((_, i) => significant[i]);
  const sigY = delta.filter((_, i) => significant[i]);
  return (
    <Plot
      data={[
        { x: frequency, y: lo, mode: "lines", line: { width: 0 }, showlegend: false, hoverinfo: "skip" },
        {
          x: frequency, y: hi, mode: "lines", line: { width: 0 }, fill: "tonexty",
          fillcolor: "rgba(148,163,184,0.18)", name: "95% CI", hoverinfo: "skip",
        },
        { x: frequency, y: delta, mode: "lines", name: "Δ", line: { color: SIGNAL, width: 2 } },
        {
          x: sigX, y: sigY, mode: "markers", name: "significant",
          marker: { color: ROSE, size: 6 },
        },
      ]}
      layout={{
        ...baseLayout,
        xaxis: { title: { text: "frequency (Hz)" }, type: "log", gridcolor: GRID },
        yaxis: { title: { text: yTitle }, gridcolor: GRID, zeroline: true, zerolinecolor: "#475569" },
      }}
      config={config}
      style={{ width: "100%", height: PLOT_H }}
      useResizeHandler
    />
  );
}
