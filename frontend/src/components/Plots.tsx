// The factory entry's types are declared in shims.d.ts.
import createPlotlyComponent from "react-plotly.js/factory";
import Plotly from "plotly.js-dist-min";
import type { SpectrumPlot } from "../types";

const Plot = createPlotlyComponent(Plotly);

const SIGNAL = "#2dd4bf";
const VIOLET = "#a78bfa";
const FIT = "#fbbf24";
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
