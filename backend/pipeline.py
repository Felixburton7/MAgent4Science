from __future__ import annotations

import importlib
import inspect
import asyncio
import operator
import warnings
from datetime import datetime
from typing import Annotated, Any, Callable, List, Optional, TypedDict

try:
    from langchain_core._api.deprecation import (
        LangChainDeprecationWarning,
        LangChainPendingDeprecationWarning,
    )

    warnings.filterwarnings("ignore", category=LangChainDeprecationWarning)
    warnings.filterwarnings("ignore", category=LangChainPendingDeprecationWarning)
except ImportError:
    pass

from langgraph.graph import END, StateGraph

try:
    from langgraph.types import Send
except ImportError:
    from langgraph.constants import Send

from backend.schemas import (
    Conflict,
    ImpactDimension,
    ImpactForecast,
    MetricScore,
    OverlapReport,
    Paper,
    ParsedHypothesis,
    RetrievalReport,
    Scorecard,
    StrategyMemo,
    Variant,
)
from backend.tracing import observe


class PipelineState(TypedDict, total=False):
    raw_hypothesis: str
    parsed: ParsedHypothesis
    papers: List[Paper]
    conflicts: List[Conflict]
    overlaps: OverlapReport
    forecast: ImpactForecast
    metric_scores: Annotated[List[MetricScore], operator.add]
    scorecard: Scorecard
    variants: List[Variant]
    current_variant: Variant
    rescored_variants: Annotated[List[Variant], operator.add]
    pareto_variants: List[Variant]
    ranked_variants: List[Variant]
    final_memo: StrategyMemo
    information_cutoff_year: Optional[int]
    backtest_metadata: Optional[dict]
    openalex_total_count: Optional[int]
    retrieval_report: Optional[RetrievalReport]


PartialState = dict[str, Any]
AgentFn = Callable[[PipelineState], PartialState | Any]


async def _call_agent(
    agent_name: str,
    fallback: AgentFn,
    state: PipelineState,
    aliases: tuple[str, ...] = (),
) -> PartialState:
    func = _load_agent(agent_name, fallback, aliases)
    result = func(state)
    if inspect.isawaitable(result):
        result = await result
    return result


def _load_agent(agent_name: str, fallback: AgentFn, aliases: tuple[str, ...] = ()) -> AgentFn:
    for candidate in (agent_name, *aliases):
        module_name = f"backend.{candidate}"
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name == module_name:
                continue
            raise

        implementation = (
            getattr(module, candidate, None)
            or getattr(module, agent_name, None)
            or getattr(module, "run", None)
        )
        if implementation is not None:
            return implementation
    raise RuntimeError(f"No production implementation found for backend.{agent_name}.")


@observe(name="parser")
async def parser(state: PipelineState) -> PartialState:
    return await _call_agent("parser", _parser_stub, state)


@observe(name="cartographer")
async def cartographer(state: PipelineState) -> PartialState:
    return await _call_agent("cartographer", _cartographer_stub, state)


@observe(name="novelty_scorer")
async def novelty_scorer(state: PipelineState) -> PartialState:
    return await _call_agent("novelty_scorer", _novelty_scorer_stub, state)


@observe(name="saturation_scorer")
async def saturation_scorer(state: PipelineState) -> PartialState:
    return await _call_agent("saturation_scorer", _saturation_scorer_stub, state)


@observe(name="conflict_scorer")
async def conflict_scorer(state: PipelineState) -> PartialState:
    return await _call_agent("conflict_scorer", _conflict_scorer_stub, state)


@observe(name="feasibility_scorer")
async def feasibility_scorer(state: PipelineState) -> PartialState:
    return await _call_agent("feasibility_scorer", _feasibility_scorer_stub, state)


@observe(name="impact_forecaster")
async def impact_forecaster(state: PipelineState) -> PartialState:
    result = await _call_agent("impact_forecaster", _impact_forecaster_stub, state)
    if "forecast" in result and "metric_scores" not in result:
        result = {
            **result,
            "metric_scores": _impact_metric_scores(result["forecast"], state),
        }
    return result


@observe(name="evidence_quality_scorer")
async def evidence_quality_scorer(state: PipelineState) -> PartialState:
    return await _call_agent("evidence_quality_scorer", _evidence_quality_scorer_stub, state)


