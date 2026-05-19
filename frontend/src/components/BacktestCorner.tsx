"use client";

import { useMemo } from "react";
import dynamic from "next/dynamic";
import { IMPACT_DIMENSIONS, type ImpactDimensionKey } from "@/types/schemas";
import correlations from "@/data/backtestCorrelations.json";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

function seededRandom(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 0xffffffff;
  };
}

function generateScatter(seed: number, n = 30, rho = 0.75) {
  const rng = seededRandom(seed);
  const xs: number[] = [];
  const ys: number[] = [];
  for (let i = 0; i < n; i++) {
    const x = rng() * 90 + 5;
    const noise = (rng() - 0.5) * (1 - rho) * 80;
    const y = Math.min(95, Math.max(5, x * rho + noise + 12));
    xs.push(x);
    ys.push(y);
  }
  return { xs, ys };
}

const DIM_RHO: Record<ImpactDimensionKey, number> = {
  volume: correlations.volume.forecaster,
  velocity: correlations.velocity.forecaster,
  reach: correlations.reach.forecaster,
  depth: correlations.depth.forecaster,
  disruption: correlations.disruption.forecaster,
  translation: correlations.translation.forecaster,
};

export default function BacktestCorner() {
  const tiles = useMemo(
    () =>
      IMPACT_DIMENSIONS.map((d, idx) => {
        const { xs, ys } = generateScatter(7919 + idx * 31, 30, Math.max(0.1, Math.abs(DIM_RHO[d])));
        return { dim: d, xs, ys, rho: DIM_RHO[d] };
      }),
    [],
  );

  const baseLayout: Partial<Plotly.Layout> = {
    margin: { l: 4, r: 4, t: 4, b: 4 },
    xaxis: { showticklabels: false, showgrid: false, zeroline: false, range: [0, 100] },
    yaxis: { showticklabels: false, showgrid: false, zeroline: false, range: [0, 100] },
    paper_bgcolor: "#FFFFFF",
    plot_bgcolor: "#FFFFFF",
    showlegend: false,
    shapes: [
      {
        type: "line",
        x0: 0,
        y0: 0,
        x1: 100,
        y1: 100,
        line: { color: "#E3E3E0", width: 1 },
      },
    ],
  };

  return (
    <div className="h-full w-full bg-canvas/70 backdrop-blur-md border border-divider rounded-md overflow-hidden flex flex-col">
      <div className="px-3 pt-2 pb-1 flex items-center justify-between">
        <span className="smallcaps text-muted">Backtest rho</span>
      </div>
      <div className="flex-1 grid grid-cols-3 grid-rows-2 gap-1 p-1.5 min-h-0">
        {tiles.map((t) => (
          <div
            key={t.dim}
            className="relative border border-divider rounded-sm bg-surface overflow-hidden"
          >
            <Plot
              data={[
                {
                  type: "scatter",
                  mode: "markers",
                  x: t.xs,
                  y: t.ys,
                  marker: { color: "#1A1A1A", size: 4 },
                  hoverinfo: "skip",
                },
              ]}
              layout={baseLayout}
              config={{ displayModeBar: false, responsive: true, staticPlot: true }}
              style={{ width: "100%", height: "100%" }}
              useResizeHandler
            />
            <div className="absolute top-1 left-1 text-mono text-[9px] text-muted">
              {t.dim}
            </div>
            <div className="absolute bottom-1 right-1 text-mono text-[9px] text-ink">
              ρ {t.rho.toFixed(2)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
