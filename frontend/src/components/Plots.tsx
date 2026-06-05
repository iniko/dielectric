// The factory entry's types are declared in shims.d.ts.
import createPlotlyComponent from "react-plotly.js/factory";
import Plotly from "plotly.js-dist-min";
import type { KKDetail, RefOverlay, RepeatBand, ResidualSeries, SpectrumPlot } from "../types";

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

export function BodePlot({ data }: { data: SpectrumPlot }) {
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
          y: data.loss,
          mode: "markers",
          type: "scatter",
          name: "ε″ data",
          yaxis: "y2",
          marker: { color: VIOLET, size: 5 },
        },
        {
          x: data.fit_frequency_hz,
          y: data.fit_loss,
          mode: "lines",
          type: "scatter",
          name: "ε″ fit",
          yaxis: "y2",
          line: { color: VIOLET, width: 2, dash: "dot" },
        },
      ]}
      layout={{
        ...baseLayout,
        xaxis: { title: { text: "frequency (Hz)" }, type: "log", gridcolor: GRID },
        yaxis: { title: { text: "ε′" }, gridcolor: GRID, zeroline: false },
        yaxis2: {
          title: { text: "ε″" },
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
  quantity: "eps" | "sigma";
}) {
  const isEps = quantity === "eps";
  const x = band.frequency_hz;
  const mean = isEps ? band.eps_real : band.sigma;
  const lo = isEps ? band.eps_real_lo : band.sigma_lo;
  const hi = isEps ? band.eps_real_hi : band.sigma_hi;
  const color = isEps ? SIGNAL : VIOLET;
  const rgb = isEps ? "45,212,191" : "167,139,250";
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
          name: isEps ? "ε′ mean" : "σ mean",
          line: { color, width: 2 },
          marker: { color, size: 4 },
        },
      ]}
      layout={{
        ...baseLayout,
        xaxis: { title: { text: "frequency (Hz)" }, type: "log", gridcolor: GRID },
        yaxis: {
          title: { text: isEps ? "ε′" : "σ_eff (S/m)" },
          gridcolor: GRID,
          zeroline: false,
        },
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

// Fit residuals Δε′ and Δε″ (model − data) vs frequency, with a zero reference line.
export function ResidualPlot({ residual }: { residual: ResidualSeries }) {
  return (
    <Plot
      data={[
        {
          x: residual.frequency_hz,
          y: residual.residual_eps_real,
          mode: "markers",
          name: "Δε′",
          marker: { color: SIGNAL, size: 5 },
        },
        {
          x: residual.frequency_hz,
          y: residual.residual_loss,
          mode: "markers",
          name: "Δε″",
          marker: { color: VIOLET, size: 5 },
        },
      ]}
      layout={{
        ...baseLayout,
        xaxis: { title: { text: "frequency (Hz)" }, type: "log", gridcolor: GRID },
        yaxis: { title: { text: "residual (model − data)" }, gridcolor: GRID, zeroline: true,
          zerolinecolor: "#475569" },
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
export function ReferenceOverlayPlot({ overlay }: { overlay: RefOverlay }) {
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
          y: overlay.meas_loss,
          mode: "markers",
          name: "ε″ measured",
          yaxis: "y2",
          marker: { color: VIOLET, size: 5 },
        },
        {
          x: overlay.frequency_hz,
          y: overlay.ref_loss,
          mode: "lines",
          name: "ε″ reference",
          yaxis: "y2",
          line: { color: VIOLET, width: 2, dash: "dot" },
        },
      ]}
      layout={{
        ...baseLayout,
        xaxis: { title: { text: "frequency (Hz)" }, type: "log", gridcolor: GRID },
        yaxis: { title: { text: "ε′" }, gridcolor: GRID, zeroline: false },
        yaxis2: {
          title: { text: "ε″" },
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
