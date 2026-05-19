from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Mapping, Sequence, TypeVar

from pydantic import BaseModel

from backend.tracing import observe


StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


@dataclass(frozen=True)
class ModelRoute:
    model: str
    structured_output: bool = True
    reasoning_effort: str | None = None
    notes: str = ""


# Core quantitative Idea Hater route table. Group emulation is intentionally not
# on this path: parser -> cartographer -> metric scorers -> score aggregation ->
# mutation -> variant re-scoring -> ranking/Pareto -> strategy memo.
CORE_MODEL_ROUTES: dict[str, ModelRoute] = {
    "parser": ModelRoute("gpt-5-nano", notes="Parse raw hypothesis into ParsedHypothesis."),
    "cartographer": ModelRoute("gpt-5-nano", notes="Retrieve and summarize literature evidence."),
    "novelty_scorer": ModelRoute("gpt-5-nano", notes="Return MetricScore for novelty."),
    "saturation_scorer": ModelRoute("gpt-5-nano", notes="Return MetricScore for saturation/overlap."),
    "conflict_scorer": ModelRoute("gpt-5-nano", notes="Return MetricScore for conflict risk."),
    "feasibility_scorer": ModelRoute("gpt-5-mini", notes="Return MetricScore for feasibility."),
    "impact_forecaster": ModelRoute("gpt-5-mini", notes="Forecast volume, velocity, reach, depth, disruption, translation."),
    "evidence_quality_scorer": ModelRoute("gpt-5-nano", notes="Return MetricScore for evidence quality."),
    "score_aggregator": ModelRoute("code", structured_output=False, notes="Deterministically combine metrics into scorecard."),
    "mutator": ModelRoute("gpt-5", notes="Generate variants targeted at weak metrics."),
    "variant_rescorer": ModelRoute("gpt-5-mini", notes="Re-score each variant using MetricScore outputs."),
    "ranker": ModelRoute("code", structured_output=False, notes="Deterministically rank variants."),
    "pareto_curator": ModelRoute("gpt-5-nano", notes="Compute non-dominated variants and synthesize short explanations."),
    "strategist": ModelRoute(
        "gpt-5",
        reasoning_effort="high",
        notes="Recommend original or variant using scorecard, trade-offs, and evidence trail.",
    ),
}


# Optional frontend/generator proof-of-concept routes. These are not part of the
# quantitative core backend path or validation claim.
EXPERIMENTAL_MODEL_ROUTES: dict[str, ModelRoute] = {
    "group_identifier": ModelRoute("gpt-5-nano", notes="Experimental generator-side group discovery."),
    "group_emulator": ModelRoute("gpt-5-mini", notes="Experimental frontend-only group response emulator."),
    "trajectory_synth": ModelRoute("gpt-5", notes="Experimental group trajectory synthesis."),
    "groundedness_check": ModelRoute("gpt-5-nano", notes="Experimental group-emulation groundedness audit."),
    "conflict_detector": ModelRoute("gpt-5-nano", notes="Legacy alias; use conflict_scorer in the core path."),
    "overlap_auditor": ModelRoute("gpt-5-nano", notes="Legacy alias; use saturation_scorer in the core path."),
}


# Backwards-compatible string mappings for existing code that imports
# MODEL_ROUTING directly.
MODEL_ROUTING: dict[str, str] = {agent: route.model for agent, route in CORE_MODEL_ROUTES.items()}
EXPERIMENTAL_MODEL_ROUTING: dict[str, str] = {
    agent: route.model for agent, route in EXPERIMENTAL_MODEL_ROUTES.items()
}


def get_route(agent_name: str, *, include_experimental: bool = False) -> ModelRoute:
    if agent_name in CORE_MODEL_ROUTES:
        return CORE_MODEL_ROUTES[agent_name]
    if include_experimental and agent_name in EXPERIMENTAL_MODEL_ROUTES:
        return EXPERIMENTAL_MODEL_ROUTES[agent_name]
    raise KeyError(f"No model route configured for agent '{agent_name}'.")


def get_model(agent_name: str, *, include_experimental: bool = False) -> str:
    return get_route(agent_name, include_experimental=include_experimental).model


def is_code_agent(agent_name: str, *, include_experimental: bool = False) -> bool:
    return get_model(agent_name, include_experimental=include_experimental) == "code"


def reasoning_effort_for(agent_name: str, *, include_experimental: bool = False) -> str | None:
    """Return high reasoning only for the strategist route."""

    return get_route(agent_name, include_experimental=include_experimental).reasoning_effort


@observe(name="call_llm")
async def call_llm(
    agent_name: str,
    messages: Sequence[Mapping[str, str]],
    *,
    output_schema: type[StructuredModel] | None = None,
    client: Any | None = None,
    include_experimental: bool = False,
    **kwargs: Any,
) -> StructuredModel | str | Any:
    """Shared LLM wrapper for routed, traceable, optionally structured calls.

    Pass an OpenAI-compatible async client or a callable test double through
    `client`. Code-only agents such as `score_aggregator`, `ranker`, and
    `pareto_curator` should not call this wrapper.
    """

    route = get_route(agent_name, include_experimental=include_experimental)
    if route.model == "code":
        raise ValueError(f"Agent '{agent_name}' is routed to deterministic code, not an LLM.")
    if client is None:
        raise RuntimeError("call_llm requires an OpenAI-compatible client or callable client.")

    payload: dict[str, Any] = {
        "model": route.model,
        "messages": list(messages),
        **kwargs,
    }
    if route.reasoning_effort:
        payload["reasoning_effort"] = route.reasoning_effort

    response = await _dispatch_client(client, payload, output_schema)
    if output_schema is None:
        return _extract_text(response)
    return _coerce_structured_output(response, output_schema)


async def _dispatch_client(
    client: Any,
    payload: dict[str, Any],
    output_schema: type[StructuredModel] | None,
) -> Any:
    completions = getattr(getattr(getattr(client, "beta", None), "chat", None), "completions", None)
    if output_schema is not None and completions is not None and hasattr(completions, "parse"):
        return await _maybe_await(completions.parse(response_format=output_schema, **payload))

    completions = getattr(getattr(client, "chat", None), "completions", None)
    if completions is not None and hasattr(completions, "create"):
        return await _maybe_await(completions.create(**payload))

    if callable(client):
        return await _maybe_await(client(**payload))

    raise TypeError("Unsupported LLM client. Provide an OpenAI-compatible client or callable.")


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _coerce_structured_output(response: Any, output_schema: type[StructuredModel]) -> StructuredModel:
    if isinstance(response, output_schema):
        return response


    parsed = _extract_parsed(response)
    if isinstance(parsed, output_schema):
        return parsed
    if isinstance(parsed, Mapping):
        return output_schema.model_validate(parsed)
    if isinstance(parsed, str):
        return output_schema.model_validate_json(parsed)

    text = _extract_text(response)
    if isinstance(text, str):
        return output_schema.model_validate_json(text)
    raise TypeError(f"Could not coerce response into {output_schema.__name__}.")


def _extract_parsed(response: Any) -> Any:
    try:
        return response.choices[0].message.parsed
    except (AttributeError, IndexError, KeyError, TypeError):
        return None


def _extract_text(response: Any) -> Any:
    try:
        return response.choices[0].message.content
    except (AttributeError, IndexError, KeyError, TypeError):
        return response
