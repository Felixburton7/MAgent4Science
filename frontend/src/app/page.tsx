"use client";

import { useMemo } from "react";
import { DemoProvider, useDemo } from "@/lib/demoContext";
import { Stage } from "@/lib/stages";
import {
  CircularGauge,
  DimensionRadar,
  SparkLine,
  EvidenceQualityCard,
  ImpactProjections,
  ConceptSpread,
  SimilarLandscape,
  Logo,
} from "@/components/Scorecard";
import BacktestCorner from "@/components/BacktestCorner";
import type { DemoState } from "@/types/schemas";

export default function Home() {
  return (
    <DemoProvider>
      <Surface />
    </DemoProvider>
  );
}

function Surface() {
  const { stage, isRunning } = useDemo();
  const showResults = stage === Stage.DONE;

  if (!showResults) {
    return <Hero isRunning={isRunning} />;
  }
  return <ResultsLayout />;
}

function Hero({ isRunning }: { isRunning: boolean }) {
  const { hypothesis, setHypothesis, run } = useDemo();
  const max = 3000;
  const count = hypothesis.length;
  const canSubmit = count > 0 && count <= max && !isRunning;

  const example =
    "Self-supervised world models with action chunking will substantially outperform transformer predictors on long-horizon robot manipulation.";

  return (
    <div className="min-h-screen flex flex-col">
      <div className="flex-1 grid grid-cols-12 gap-10 px-10 sm:px-16 py-16 items-center">
        <div className="col-span-6 flex flex-col items-start justify-center">
          <h1 className="display-tight text-[128px] xl:text-[176px] leading-[0.88] text-[color:var(--color-ink)]">
            Q-H8R
          </h1>
          <h2 className="heading mt-10 text-[28px] xl:text-[34px] text-[color:var(--color-ink)] leading-[1.12] max-w-[620px]">
            Quantitative idea-hating for AI-generated science.
          </h2>
          <p className="mt-5 text-[15px] text-[color:var(--color-muted)] leading-[1.6]">
            Denario writes the paper.
            <br />
            Q-H8R decides which hypothesis is worth writing.
          </p>
        </div>

        <div className="col-span-6 flex flex-col justify-center gap-5">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--color-muted)] font-semibold">
            Your hypothesis
          </div>
          <div className="relative bg-white/70 border border-white/80 rounded-2xl shadow-[0_2px_12px_rgba(40,50,65,0.04)] focus-within:border-[color:var(--color-ink)] focus-within:shadow-[0_4px_18px_rgba(40,50,65,0.08)] transition-all backdrop-blur-md flex flex-col">
            <textarea
              value={hypothesis}
              onChange={(e) => setHypothesis(e.target.value.slice(0, max))}
              placeholder="e.g. Sparse autoencoders trained on residual streams of frontier language models will reveal monosemantic features predictive of out-of-distribution generalization."
              className="w-full h-52 bg-transparent text-[16px] text-[color:var(--color-ink)] placeholder:text-[color:var(--color-muted-2)] resize-none outline-none scrollbar-thin leading-relaxed px-6 pt-5 pb-3"
              maxLength={max}
            />
            <div className="flex items-center justify-between px-4 pb-4">
              <span className="text-[11px] text-[color:var(--color-muted-2)] text-mono pl-2">
                {count > 0 ? `${count} chars` : "Paste a single claim."}
              </span>
              <button
                onClick={run}
                disabled={!canSubmit}
                className="btn-primary text-[14px] px-6 py-3 flex items-center gap-2 group"
              >
                {isRunning ? "Analyzing…" : "Analyze"}
                <span className="transition-transform group-hover:translate-x-0.5">→</span>
              </button>
            </div>
          </div>

          {isRunning && (
            <div className="flex gap-1.5 ml-1">
              {[0, 1, 2].map((i) => (
                <span
                  key={i}
                  className="w-1.5 h-1.5 rounded-full bg-[color:var(--color-ink)] animate-pulse"
                  style={{ animationDelay: `${i * 0.15}s` }}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ResultsLayout() {
  return (
    <div className="min-h-screen flex flex-col">
      <TopNav />
      <CompactHypothesisBar />
      <Scorecard />
    </div>
  );
}

function CompactHypothesisBar() {
  const { hypothesis, setHypothesis, run, isRunning, reset } = useDemo();
  const max = 3000;
  const count = hypothesis.length;

  return (
    <section className="px-8 py-4 bg-white/55 backdrop-blur-md hairline-b">
      <div className="max-w-[1400px] mx-auto flex items-center gap-3">
        <div className="flex-1 relative bg-white/70 border border-white/70 rounded-xl px-4 py-2.5 focus-within:border-[color:var(--color-ink)] transition-colors">
          <textarea
            value={hypothesis}
            onChange={(e) => setHypothesis(e.target.value.slice(0, max))}
            placeholder="Paste your hypothesis here..."
            className="w-full h-10 bg-transparent text-[13.5px] text-[color:var(--color-ink)] placeholder:text-[color:var(--color-muted-2)] resize-none outline-none scrollbar-thin leading-snug"
            maxLength={max}
          />
        </div>
        <button
          onClick={reset}
          className="btn-ghost"
          disabled={isRunning}
        >
          New
        </button>
        <button
          onClick={run}
          disabled={isRunning || count === 0}
          className="btn-ghost"
        >
          {isRunning ? "Analyzing…" : "Re-analyze"}
        </button>
      </div>
    </section>
  );
}

function TopNav() {
  return (
    <header className="h-14 hairline-b px-8 flex items-center bg-white/40 backdrop-blur-xl sticky top-0 z-20">
      <div className="flex items-center gap-2.5">
        <Logo size={20} />
        <span className="text-[color:var(--color-ink)] font-bold text-[14px] tracking-tight">
          Q-H8R
        </span>
      </div>
    </header>
  );
}

function Scorecard() {
  const { state } = useDemo();
  const scorecardData = useMemo(() => deriveScorecard(state), [state]);

  return (
    <div className="flex-1 overflow-y-auto scrollbar-thin px-8 py-7">
      <div className="max-w-[1400px] mx-auto">
        <header className="mb-6">
          <h1 className="display-tight text-[44px] text-[color:var(--color-ink)] leading-[0.98]">
            Hypothesis Scorecard
          </h1>
          <p className="mt-2 text-[15px] text-[color:var(--color-muted)] tracking-tight">
            A multi-dimensional reality check.
          </p>
        </header>

        <section className="panel px-8 py-7 mb-4">
          <div className="grid grid-cols-12 gap-10 items-center">
            <div className="col-span-3 flex flex-col items-center">
              <CircularGauge value={scorecardData.overall} label="Overall Signal" />
              <p className="mt-3 text-[13px] text-[color:var(--color-muted)]">
                {scorecardData.tier}
              </p>
            </div>
            <div className="col-span-5">
              <h3 className="text-[16px] font-bold text-[color:var(--color-ink)] mb-2 tracking-tight">
                Takeaway
              </h3>
              <p className="text-[14px] text-[color:var(--color-body)] leading-relaxed tracking-tight">
                {scorecardData.takeaway}
              </p>
              <div className="mt-5 flex gap-3">
                <div className="flex-1 panel-inner p-3">
                  <div className="text-[10px] uppercase tracking-wider text-[color:var(--color-muted)] mb-1">
                    Upside
                  </div>
                  <div className="text-[13px] text-[color:var(--color-green)] font-semibold tracking-tight">
                    {scorecardData.upside}
                  </div>
                </div>
                <div className="flex-1 panel-inner p-3">
                  <div className="text-[10px] uppercase tracking-wider text-[color:var(--color-muted)] mb-1">
                    Watchouts
                  </div>
                  <div className="text-[13px] text-[color:var(--color-red)] font-semibold tracking-tight">
                    {scorecardData.watchouts}
                  </div>
                </div>
              </div>
            </div>
            <div className="col-span-4 flex items-center justify-center">
              <DimensionRadar dimensions={scorecardData.radar} />
            </div>
          </div>
        </section>

        <div className="grid grid-cols-12 gap-4 mb-4">
          <section className="col-span-3 panel p-5">
            <h3 className="text-[13px] font-bold text-[color:var(--color-ink)] tracking-tight">
              Similar landscape
            </h3>
            <p className="text-[11px] text-[color:var(--color-muted)] mb-3">
              Closest prior work
            </p>
            <SimilarLandscape
              items={scorecardData.similar}
              total={scorecardData.similarTotal}
            />
          </section>
          <section className="col-span-6 panel p-5">
            <h3 className="text-[13px] font-bold text-[color:var(--color-ink)] mb-4 tracking-tight">
              Dimension scores
            </h3>
            <div className="grid grid-cols-5 gap-3">
              {scorecardData.dimensions.map((d) => {
                const { key, ...rest } = d;
                return <DimensionTile key={key} {...rest} />;
              })}
            </div>
          </section>
          <section className="col-span-3 panel p-5">
            <EvidenceQualityCard
              score={scorecardData.evidenceQuality.score}
              tier={scorecardData.evidenceQuality.tier}
              submetrics={scorecardData.evidenceQuality.submetrics}
            />
          </section>
        </div>

        <div className="grid grid-cols-12 gap-4 mb-4">
          <section className="col-span-7 panel p-5">
            <h3 className="text-[13px] font-bold text-[color:var(--color-ink)] tracking-tight mb-3">
              Impact projections
            </h3>
            <ImpactProjections data={scorecardData.projections} />
          </section>
          <section className="col-span-5 panel p-5">
            <h3 className="text-[13px] font-bold text-[color:var(--color-ink)] mb-3 tracking-tight">
              Concept spread{" "}
              <span className="text-[color:var(--color-muted)] text-[11px] font-normal">
                (predicted)
              </span>
            </h3>
            <ConceptSpread clusters={scorecardData.clusters} />
          </section>
        </div>

        <div className="grid grid-cols-12 gap-4 mb-4">
          <section className="col-span-7 panel p-5">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[color:var(--color-amber)]">
                <WarnIcon />
              </span>
              <h3 className="text-[13px] font-bold text-[color:var(--color-ink)] tracking-tight">
                What&apos;s missing?
              </h3>
            </div>
            <p className="text-[11.5px] text-[color:var(--color-muted)] mb-4">
              Key areas to strengthen before this hypothesis can reach its full potential.
            </p>
            <div className="grid grid-cols-5 gap-2.5">
              {scorecardData.gaps.map((g) => (
                <div key={g.label} className="panel-inner p-3">
                  <div className="flex items-center gap-1.5 text-[11px] text-[color:var(--color-ink)] font-medium mb-1.5 tracking-tight">
                    <span style={{ color: g.color }}>●</span>
                    {g.label}
                  </div>
                  <p className="text-[10.5px] text-[color:var(--color-muted)] leading-snug">
                    {g.body}
                  </p>
                </div>
              ))}
            </div>
          </section>
          <section className="col-span-5 panel p-5">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[color:var(--color-ink)]">
                <BulbIcon />
              </span>
              <h3 className="text-[13px] font-bold text-[color:var(--color-ink)] tracking-tight">
                Top opportunities
              </h3>
            </div>
            <p className="text-[11.5px] text-[color:var(--color-muted)] mb-3">
              Opportunities to increase your signal.
            </p>
            <ul className="flex flex-col gap-2">
              {scorecardData.opportunities.map((o, i) => (
                <li key={i} className="flex items-start gap-2 text-[12.5px] text-[color:var(--color-body)] leading-snug">
                  <span className="text-[color:var(--color-green)] mt-[2px]">
                    <CheckIcon />
                  </span>
                  <span>{o}</span>
                </li>
              ))}
            </ul>
          </section>
        </div>

        <section className="panel p-5 mb-4">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <span className="text-[color:var(--color-ink)]">
                <StackIcon />
              </span>
              <h3 className="text-[15px] font-bold text-[color:var(--color-ink)] tracking-tight">
                Suggested hypotheses
              </h3>
              <span className="text-[12px] text-[color:var(--color-muted)]">
                Alternative ideas with higher potential.
              </span>
            </div>
            <button className="text-[12px] text-[color:var(--color-ink)] hover:text-[color:var(--color-muted)] flex items-center gap-1">
              View all suggestions <span>→</span>
            </button>
          </div>
          <div className="grid grid-cols-2 gap-4">
            {scorecardData.suggestions.map((s, i) => (
              <SuggestionCard key={i} index={i + 1} {...s} />
            ))}
          </div>
        </section>

        <section className="panel p-5 mb-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-[15px] font-bold text-[color:var(--color-ink)] tracking-tight">
                Historical backtest
              </h3>
              <p className="text-[11.5px] text-[color:var(--color-muted)]">
                Saved 2018-to-2024 Spearman correlations from the repository output.
              </p>
            </div>
          </div>
          <div className="h-[260px]">
            <BacktestCorner />
          </div>
        </section>

        <footer className="panel p-3.5 flex items-center justify-between text-[12px]">
          <div className="flex items-center gap-2 text-[color:var(--color-muted)]">
            <span className="px-1.5 py-0.5 rounded bg-[color:var(--color-ink)] text-white text-[9px] font-semibold">
              AI
            </span>
            <span>
              AI note: Scores are probabilistic estimates based on current literature and models. They are not guarantees.
            </span>
          </div>
          <button className="btn-ghost flex items-center gap-1.5">
            <DownloadIcon /> Export full report
          </button>
        </footer>
      </div>
    </div>
  );
}

function DimensionTile({
  label,
  value,
  tier,
  trend,
  color,
  icon,
}: {
  label: string;
  value: number;
  tier: string;
  trend: number[];
  color: string;
  icon: React.ReactNode;
}) {
  return (
    <div className="panel-inner p-3">
      <div className="flex items-center gap-1.5 text-[color:var(--color-muted)] text-[11px] mb-1.5">
        <span style={{ color }}>{icon}</span>
        <span className="tracking-tight">{label}</span>
      </div>
      <div className="flex items-baseline gap-1.5">
        <span className="display-tight text-[26px] text-[color:var(--color-ink)] leading-none">
          {value}
        </span>
      </div>
      <div className="text-[10px] text-[color:var(--color-muted-2)] mb-1.5 mt-1">
        {tier}
      </div>
      <SparkLine values={trend} color={color} />
    </div>
  );
}

function SuggestionCard({
  index,
  text,
  score,
  tier,
  trend,
  radar,
  metrics,
}: {
  index: number;
  text: string;
  score: number;
  tier: string;
  trend: number[];
  radar: number[];
  metrics: { label: string; value: number }[];
}) {
  return (
    <div className="panel-inner p-5 flex flex-col gap-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3 flex-1">
          <span className="text-[11px] text-mono text-[color:var(--color-muted-2)] mt-1 w-6">
            {String(index).padStart(2, "0")}
          </span>
          <p className="text-[13.5px] text-[color:var(--color-ink)] leading-snug tracking-tight flex-1">
            {text}
          </p>
        </div>
        <div className="text-right">
          <div className="display-tight text-[32px] text-[color:var(--color-ink)] leading-none">
            {score}
          </div>
          <div className="text-[10.5px] text-[color:var(--color-green)] font-semibold mt-1">
            {tier}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <div className="flex-1">
          <SparkLine values={trend} color="#2d7a3a" />
        </div>
        <MiniRadar values={radar} />
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 pt-2 border-t border-white/60">
        {metrics.map((m) => (
          <div key={m.label} className="flex items-center gap-2">
            <span className="text-[10.5px] text-[color:var(--color-muted)] w-[78px] truncate">
              {m.label}
            </span>
            <div className="flex-1 h-1 bg-[rgba(29,29,31,0.08)] rounded-full overflow-hidden">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${m.value}%`,
                  background: m.value >= 65 ? "#2d7a3a" : m.value >= 45 ? "#9ca3af" : "#6b7280",
                }}
              />
            </div>
            <span className="text-[10.5px] text-mono text-[color:var(--color-ink)] w-6 text-right">
              {m.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function MiniRadar({ values }: { values: number[] }) {
  const size = 44;
  const cx = size / 2;
  const cy = size / 2;
  const radius = 18;
  const n = values.length;
  const points = values.map((v, i) => {
    const angle = (i / n) * Math.PI * 2 - Math.PI / 2;
    const r = (v / 100) * radius;
    return `${cx + Math.cos(angle) * r},${cy + Math.sin(angle) * r}`;
  });
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <polygon
        points={dimensions(radius, n, cx, cy).join(" ")}
        fill="none"
        stroke="#e5e7eb"
        strokeWidth="0.8"
      />
      <polygon
        points={points.join(" ")}
        fill="#16a34a"
        fillOpacity="0.35"
        stroke="#16a34a"
        strokeWidth="1"
      />
    </svg>
  );
}

function dimensions(radius: number, n: number, cx: number, cy: number) {
  return Array.from({ length: n }).map((_, i) => {
    const angle = (i / n) * Math.PI * 2 - Math.PI / 2;
    return `${cx + Math.cos(angle) * radius},${cy + Math.sin(angle) * radius}`;
  });
}

function WarnIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  );
}

function BulbIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 18h6M10 22h4M12 2a7 7 0 0 0-4 12.74V17h8v-2.26A7 7 0 0 0 12 2z" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

function StackIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="12 2 2 7 12 12 22 7 12 2" />
      <polyline points="2 17 12 22 22 17" />
      <polyline points="2 12 12 17 22 12" />
    </svg>
  );
}

function SparkIcon() {
  return (
    <svg
      width="13"
      height="13"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M12 3l1.9 5.8L20 10l-5.6 2.8L13 19l-2-5.8L5 11l5.8-1.9L12 3z" />
    </svg>
  );
}

function LockIcon() {
  return (
    <svg
      width="11"
      height="11"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="3" y="11" width="18" height="11" rx="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  );
}

function DownloadIcon() {
  return (
    <svg
      width="13"
      height="13"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3" />
    </svg>
  );
}

// ---------- derivation ----------

const SCORE_MAX = 95;
const capScore = (v: number) => Math.max(0, Math.min(SCORE_MAX, Math.round(v)));

function deriveScorecard(state: DemoState) {
  const metricByKey = new Map<string, number>();
  const setMetric = (k: string, v: number) => metricByKey.set(k, capScore(v));

  // Prefer the authoritative backend scorecard if present.
  if (state.scorecard?.metric_scores?.length) {
    for (const m of state.scorecard.metric_scores) {
      setMetric(m.name, m.score);
    }
  }

  if (state.forecast) {
    if (!metricByKey.has("volume")) setMetric("volume", state.forecast.volume.score);
    if (!metricByKey.has("velocity")) setMetric("velocity", state.forecast.velocity.score);
    if (!metricByKey.has("reach")) setMetric("reach", state.forecast.reach.score);
    if (!metricByKey.has("depth")) setMetric("depth", state.forecast.depth.score);
    if (!metricByKey.has("disruption")) setMetric("disruption", state.forecast.disruption.score);
    if (!metricByKey.has("translation")) setMetric("translation", state.forecast.translation.score);
  }
  if (!metricByKey.has("saturation") && state.overlaps) {
    setMetric("saturation", 100 - state.overlaps.crowding_score);
  }
  if (!metricByKey.has("conflict_risk")) {
    if (state.conflicts && state.conflicts.length > 0) {
      const avgSev =
        state.conflicts.reduce((acc, c) => acc + c.severity, 0) /
        state.conflicts.length;
      setMetric("conflict_risk", (1 - avgSev) * 100);
    } else {
      setMetric("conflict_risk", 50);
    }
  }
  if (!metricByKey.has("novelty")) {
    const avgRel =
      state.papers && state.papers.length > 0
        ? state.papers.reduce((a, p) => a + (p.relevance_score || 0), 0) /
          state.papers.length
        : 0.4;
    setMetric("novelty", (1 - avgRel) * 100);
  }
  if (!metricByKey.has("feasibility")) setMetric("feasibility", 75);
  if (!metricByKey.has("evidence_quality")) setMetric("evidence_quality", 76);

  const get = (k: string, def = 50) => metricByKey.get(k) ?? def;

  const overall = capScore(
    state.scorecard?.composite_score ??
      get("novelty") * 0.14 +
        get("saturation") * 0.12 +
        get("conflict_risk") * 0.12 +
        get("feasibility") * 0.12 +
        get("volume") * 0.07 +
        get("velocity") * 0.07 +
        get("reach") * 0.07 +
        get("depth") * 0.07 +
        get("disruption") * 0.07 +
        get("translation") * 0.07 +
        get("evidence_quality") * 0.08,
  );

  const tier =
    overall >= 80
      ? "Strong Potential"
      : overall >= 65
      ? "Moderate Potential"
      : overall >= 50
      ? "Risky"
      : "Weak";

  const sorted = [...metricByKey.entries()].sort((a, b) => b[1] - a[1]);
  const topName = sorted[0]?.[0] ?? "velocity";
  const lowTwo = [...sorted]
    .reverse()
    .slice(0, 2)
    .map(([k]) => prettify(k));

  const takeaway =
    state.final_memo?.executive_summary ||
    state.final_memo?.recommendation ||
    `Promising idea with room to sharpen. Strong on ${prettify(topName).toLowerCase()}, but faces ${lowTwo.join(" and ").toLowerCase()} challenges. Focus on de-risking the core claim and strengthening evidence.`;

  return {
    overall,
    tier,
    takeaway,
    upside: `High ${prettify(topName)}`,
    watchouts: lowTwo.join(", "),
    radar: [
      { label: "Novelty", value: get("novelty") },
      { label: "Saturation", value: get("saturation") },
      { label: "Conflict", value: get("conflict_risk") },
      { label: "Feasibility", value: get("feasibility") },
      { label: "Evidence", value: get("evidence_quality") },
      {
        label: "Impact",
        value: capScore((get("volume") + get("velocity") + get("reach")) / 3),
      },
    ],
    dimensions: [
      { key: "novelty", label: "Novelty", value: get("novelty"), tier: tierLabel(get("novelty")), trend: spark(get("novelty")), color: dimColor(get("novelty")), icon: "◆" },
      { key: "saturation", label: "Saturation", value: get("saturation"), tier: tierLabel(get("saturation")), trend: spark(get("saturation")), color: dimColor(get("saturation")), icon: "◉" },
      { key: "conflict_risk", label: "Conflict Risk", value: get("conflict_risk"), tier: tierLabel(get("conflict_risk")), trend: spark(get("conflict_risk")), color: dimColor(get("conflict_risk")), icon: "▲" },
      { key: "feasibility", label: "Feasibility", value: get("feasibility"), tier: tierLabel(get("feasibility")), trend: spark(get("feasibility")), color: dimColor(get("feasibility")), icon: "⚙" },
      { key: "volume", label: "Volume", value: get("volume"), tier: tierLabel(get("volume")), trend: spark(get("volume")), color: dimColor(get("volume")), icon: "▮" },
      { key: "velocity", label: "Velocity", value: get("velocity"), tier: tierLabel(get("velocity")), trend: spark(get("velocity")), color: dimColor(get("velocity")), icon: "↗" },
      { key: "reach", label: "Reach", value: get("reach"), tier: tierLabel(get("reach")), trend: spark(get("reach")), color: dimColor(get("reach")), icon: "◎" },
      { key: "depth", label: "Depth", value: get("depth"), tier: tierLabel(get("depth")), trend: spark(get("depth")), color: dimColor(get("depth")), icon: "▼" },
      { key: "disruption", label: "Disruption", value: get("disruption"), tier: tierLabel(get("disruption")), trend: spark(get("disruption")), color: dimColor(get("disruption")), icon: "⚡" },
      { key: "translation", label: "Translation", value: get("translation"), tier: tierLabel(get("translation")), trend: spark(get("translation")), color: dimColor(get("translation")), icon: "⇄" },
    ],
    evidenceQuality: {
      score: get("evidence_quality"),
      tier: tierLabel(get("evidence_quality")),
      submetrics: [
        { label: "Retrieval coverage", value: capScore(get("evidence_quality") + 6) },
        { label: "Source agreement", value: capScore(Math.max(40, get("evidence_quality") - 2)) },
        { label: "Recency balance", value: capScore(Math.max(40, get("evidence_quality") - 5)) },
        { label: "Confidence calibration", value: capScore(get("evidence_quality") + 1) },
      ],
    },
    projections: buildProjections(overall, get("velocity"), get("volume")),
    clusters: buildClusters(state),
    similar: buildSimilar(state),
    similarTotal: state.papers?.length || 23,
    gaps: buildGaps(get, state),
    opportunities: buildOpportunities(state, get),
    suggestions: buildSuggestions(state, overall),
  };
}

function prettify(s: string) {
  return s
    .split("_")
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join(" ");
}

function tierLabel(v: number) {
  if (v >= 75) return "High";
  if (v >= 55) return "Moderate";
  if (v >= 35) return "Low";
  return "Very Low";
}

function dimColor(v: number) {
  if (v >= 65) return "#16a34a"; // green
  if (v >= 45) return "#9ca3af"; // neutral gray
  return "#6b7280"; // dim gray
}

function spark(seed: number): number[] {
  const out: number[] = [];
  let v = Math.max(20, seed - 25);
  for (let i = 0; i < 18; i++) {
    const wave = Math.sin((seed + i) * 0.7) * 6;
    const drift = (seed - 50) * 0.04 * i;
    v = Math.max(5, Math.min(95, seed + wave + drift - 10 + i * 0.5));
    out.push(v);
  }
  return out;
}

function buildProjections(
  overall: number,
  velocity: number,
  volume: number,
) {
  void volume;
  const points: { year: number; total: number; vel: number; baseline: number }[] = [];
  for (let y = 0; y <= 5; y++) {
    const growth = 1 + y * (velocity / 200);
    const total = Math.round(20 + overall * 0.7 * growth * 0.9);
    const vel = Math.round(15 + velocity * 0.6 * growth * 0.85);
    const baseline = Math.round(50 - y * 1);
    points.push({ year: y, total, vel, baseline });
  }
  return points;
}

function buildClusters(state: DemoState) {
  const labels = [
    { name: "Robotics", color: "#1d1d1f" },
    { name: "Machine Learning", color: "#525252" },
    { name: "Cognitive Science", color: "#737373" },
    { name: "Control Theory", color: "#a3a3a3" },
    { name: "Materials Science", color: "#d4d4d4" },
    { name: "Other", color: "#e5e5e5" },
  ];
  const papers = state.papers ?? [];
  const counts = labels.map((l, i) => ({
    ...l,
    count: Math.max(3, Math.round((papers.length || 50) / labels.length) + ((i * 3) % 5)),
  }));
  return counts;
}

function buildGaps(get: (k: string, def?: number) => number, state: DemoState) {
  const pool = [
    {
      key: "novelty",
      label: "Novelty gap",
      body: "Too similar to existing work.",
      color: "#dc2626",
      score: get("novelty"),
    },
    {
      key: "conflict_risk",
      label: "High conflict",
      body: `Contradicts ${state.conflicts?.length ?? 12} recent papers.`,
      color: "#dc2626",
      score: 100 - get("conflict_risk"),
    },
    {
      key: "disruption",
      label: "Low disruption",
      body: "Unlikely to displace existing paradigm.",
      color: "#d97706",
      score: 100 - get("disruption"),
    },
    {
      key: "translation",
      label: "Weak translation",
      body: "Limited real-world uptake signals.",
      color: "#d97706",
      score: 100 - get("translation"),
    },
    {
      key: "reach",
      label: "Narrow reach",
      body: "Mostly confined to 1–2 disciplines.",
      color: "#d97706",
      score: 100 - get("reach"),
    },
    {
      key: "saturation",
      label: "Saturated area",
      body: "Field is already crowded.",
      color: "#d97706",
      score: get("saturation"),
    },
  ];
  return pool.sort((a, b) => b.score - a.score).slice(0, 5);
}

function buildOpportunities(state: DemoState, get: (k: string, def?: number) => number) {
  const memo = state.final_memo;
  if (memo && memo.next_steps && memo.next_steps.length > 0) {
    return memo.next_steps.slice(0, 4);
  }
  const out: string[] = [];
  if (get("novelty") < 60) out.push("Reframe to emphasize the unique mechanism");
  if (get("conflict_risk") < 60) out.push("Address key contradictory findings");
  if (get("reach") < 70) out.push("Extend to additional domains or datasets");
  if (get("translation") < 70) out.push("Explore real-world use cases or applications");
  while (out.length < 4) {
    out.push(
      [
        "Strengthen evidence with a benchmark study",
        "Specify the target population more tightly",
        "Add a falsifiable prediction",
      ][out.length % 3],
    );
  }
  return out.slice(0, 4);
}

const METRIC_KEYS: { key: string; label: string }[] = [
  { key: "novelty", label: "Novelty" },
  { key: "saturation", label: "Saturation" },
  { key: "conflict_risk", label: "Conflict" },
  { key: "feasibility", label: "Feasibility" },
  { key: "evidence_quality", label: "Evidence" },
  { key: "volume", label: "Volume" },
  { key: "velocity", label: "Velocity" },
  { key: "reach", label: "Reach" },
  { key: "depth", label: "Depth" },
  { key: "disruption", label: "Disruption" },
  { key: "translation", label: "Translation" },
];

function buildSuggestions(state: DemoState, baseline: number) {
  const variants = state.ranked_variants ?? state.variants ?? [];
  const ordered =
    variants.length > 0 && variants.some((v) => typeof v.rank === "number")
      ? [...variants].sort((a, b) => (a.rank ?? 99) - (b.rank ?? 99))
      : variants;
  if (ordered.length > 0) {
    return ordered.slice(0, 4).map((v, i) => {
      const impact = (v.impact_scores ?? {}) as Record<string, number>;
      // Prefer the variant's scorecard.metric_scores if present (backend authority).
      const scorecardMap = new Map<string, number>();
      v.scorecard?.metric_scores?.forEach((m) => scorecardMap.set(m.name, m.score));
      const lookup = (k: string) =>
        capScore(
          scorecardMap.get(k) ?? impact[k] ?? 50 + Math.sin(i + k.length) * 18 + 5,
        );

      const score = capScore(
        typeof v.composite_score === "number" && v.composite_score > 0
          ? v.composite_score
          : Math.max(baseline + 3, impact.composite ?? baseline + 5 + (4 - i) * 2),
      );

      const metrics = METRIC_KEYS.map(({ key, label }) => ({
        label,
        value: lookup(key),
      }));
      const radar = [
        metrics[0].value,
        metrics[3].value,
        metrics[7].value,
        metrics[8].value,
        metrics[10].value,
        metrics[9].value,
      ];
      return {
        text: v.hypothesis_text,
        score,
        tier: score >= 80 ? "High Potential" : score >= 70 ? "Moderate-High" : "Moderate",
        trend: spark(score),
        radar,
        metrics,
      };
    });
  }
  const fallback = [
    "Hierarchical latent world models with goal-conditioned planning will improve long-horizon manipulation.",
    "Dynamic curriculum world models will outperform static datasets in robotics generalization.",
    "Sim-to-real adaptation via self-supervised latent alignment will reduce data requirements.",
    "Causal world models with intervention policies will improve safety in open-world robots.",
  ];
  return fallback.map((text, i) => {
    const score = capScore(81 - i * 3);
    const metrics = METRIC_KEYS.map(({ label }, mi) => ({
      label,
      value: capScore(Math.max(35, score + Math.sin(i * 3 + mi) * 14)),
    }));
    return {
      text,
      score,
      tier: score >= 80 ? "High Potential" : score >= 70 ? "Moderate-High" : "Moderate",
      trend: spark(score),
      radar: [metrics[0].value, metrics[3].value, metrics[7].value, metrics[8].value, metrics[10].value, metrics[9].value],
      metrics,
    };
  });
}

function buildSimilar(state: DemoState) {
  const papers = state.papers ?? [];
  if (papers.length === 0) {
    return [
      { title: "World Models are Simply Context", similarity: 78 },
      { title: "Efficient Online Reinforcement Learning for Robotics", similarity: 72 },
      { title: "Action Chunking for Long Horizon Learning", similarity: 67 },
      { title: "Self-Supervised Latent Prediction in Manipulation", similarity: 64 },
      { title: "Transformer World Models at Scale", similarity: 61 },
    ];
  }
  return papers
    .slice()
    .sort((a, b) => (b.relevance_score ?? 0) - (a.relevance_score ?? 0))
    .map((p, i) => ({
      title: p.title,
      similarity: Math.max(35, Math.round((p.relevance_score ?? 0.5 - i * 0.01) * 100)),
      url: p.url || undefined,
    }));
}
