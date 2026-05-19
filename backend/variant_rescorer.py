from __future__ import annotations

from typing import Any

from backend.evidence_utils import paper_evidence_id
from backend.schemas import ImpactForecast, MetricScore, Scorecard, Variant


METRIC_WEIGHTS = {
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

OPERATOR_DELTAS = {
    "Generalise": {"volume": 8, "velocity": 3, "reach": 9, "depth": -4, "saturation": -6, "evidence_quality": -2},
    "Narrow": {"volume": -5, "reach": -2, "saturation": 12, "feasibility": 7, "depth": 7, "translation": 3},
    "Substitute": {"novelty": 10, "conflict_risk": 9, "depth": 5, "disruption": 9, "feasibility": -3},
    "Shift scale": {"volume": 5, "velocity": -3, "reach": 6, "saturation": 8, "depth": 4, "translation": 12},
    "Cross-pollinate": {"novelty": 13, "velocity": 3, "reach": 14, "depth": 4, "disruption": 10, "feasibility": -4},
    "Invert": {"volume": -2, "velocity": 4, "conflict_risk": 14, "feasibility": 5, "depth": 10, "disruption": 7},
    "Combine": {"volume": 7, "reach": 7, "depth": 7, "translation": 11, "evidence_quality": 5, "feasibility": -4},
}

TARGETS = {
    "Generalise": ("volume", "reach", "velocity"),
    "Narrow": ("saturation", "feasibility", "depth"),
    "Substitute": ("novelty", "conflict_risk", "disruption"),
    "Shift scale": ("saturation", "translation", "reach"),
    "Cross-pollinate": ("novelty", "reach", "disruption"),
    "Invert": ("conflict_risk", "depth", "feasibility"),
    "Combine": ("translation", "depth", "evidence_quality"),
}


async def variant_rescorer(state: dict[str, Any]) -> dict[str, list[Variant]]:
    variant = state["current_variant"]
    try:
        rescored = await _real_rescore_variant(variant, state)
        return {"rescored_variants": [rescored]}
    except Exception:
        return _heuristic_rescore_variant(state)


async def _heuristic_rescore_variant(state: dict[str, Any]) -> dict[str, list[Variant]]:
    variant = state["current_variant"]
    original_metrics = _metric_map(state.get("scorecard"), state.get("metric_scores", []))
    weak_metrics = {name for name, metric in original_metrics.items() if metric.score < 58}
    operator = _normalise_operator(variant.operator)
    proposed_scores = _normalise_scores(variant.impact_scores)
    deltas = OPERATOR_DELTAS.get(operator, {})
    targets = set(TARGETS.get(operator, ()))

    rescored_metrics: list[MetricScore] = []
    score_values: dict[str, int] = {}
    for metric_name, weight in METRIC_WEIGHTS.items():
        original = original_metrics.get(metric_name)
        if metric_name in proposed_scores:
            score = _clamp(proposed_scores[metric_name])
        else:
            base_score = original.score if original else 50
            targeted_bonus = 4 if metric_name in targets and metric_name in weak_metrics else 0
            score = _clamp(base_score + deltas.get(metric_name, 0) + targeted_bonus)
        score_values[metric_name] = score
        rescored_metrics.append(
            MetricScore(
                name=metric_name,
                score=score,
                confidence_low=max(0, score - _confidence_span(original)),
                confidence_high=min(100, score + _confidence_span(original)),
                rationale=_metric_rationale(metric_name, operator, score, original),
                evidence_ids=_evidence_ids(original),
                method=f"variant_rescore:{operator.lower().replace(' ', '_')}",
                weakness=_weakness(metric_name, score),
            )
        )

    composite = _weighted_score(score_values)
    original_composite = int(getattr(state.get("scorecard"), "composite_score", 0) or 0)
    score_values["composite"] = composite
    strengths = _strengths(score_values, original_metrics)
    weaknesses = [metric.weakness for metric in rescored_metrics if metric.weakness][:5]
    scorecard = Scorecard(
        composite_score=composite,
        verdict=_verdict(composite),
        metric_scores=rescored_metrics,
        strengths=strengths,
        weaknesses=weaknesses,
        evidence_summary=(
            f"Variant re-scored with {len(rescored_metrics)} metrics using the original evidence neighbourhood; "
            f"composite change is {composite - original_composite:+d}."
        ),
        metric_weights=METRIC_WEIGHTS,
        weighted_contributions={name: round(score_values[name] * weight, 3) for name, weight in METRIC_WEIGHTS.items()},
    )

    return {
        "rescored_variants": [
            _copy_model(
                variant,
                operator=operator,
                composite_score=composite,
                impact_scores=score_values,
                scorecard=scorecard,
            )
        ]
    }


run = variant_rescorer


async def _real_rescore_variant(variant: Variant, state: dict[str, Any]) -> Variant:
    from backend import (
        cartographer,
        conflict_scorer,
        evidence_quality_scorer,
        feasibility_scorer,
        impact_forecaster,
        novelty_scorer,
        parser,
        saturation_scorer,
        score_aggregator,
    )

    variant_state: dict[str, Any] = {
        "raw_hypothesis": variant.hypothesis_text,
        "metric_scores": [],
    }
    for key in ("information_cutoff_year", "backtest_metadata"):
        if state.get(key) is not None:
            variant_state[key] = state[key]

    for node in (parser.run, cartographer.run):
        _merge_result(variant_state, await node(variant_state))

    for scorer in (
        novelty_scorer.run,
        saturation_scorer.run,
        conflict_scorer.run,
        feasibility_scorer.run,
        evidence_quality_scorer.run,
    ):
        _merge_result(variant_state, await scorer(variant_state))

    impact_result = await impact_forecaster.run(variant_state)
    _merge_result(variant_state, impact_result)
    forecast = variant_state.get("forecast")
    if isinstance(forecast, ImpactForecast):
        variant_state["metric_scores"].extend(_forecast_metric_scores(forecast, variant_state))

    _merge_result(variant_state, await score_aggregator.run(variant_state))
    scorecard = variant_state["scorecard"]
    score_values = {
        metric.name: metric.score
        for metric in scorecard.metric_scores
    }
    score_values["composite"] = int(scorecard.composite_score)

    return _copy_model(
        variant,
        operator=_normalise_operator(variant.operator),
        composite_score=scorecard.composite_score,
        impact_scores=score_values,
        scorecard=scorecard,
    )


def _merge_result(target: dict[str, Any], update: dict[str, Any]) -> None:
    for key, value in update.items():
        if key == "metric_scores":
            target.setdefault("metric_scores", [])
            target["metric_scores"].extend(value or [])
        else:
            target[key] = value


def _forecast_metric_scores(forecast: ImpactForecast, state: dict[str, Any]) -> list[MetricScore]:
    evidence_ids = [paper_evidence_id(paper) for paper in state.get("papers", [])[:6]]
    metrics: list[MetricScore] = []
    for name in ("volume", "velocity", "reach", "depth", "disruption", "translation"):
        dimension = getattr(forecast, name)
        metrics.append(
            MetricScore(
                name=name,
                score=dimension.score,
                confidence_low=dimension.confidence_low,
                confidence_high=dimension.confidence_high,
                rationale=dimension.rationale,
                evidence_ids=evidence_ids,
                method=f"forecast:{name}_v1",
                weakness="" if dimension.score >= 55 else f"{name} remains weak after mutation.",
            )
        )
    return metrics


def _metric_map(scorecard: Any, fallback_metrics: list[Any]) -> dict[str, MetricScore]:
    metrics = getattr(scorecard, "metric_scores", None) or fallback_metrics or []
    return {_metric_name(metric): metric for metric in metrics if _metric_name(metric)}


def _normalise_scores(scores: dict[str, int]) -> dict[str, int]:
    return {key.lower().replace(" ", "_").replace("-", "_"): int(value) for key, value in (scores or {}).items()}


def _normalise_operator(operator: str) -> str:
    aliases = {
        "Substitute mechanism": "Substitute",
        "Shift Scale": "Shift scale",
        "Cross Pollinate": "Cross-pollinate",
    }
    return aliases.get(operator, operator)


def _metric_name(metric: Any) -> str:
    return str(getattr(metric, "metric_name", None) or getattr(metric, "name", "")).lower()


def _evidence_ids(metric: Any | None) -> list[str]:
    if metric is None:
        return []
    return list(getattr(metric, "evidence_ids", []) or getattr(metric, "evidence", []) or [])


def _confidence_span(metric: Any | None) -> int:
    if metric is None:
        return 14
    low = int(getattr(metric, "confidence_low", 0) or 0)
    high = int(getattr(metric, "confidence_high", 100) or 100)
    score = int(getattr(metric, "score", 50) or 50)
    return max(8, min(18, max(score - low, high - score)))


def _metric_rationale(metric_name: str, operator: str, score: int, original: MetricScore | None) -> str:
    original_score = original.score if original else 50
    movement = score - original_score
    if movement > 0:
        direction = f"improves by {movement} points"
    elif movement < 0:
        direction = f"trades off {-movement} points"
    else:
        direction = "stays unchanged"
    return f"{operator} variant {direction} on {metric_name} relative to the original scorecard."


def _weakness(metric_name: str, score: int) -> str:
    if score >= 55:
        return ""
    return f"{metric_name} remains weak after mutation."


def _strengths(scores: dict[str, int], original_metrics: dict[str, MetricScore]) -> list[str]:
    gains = []
    for name, score in scores.items():
        if name == "composite":
            continue
        original = original_metrics.get(name)
        if original is not None:
            gains.append((name, score - original.score, score))
    positive = [item for item in sorted(gains, key=lambda item: (item[1], item[2]), reverse=True) if item[1] > 0]
    if positive:
        return [f"{name}: {score} ({gain:+d})" for name, gain, score in positive[:3]]
    return [f"{name}: {score}" for name, _gain, score in sorted(gains, key=lambda item: item[2], reverse=True)[:3]]


def _weighted_score(scores: dict[str, int]) -> int:
    total_weight = sum(METRIC_WEIGHTS.values())
    weighted = sum(scores.get(name, 50) * weight for name, weight in METRIC_WEIGHTS.items())
    return round(weighted / total_weight)


def _verdict(score: int) -> str:
    if score >= 80:
        return "strong candidate"
    if score >= 65:
        return "promising but needs steering"
    if score >= 50:
        return "risky; mutate before development"
    return "weak idea; substantial repair required"


def _clamp(value: float) -> int:
    return int(max(0, min(100, round(value))))


def _copy_model(model: Any, **updates: Any) -> Any:
    if hasattr(model, "model_copy"):
        return model.model_copy(update=updates)
    return model.copy(update=updates)
