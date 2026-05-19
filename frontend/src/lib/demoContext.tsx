"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Stage } from "@/lib/stages";
import { buildMockState, DEFAULT_HYPOTHESIS } from "@/lib/mockState";
import type { DemoState, PipelineState } from "@/types/schemas";

interface DemoContextValue {
  stage: Stage;
  state: DemoState;
  isRunning: boolean;
  hypothesis: string;
  setHypothesis: (s: string) => void;
  run: () => void;
  reset: () => void;
}

const Ctx = createContext<DemoContextValue | null>(null);

export function DemoProvider({ children }: { children: React.ReactNode }) {
  const [hypothesis, setHypothesis] = useState(DEFAULT_HYPOTHESIS);
  const [stage, setStage] = useState<Stage>(Stage.IDLE);
  const [state, setState] = useState<DemoState>(() => buildMockState(DEFAULT_HYPOTHESIS));
  const [isRunning, setIsRunning] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimer = () => {
    if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
    }
  };

  const reset = useCallback(() => {
    clearTimer();
    setIsRunning(false);
    setStage(Stage.IDLE);
  }, []);

  const run = useCallback(() => {
    clearTimer();
    const fresh = buildMockState(hypothesis);
    setState(fresh);
    setStage(Stage.PARSING);
    setIsRunning(true);

    const apiBase = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
    const minWaitMs = 900;
    const startedAt = Date.now();

    const finish = (data?: Partial<PipelineState>) => {
      if (data) {
        setState((prev) => ({
          ...prev,
          raw_hypothesis: data.raw_hypothesis ?? hypothesis,
          parsed: data.parsed ?? prev.parsed,
          papers: data.papers ?? prev.papers,
          conflicts: data.conflicts ?? prev.conflicts,
          overlaps: data.overlaps ?? prev.overlaps,
          forecast: data.forecast ?? prev.forecast,
          metric_scores: data.metric_scores ?? prev.metric_scores,
          scorecard: data.scorecard ?? prev.scorecard,
          retrieval_report: data.retrieval_report ?? prev.retrieval_report,
          openalex_total_count: data.openalex_total_count ?? prev.openalex_total_count,
          variants:
            data.ranked_variants && data.ranked_variants.length > 0
              ? data.ranked_variants
              : data.variants ?? prev.variants,
          ranked_variants: data.ranked_variants ?? prev.ranked_variants,
          final_memo: data.final_memo ?? prev.final_memo,
        }));
      }
      if (data?.retrieval_report?.status && data.retrieval_report.status !== "ok") {
        console.warn("Literature retrieval completed with warnings.", data.retrieval_report);
      }
      const elapsed = Date.now() - startedAt;
      const delay = Math.max(0, minWaitMs - elapsed);
      timer.current = setTimeout(() => {
        setStage(Stage.DONE);
        setIsRunning(false);
      }, delay);
    };

    fetch(`${apiBase}/api/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ hypothesis }),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((data: Partial<PipelineState>) => finish(data))
      .catch((err) => {
        console.warn("Backend unavailable; showing mock scorecard.", err);
        finish();
      });
  }, [hypothesis]);

  useEffect(() => () => clearTimer(), []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("autostart") === "1") {
      run();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const value = useMemo(
    () => ({ stage, state, isRunning, hypothesis, setHypothesis, run, reset }),
    [stage, state, isRunning, hypothesis, run, reset],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useDemo() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useDemo must be used inside <DemoProvider />");
  return v;
}