@observe(name="score_aggregator")
async def score_aggregator(state: PipelineState) -> PartialState:
    return await _call_agent("score_aggregator", _score_aggregator_stub, state)


@observe(name="mutator")
async def mutator(state: PipelineState) -> PartialState:
    return await _call_agent("mutator", _mutator_stub, state)


@observe(name="variant_rescorer")
async def variant_rescorer(state: PipelineState) -> PartialState:
    return await _call_agent("variant_rescorer", _variant_rescorer_stub, state)


@observe(name="pareto_curator")
async def pareto_curator(state: PipelineState) -> PartialState:
    return await _call_agent("pareto_curator", _ranker_stub, state)


@observe(name="ranker")
async def ranker(state: PipelineState) -> PartialState:
    result = await _call_agent("ranker", _ranker_stub, state)
    if "ranked_variants" not in result and "variants" in result:
        result = _rank_variants(result["variants"])
    return result


@observe(name="strategist")
async def strategist(state: PipelineState) -> PartialState:
    return await _call_agent("strategist", _strategist_stub, state)


def build_graph():
    graph = StateGraph(PipelineState)

    graph.add_node("parser", parser)
    graph.add_node("cartographer", cartographer)
    graph.add_node("novelty_scorer", novelty_scorer)
    graph.add_node("saturation_scorer", saturation_scorer)
    graph.add_node("conflict_scorer", conflict_scorer)
    graph.add_node("feasibility_scorer", feasibility_scorer)
    graph.add_node("impact_forecaster", impact_forecaster)
    graph.add_node("evidence_quality_scorer", evidence_quality_scorer)
    graph.add_node("score_aggregator", score_aggregator)
    graph.add_node("mutator", mutator)
    graph.add_node("variant_rescorer", variant_rescorer)
    graph.add_node("pareto_curator", pareto_curator)
    graph.add_node("ranker", ranker)
    graph.add_node("strategist", strategist)

    graph.set_entry_point("parser")

    graph.add_edge("parser", "cartographer")

    metric_nodes = [
        "novelty_scorer",
        "saturation_scorer",
        "conflict_scorer",
        "feasibility_scorer",
        "impact_forecaster",
        "evidence_quality_scorer",
    ]
    for node in metric_nodes:
        graph.add_edge("cartographer", node)

    graph.add_edge(metric_nodes, "score_aggregator")
    graph.add_edge("score_aggregator", "mutator")
    graph.add_conditional_edges(
        "mutator",
        _dispatch_variant_rescorers,
        ["variant_rescorer"],
    )
    graph.add_edge("variant_rescorer", "pareto_curator")
    graph.add_edge("pareto_curator", "ranker")
    graph.add_edge("ranker", "strategist")
    graph.add_edge("strategist", END)

    return graph.compile()


async def run_pipeline(
    raw_hypothesis: str,
    *,
    information_cutoff_year: Optional[int] = None,
    backtest_metadata: Optional[dict] = None,
) -> PipelineState:
    app = build_graph()
    initial_state = _initial_state(
        raw_hypothesis,
        information_cutoff_year=information_cutoff_year,
        backtest_metadata=backtest_metadata,
    )
    return await app.ainvoke(initial_state)


async def run_scorecard_pipeline(
    raw_hypothesis: str,
    *,
    information_cutoff_year: Optional[int] = None,
    backtest_metadata: Optional[dict] = None,
) -> PipelineState:
    state = _initial_state(
        raw_hypothesis,
        information_cutoff_year=information_cutoff_year,
        backtest_metadata=backtest_metadata,
    )

    for node in (parser, cartographer):
        _merge_partial_state(state, await node(state))

    metric_results = await asyncio.gather(
        novelty_scorer(state),
        saturation_scorer(state),
        conflict_scorer(state),
        feasibility_scorer(state),
        impact_forecaster(state),
        evidence_quality_scorer(state),
    )
    for result in metric_results:
        _merge_partial_state(state, result)

    _merge_partial_state(state, await score_aggregator(state))
    return state


def _initial_state(
    raw_hypothesis: str,
    *,
    information_cutoff_year: Optional[int] = None,
    backtest_metadata: Optional[dict] = None,
) -> PipelineState:
    state: PipelineState = {
        "raw_hypothesis": raw_hypothesis,
        "metric_scores": [],
        "rescored_variants": [],
    }
    if information_cutoff_year is not None:
        state["information_cutoff_year"] = information_cutoff_year
    if backtest_metadata is not None:
        state["backtest_metadata"] = backtest_metadata
    return state


def _merge_partial_state(state: PipelineState, update: PartialState) -> None:
    for key, value in update.items():
        if key == "metric_scores":
            state.setdefault("metric_scores", [])
            state["metric_scores"].extend(value or [])
        elif key == "rescored_variants":
            state.setdefault("rescored_variants", [])
            state["rescored_variants"].extend(value or [])
        else:
            state[key] = value


def _dispatch_variant_rescorers(state: PipelineState) -> list[Send]:
    return [
        Send(
            "variant_rescorer",
            {
                "raw_hypothesis": state["raw_hypothesis"],
                "parsed": state["parsed"],
                "papers": state.get("papers", []),
                "conflicts": state.get("conflicts", []),
                "overlaps": state.get("overlaps"),
                "forecast": state.get("forecast"),
                "metric_scores": state.get("metric_scores", []),
                "scorecard": state["scorecard"],
                "variants": state.get("variants", []),
                "current_variant": variant,
                "information_cutoff_year": state.get("information_cutoff_year"),
                "backtest_metadata": state.get("backtest_metadata"),
                "retrieval_report": state.get("retrieval_report"),
            },
        )
        for variant in state.get("variants", [])
    ]


async def _parser_stub(state: PipelineState) -> PartialState:
    hypothesis = state["raw_hypothesis"]
    return {
        "parsed": ParsedHypothesis(
            claim=f"Mock structured claim extracted from: {hypothesis}",
            mechanism="Mock mechanism: quantitative pathway 42.",
            context="Mock context: literature-backed Idea Hater demo.",
            population="Mock population: target research setting.",
            method="Mock method: measurable intervention and outcome.",
        )
    }


async def _cartographer_stub(state: PipelineState) -> PartialState:
    papers = [
        Paper(
            paper_id=f"mock-paper-{idx:02d}",
            title=f"Mock literature neighbour {idx:02d}",
            authors=[f"Fake Author {idx}", f"Demo Collaborator {idx}"],
            year=2020 + (idx % 5),
            abstract=f"Obviously fake abstract for quantitative scoring paper {idx}.",
            url=f"https://example.test/mock-paper-{idx:02d}",
            citation_count=idx * 9,
            relevance_score=round(1.0 - (idx * 0.012), 3),
            cluster=f"mock-evidence-cluster-{(idx % 6) + 1}",
            doi=f"10.1000/mock.{idx:02d}" if idx <= 20 else "",
            openalex_id=f"https://openalex.org/W{100000 + idx}",
            semantic_scholar_id=f"S2-MOCK-{idx:02d}",
            source_provenance=["openalex", "semantic_scholar"] if idx <= 15 else ["openalex"],
        )
        for idx in range(1, 51)
    ]
    return {"papers": papers}


async def _novelty_scorer_stub(state: PipelineState) -> PartialState:
    papers = sorted(
        state.get("papers", []),
        key=lambda paper: (paper.relevance_score, paper.citation_count),
        reverse=True,
    )
    if not papers:
        return {
            "metric_scores": [
                _metric(
                    "novelty",
                    50,
                    "Novelty defaults to neutral when no literature neighbourhood is available.",
                    [],
                    "Retrieve papers before trusting this metric.",
                    method="fallback:no_papers",
                )
            ]
        }

    neighbours = [paper for paper in papers if paper.relevance_score >= 0.6][:5]
    current_year = datetime.now().year
    nearest_year = min((paper.year for paper in neighbours if paper.year), default=current_year)
    neighbour_density = min(1.0, len(neighbours) / 5)
    recency_penalty = max(0.0, 1 - ((current_year - nearest_year) / 10)) if nearest_year else 0.5
    novelty_penalty = round((neighbour_density * 65) + (recency_penalty * 20))
    novelty_score = max(0, 100 - novelty_penalty)
    evidence_ids = [_paper_evidence_id(paper) for paper in neighbours]
    confidence_span = max(8, 18 - len(neighbours))

    return {
        "metric_scores": [
            _metric(
                "novelty",
                novelty_score,
                (
                    f"Novelty is based on {len(neighbours)} close neighbours and a nearest relevant paper year of "
                    f"{nearest_year}; more dense and more recent analogues reduce novelty."
                ),
                evidence_ids,
                "Closest papers make the base idea feel only partly new.",
                confidence_low=max(0, novelty_score - confidence_span),
                confidence_high=min(100, novelty_score + confidence_span),
                method="deterministic:nearest_neighbour_density",
            )
        ]
    }


async def _saturation_scorer_stub(state: PipelineState) -> PartialState:
    papers = sorted(
        state.get("papers", []),
        key=lambda paper: (paper.relevance_score, paper.citation_count),
        reverse=True,
    )
    if not papers:
        return {
            "overlaps": OverlapReport(
                crowding_score=0,
                overlapping_papers=[],
                whitespace_summary="No paper neighbourhood was available, so saturation could not be estimated.",
                risk_notes=["Retrieval returned no papers."],
            ),
            "metric_scores": [
                _metric(
                    "saturation",
                    50,
                    "Saturation defaults to neutral when no literature neighbourhood is available.",
                    [],
                    "Retrieve papers before trusting this metric.",
                    method="fallback:no_papers",
                )
            ],
        }

    current_year = datetime.now().year
    relevant_papers = [paper for paper in papers if paper.relevance_score >= 0.5]
    recent_papers = [paper for paper in relevant_papers if paper.year and paper.year >= current_year - 3]
    top_overlaps = relevant_papers[:5]

    coverage_ratio = min(1.0, len(relevant_papers) / 25)
    recent_ratio = len(recent_papers) / max(1, len(relevant_papers))
    crowding_score = round(min(100, (coverage_ratio * 70) + (recent_ratio * 30)))
    saturation_score = max(0, 100 - crowding_score)
    confidence_span = max(8, min(20, 24 - len(relevant_papers) // 3))
    evidence_ids = [_paper_evidence_id(paper) for paper in top_overlaps]

    overlaps = OverlapReport(
        crowding_score=crowding_score,
        overlapping_papers=[paper.title for paper in top_overlaps],
        whitespace_summary=(
            "Whitespace is most likely to come from narrowing the claim to a sharper context or subgroup "
            "than the current high-overlap paper neighbourhood."
        ),
        risk_notes=[
            f"{len(relevant_papers)} strongly relevant papers were found in the shared neighbourhood.",
            f"{len(recent_papers)} of those papers are recent, which increases crowding risk.",
        ],
    )
    return {
        "overlaps": overlaps,
        "metric_scores": [
            _metric(
                "saturation",
                saturation_score,
                (
                    f"Saturation is based on {len(relevant_papers)} relevant papers and a recent-publication "
                    f"share of {recent_ratio:.0%}; higher crowding lowers the Idea Hater saturation score."
                ),
                evidence_ids,
                "The hypothesis likely needs sharper positioning to avoid crowded territory.",
                confidence_low=max(0, saturation_score - confidence_span),
                confidence_high=min(100, saturation_score + confidence_span),
                method="deterministic:relevance_count_plus_recent_share",
            )
        ],
    }


async def _conflict_scorer_stub(state: PipelineState) -> PartialState:
    papers = sorted(
        state.get("papers", []),
        key=lambda paper: (paper.relevance_score, paper.citation_count),
        reverse=True,
    )
    keywords = ("contradict", "inconsistent", "mixed", "fails", "not support")
    conflicts = []
    for paper in papers[:10]:
        abstract = paper.abstract.lower()
        if any(keyword in abstract for keyword in keywords):
            conflicts.append(
                Conflict(
                    paper_id=paper.paper_id,
                    title=paper.title,
                    disagreement_dimension="effect_direction",
                    explanation="Abstract contains conflict-language heuristic triggers.",
                    severity=min(1.0, 0.35 + (paper.relevance_score * 0.5)),
                )
            )

    if not conflicts and papers:
        for paper in papers[:2]:
            if paper.relevance_score >= 0.85:
                conflicts.append(
                    Conflict(
                        paper_id=paper.paper_id,
                        title=paper.title,
                        disagreement_dimension="context",
                        explanation="Highly similar prior work creates execution risk even without explicit contradiction.",
                        severity=0.25,
                    )
                )

    weighted_conflict = sum(conflict.severity for conflict in conflicts)
    conflict_penalty = min(55, round(weighted_conflict * 25))
    conflict_score = max(0, 100 - conflict_penalty)
    evidence_ids = [conflict.paper_id for conflict in conflicts[:5]]
    confidence_span = 12 if conflicts else 18

    return {
        "conflicts": conflicts,
        "metric_scores": [
            _metric(
                "conflict_risk",
                conflict_score,
                (
                    f"Conflict risk is based on {len(conflicts)} heuristic conflict signals from the most relevant papers; "
                    "higher weighted conflict lowers the score."
                ),
                evidence_ids,
                "The current claim should address the strongest nearby disagreement signals.",
                confidence_low=max(0, conflict_score - confidence_span),
                confidence_high=min(100, conflict_score + confidence_span),
                method="heuristic:abstract_conflict_scan",
            )
        ],
    }


async def _feasibility_scorer_stub(state: PipelineState) -> PartialState:
    return {
        "metric_scores": [
            _metric(
                "feasibility",
                74,
                "Mock feasibility is strong: the method is common in nearby papers and dependencies look modest.",
                ["Methods appear in mock-paper-11", "Benchmark data appears in mock-paper-26"],
                "The main feasibility risk is validation across a second context.",
            )
        ]
    }


async def _impact_forecaster_stub(state: PipelineState) -> PartialState:
    forecast = ImpactForecast(
        volume=_impact_dimension(72, "Fake volume score: many adjacent papers can cite it."),
        velocity=_impact_dimension(68, "Fake velocity score: obvious demo buzz, modest validation lag."),
        reach=_impact_dimension(61, "Fake reach score: crosses one neighboring field."),
        depth=_impact_dimension(57, "Fake depth score: useful but not yet foundational."),
        disruption=_impact_dimension(49, "Fake disruption score: more steering than displacement."),
        translation=_impact_dimension(44, "Fake translation score: needs a bridge dataset."),
        overall_summary="Mock impact forecast: promising, crowded, and best steered toward a sharper niche.",
    )
    return {
        "forecast": forecast,
        "metric_scores": [
            _metric("volume", forecast.volume.score, forecast.volume.rationale, ["Citation analogue: mock-paper-02"]),
            _metric("velocity", forecast.velocity.score, forecast.velocity.rationale, ["Recent analogue: mock-paper-06"]),
            _metric("reach", forecast.reach.score, forecast.reach.rationale, ["Adjacent concept: mock cluster 4"]),
            _metric("depth", forecast.depth.score, forecast.depth.rationale, ["Review-adjacent paper: mock-paper-14"]),
            _metric("disruption", forecast.disruption.score, forecast.disruption.rationale, ["Conflict cluster: mock cluster 3"]),
            _metric("translation", forecast.translation.score, forecast.translation.rationale, ["Bridge dataset missing"]),
        ],
    }


async def _evidence_quality_scorer_stub(state: PipelineState) -> PartialState:
    papers = state.get("papers", [])
    if not papers:
        return {
            "metric_scores": [
                _metric(
                    "evidence_quality",
                    40,
                    "Evidence quality is low because no retrieved papers were available.",
                    [],
                    "Retrieve papers before trusting the scorecard.",
                    method="fallback:no_papers",
                )
            ]
        }

    abstract_ratio = sum(1 for paper in papers if paper.abstract.strip()) / len(papers)
    identifier_ratio = sum(1 for paper in papers if _paper_evidence_id(paper) != paper.paper_id) / len(papers)
    multi_source_ratio = sum(1 for paper in papers if len(paper.source_provenance) > 1) / len(papers)
    strong_relevance_ratio = sum(1 for paper in papers if paper.relevance_score >= 0.7) / len(papers)

    evidence_quality_score = round(
        (abstract_ratio * 35)
        + (identifier_ratio * 25)
        + (multi_source_ratio * 20)
        + (strong_relevance_ratio * 20)
    )
    top_supported = sorted(
        papers,
        key=lambda paper: (len(paper.source_provenance), paper.relevance_score, bool(paper.abstract.strip())),
        reverse=True,
    )[:5]
    evidence_ids = [_paper_evidence_id(paper) for paper in top_supported]
    confidence_span = max(8, 18 - len(top_supported))

    return {
        "metric_scores": [
            _metric(
                "evidence_quality",
                evidence_quality_score,
                (
                    f"Evidence quality is based on abstract coverage ({abstract_ratio:.0%}), stable identifiers "
                    f"({identifier_ratio:.0%}), cross-source provenance ({multi_source_ratio:.0%}), and strong relevance "
                    f"coverage ({strong_relevance_ratio:.0%})."
                ),
                evidence_ids,
                "Confidence is limited when identifiers, abstracts, or cross-source agreement are missing.",
                confidence_low=max(0, evidence_quality_score - confidence_span),
                confidence_high=min(100, evidence_quality_score + confidence_span),
                method="deterministic:coverage_completeness",
            )
        ]
    }


async def _score_aggregator_stub(state: PipelineState) -> PartialState:
    metrics = state.get("metric_scores", [])
    metric_map = {metric.metric_name: metric for metric in metrics}
    weights = {
        "novelty": 0.14,
        "saturation": 0.12,
        "conflict_risk": 0.12,
        "feasibility": 0.12,
        "volume": 0.07,
        "velocity": 0.07,
        "reach": 0.07,
        "depth": 0.07,
        "disruption": 0.07,
        "translation": 0.07,
        "evidence_quality": 0.08,
    }
    composite = _weighted_score(metric_map, weights)
    weaknesses = [metric.weakness for metric in metrics if metric.weakness]
    strengths = [
        f"{metric.metric_name}: {metric.score}"
        for metric in sorted(metrics, key=lambda item: item.score, reverse=True)[:3]
    ]
    scorecard = Scorecard(
        composite_score=composite,
        verdict=_verdict(composite),
        metric_scores=metrics,
        strengths=strengths,
        weaknesses=weaknesses[:5],
        evidence_summary=(
            f"Mock scorecard aggregated {len(metrics)} metrics from "
            f"{len(state.get('papers', []))} retrieved papers."
        ),
    )
    return {"scorecard": scorecard}


async def _mutator_stub(state: PipelineState) -> PartialState:
    raw = state["raw_hypothesis"]
    mutation_specs = [
        ("Narrow", 6, "Focus the claim on the less crowded subgroup flagged by saturation scoring."),
        ("Substitute mechanism", 3, "Avoid the highest-severity mechanism conflict with an alternate pathway."),
        ("Cross-pollinate", 10, "Borrow a method from the strongest adjacent evidence cluster."),
        ("Invert", 4, "Turn the conflict into a boundary-condition test."),
        ("Combine", 8, "Pair the claim with the missing bridge dataset needed for translation."),
    ]
    variants = [
        Variant(
            variant_id=f"mock-variant-{idx}",
            hypothesis_text=f"{raw} [{operator.lower()} quantitative repair]",
            operator=operator,
            rationale=f"{rationale} Obvious-fake expected gain: +{expected_gain}.",
            composite_score=min(100, state["scorecard"].composite_score + expected_gain),
            impact_scores={
                "novelty": 58 + idx,
                "saturation": 33 + expected_gain,
                "conflict_risk": 46 + (idx % 3) * 4,
                "feasibility": 74 - idx,
                "evidence_quality": 69 + idx,
            },
        )
        for idx, (operator, expected_gain, rationale) in enumerate(mutation_specs, start=1)
    ]
    return {"variants": variants}


async def _variant_rescorer_stub(state: PipelineState) -> PartialState:
    variant = state["current_variant"]
    score_adjustment = {
        "Narrow": 7,
        "Substitute mechanism": 5,
        "Cross-pollinate": 11,
        "Invert": 4,
        "Combine": 9,
    }.get(variant.operator, 0)
    original_score = state["scorecard"].composite_score
    composite = min(100, original_score + score_adjustment)
    scores = {
        **variant.impact_scores,
        "composite": composite,
        "volume": 65 + score_adjustment,
        "velocity": 60 + score_adjustment // 2,
        "reach": 58 + score_adjustment,
        "depth": 55 + score_adjustment,
        "disruption": 48 + score_adjustment,
        "translation": 45 + score_adjustment,
    }
    scorecard = Scorecard(
        composite_score=composite,
        verdict=_verdict(composite),
        metric_scores=[
            _metric("novelty", scores.get("novelty", 50), f"Mock re-score for {variant.variant_id}: novelty adjusted."),
            _metric("saturation", scores.get("saturation", 50), f"Mock re-score for {variant.variant_id}: saturation adjusted."),
            _metric(
                "evidence_quality",
                scores.get("evidence_quality", 50),
                f"Mock re-score for {variant.variant_id}: evidence confidence adjusted.",
            ),
        ],
        strengths=[f"Improves composite score by {score_adjustment} points."],
        weaknesses=["Still requires real literature scoring before demo claims become credible."],
        evidence_summary=f"Mock variant re-score reused {len(state.get('papers', []))} retrieved papers.",
    )
    return {
        "rescored_variants": [
            _copy_model(
                variant,
                composite_score=composite,
                impact_scores=scores,
                scorecard=scorecard,
            )
        ]
    }


async def _ranker_stub(state: PipelineState) -> PartialState:
    variants = state.get("rescored_variants") or state.get("variants", [])
    return _rank_variants(variants)


def _rank_variants(variants: list[Variant]) -> PartialState:
    selected_ids = _pareto_variant_ids(variants)
    ranked = sorted(
        variants,
        key=lambda variant: (
            variant.composite_score,
            variant.impact_scores.get("evidence_quality", 0),
            variant.impact_scores.get("feasibility", 0),
        ),
        reverse=True,
    )
    updated = []
    for rank, variant in enumerate(ranked, start=1):
        is_selected = variant.variant_id in selected_ids
        explanation = (
            f"Rank {rank}; Pareto-selected because no mock variant dominates its score trade-off."
            if is_selected
            else f"Rank {rank}; dominated by a higher-scoring mock variant on the quantitative scorecard."
        )
        updated.append(
            _copy_model(
                variant,
                rank=rank,
                is_pareto_selected=is_selected,
                dominance_explanation=explanation,
            )
        )
    return {"ranked_variants": updated, "variants": updated}


async def _strategist_stub(state: PipelineState) -> PartialState:
    ranked = state.get("ranked_variants", [])
    best = ranked[0] if ranked else None
    selected = [
        (
            f"#{variant.rank}: original hypothesis - score {variant.composite_score}"
            if variant.variant_id == "original"
            else f"#{variant.rank}: {variant.variant_id} ({variant.operator}) - score {variant.composite_score}"
        )
        for variant in ranked
        if variant.is_pareto_selected
    ]
    if best and best.variant_id == "original":
        recommendation = "Keep the original hypothesis; it remains the strongest ranked candidate after mutation."
    elif best:
        recommendation = f"Develop {best.variant_id} via {best.operator}; it has the strongest composite score."
    else:
        recommendation = "Do not proceed until variants can be generated and scored."
    scorecard = state["scorecard"]
    memo = StrategyMemo(
        recommendation=recommendation,
        recommended_hypothesis_text=best.hypothesis_text if best else "",
        recommended_variant_id=None if not best or best.variant_id == "original" else best.variant_id,
        original_verdict=scorecard.verdict,
        recommended_verdict=best.scorecard.verdict if best and best.scorecard else None,
        executive_summary=(
            f"The quantitative Idea Hater pipeline completed end-to-end. "
            f"The original idea scored {scorecard.composite_score}/100 ({scorecard.verdict}), "
            f"then the original and generated variants were re-scored and ranked together."
        ),
        scorecard_summary=[
            f"{metric.metric_name}: {metric.score} ({metric.confidence_low}-{metric.confidence_high})"
            for metric in scorecard.metric_scores
        ],
        key_findings=[
            f"Parsed claim: {state['parsed'].claim}",
            f"Retrieved {len(state.get('papers', []))} mock literature neighbours.",
            f"Aggregated {len(scorecard.metric_scores)} quantitative metric scores.",
            f"Generated and re-scored {len(state.get('rescored_variants', []))} variants.",
            f"Ranked {len(ranked)} candidates including the original hypothesis.",
        ],
        selected_variants=selected,
        trade_offs=[
            variant.dominance_explanation
            for variant in ranked[:5]
            if variant.dominance_explanation
        ],
        evidence_trail=sorted(
            {
                evidence_id
                for metric in scorecard.metric_scores
                for evidence_id in (metric.evidence_ids or metric.evidence)
            }
        )[:12],
        risks=scorecard.weaknesses[:3],
        next_steps=[
            "Replace mock metric scorers with real retrieval-backed implementations.",
            "Warm the SQLite cache before any demo run.",
            "Keep group emulation out of the core backend validation path.",
        ],
    )
    return {"final_memo": memo}


def _metric(
    metric_name: str,
    score: int,
    rationale: str,
    evidence: list[str] | None = None,
    weakness: str = "",
    confidence_low: int | None = None,
    confidence_high: int | None = None,
    method: str = "",
) -> MetricScore:
    low = max(0, score - 10) if confidence_low is None else confidence_low
    high = min(100, score + 10) if confidence_high is None else confidence_high
    return MetricScore(
        metric_name=metric_name,
        score=score,
        confidence_low=low,
        confidence_high=high,
        rationale=rationale,
        evidence=evidence or [],
        evidence_ids=evidence or [],
        method=method,
        weakness=weakness,
    )


def _paper_evidence_id(paper: Paper) -> str:
    if paper.doi:
        return f"doi:{paper.doi.lower()}"
    if paper.openalex_id:
        return f"openalex:{paper.openalex_id.rsplit('/', 1)[-1]}"
    if paper.semantic_scholar_id:
        return f"s2:{paper.semantic_scholar_id}"
    return paper.paper_id


def _impact_dimension(score: int, rationale: str) -> ImpactDimension:
    return ImpactDimension(
        score=score,
        confidence_low=max(0, score - 12),
        confidence_high=min(100, score + 12),
        rationale=rationale,
    )


def _impact_metric_scores(forecast: ImpactForecast, state: PipelineState | None = None) -> list[MetricScore]:
    evidence_ids = [
        _paper_evidence_id(paper)
        for paper in (state or {}).get("papers", [])[:6]
        if isinstance(paper, Paper)
    ]
    return [
        _metric("volume", forecast.volume.score, forecast.volume.rationale, evidence_ids, method="forecast:volume_v1"),
        _metric("velocity", forecast.velocity.score, forecast.velocity.rationale, evidence_ids, method="forecast:velocity_v1"),
        _metric("reach", forecast.reach.score, forecast.reach.rationale, evidence_ids, method="forecast:reach_v1"),
        _metric("depth", forecast.depth.score, forecast.depth.rationale, evidence_ids, method="forecast:depth_v1"),
        _metric("disruption", forecast.disruption.score, forecast.disruption.rationale, evidence_ids, method="forecast:disruption_v1"),
        _metric("translation", forecast.translation.score, forecast.translation.rationale, evidence_ids, method="forecast:translation_v1"),
    ]


def _weighted_score(metric_map: dict[str, MetricScore], weights: dict[str, float]) -> int:
    present_weights = {
        metric_name: weight
        for metric_name, weight in weights.items()
        if metric_name in metric_map
    }
    total_weight = sum(present_weights.values())
    if total_weight == 0:
        return 0
    weighted = sum(metric_map[metric_name].score * weight for metric_name, weight in present_weights.items())
    return round(weighted / total_weight)


def _verdict(score: int) -> str:
    if score >= 80:
        return "strong candidate"
    if score >= 65:
        return "promising but needs steering"
    if score >= 50:
        return "risky; mutate before development"
    return "weak idea; substantial repair required"


def _pareto_variant_ids(variants: list[Variant]) -> set[str]:
    selected: set[str] = set()
    for candidate in variants:
        dominated = False
        for challenger in variants:
            if challenger.variant_id == candidate.variant_id:
                continue
            if _dominates(challenger, candidate):
                dominated = True
                break
        if not dominated:
            selected.add(candidate.variant_id)
    return selected


def _dominates(left: Variant, right: Variant) -> bool:
    dimensions = set(left.impact_scores) & set(right.impact_scores)
    if not dimensions:
        return False
    left_score = left.composite_score
    right_score = right.composite_score
    if "composite" in left.impact_scores and "composite" in right.impact_scores:
        left_score = left.impact_scores["composite"]
        right_score = right.impact_scores["composite"]

    return (
        left_score >= right_score
        and all(left.impact_scores[dim] >= right.impact_scores[dim] for dim in dimensions)
        and (
            left_score > right_score
            or any(left.impact_scores[dim] > right.impact_scores[dim] for dim in dimensions)
        )
    )


def _copy_model(model: Any, **updates: Any) -> Any:
    if hasattr(model, "model_copy"):
        return model.model_copy(update=updates)
    return model.copy(update=updates)
