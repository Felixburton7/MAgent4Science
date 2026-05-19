from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, computed_field


class ParsedHypothesis(BaseModel):
    claim: str
    mechanism: str
    context: str
    population: str
    method: str


class Paper(BaseModel):
    paper_id: str
    title: str
    authors: List[str] = Field(default_factory=list)
    year: Optional[int] = None
    abstract: str = ""
    url: str = ""
    citation_count: int = 0
    relevance_score: float = 0.0
    cluster: str = "unclustered"
    doi: str = ""
    openalex_id: str = ""
    semantic_scholar_id: str = ""
    source_provenance: List[str] = Field(default_factory=list)


class SourceError(BaseModel):
    source: str
    query: str = ""
    error: str


class RetrievalReport(BaseModel):
    status: Literal["ok", "partial", "no_results", "failed"]
    attempted_queries: List[str] = Field(default_factory=list)
    source_errors: List[SourceError] = Field(default_factory=list)
    cutoff_year: Optional[int] = None
    paper_count: int = Field(default=0, ge=0)
    openalex_total_count: int = Field(default=0, ge=0)


class Conflict(BaseModel):
    paper_id: str
    title: str
    disagreement_dimension: str
    explanation: str
    severity: float = Field(ge=0.0, le=1.0)


class OverlapReport(BaseModel):
    crowding_score: int = Field(ge=0, le=100)
    overlapping_papers: List[str] = Field(default_factory=list)
    whitespace_summary: str
    risk_notes: List[str] = Field(default_factory=list)


class ResearchGroup(BaseModel):
    group_id: str
    name: str
    institution: str
    principal_investigators: List[str] = Field(default_factory=list)
    recent_paper_ids: List[str] = Field(default_factory=list)
    methods: List[str] = Field(default_factory=list)
    grounding_evidence: str


class EmulatorOutput(BaseModel):
    group_id: str
    group_name: str
    interest_score: int = Field(ge=0, le=100)
    engagement_type: str
    proposed_direction: str
    method_they_use: str
    time_to_publish_months: int = Field(ge=0)
    competitive_risk: int = Field(ge=0, le=100)
    grounding_paper_ids: List[str] = Field(default_factory=list)


class Scenario(BaseModel):
    scenario_id: str
    name: str
    probability: float = Field(ge=0.0, le=1.0)
    description: str
    leading_groups: List[str] = Field(default_factory=list)
    implications: List[str] = Field(default_factory=list)


class ImpactDimension(BaseModel):
    score: int = Field(ge=0, le=100)
    confidence_low: int = Field(ge=0, le=100)
    confidence_high: int = Field(ge=0, le=100)
    rationale: str
    predicted_value: Optional[float] = None
    predicted_low: Optional[float] = None
    predicted_high: Optional[float] = None
    units: str = ""


class ImpactForecast(BaseModel):
    volume: ImpactDimension
    velocity: ImpactDimension
    reach: ImpactDimension
    depth: ImpactDimension
    disruption: ImpactDimension
    translation: ImpactDimension
    overall_summary: str


class MetricScore(BaseModel):
    """Quantitative score for one Idea Hater metric.

    `name` and `evidence_ids` are the canonical fields. Legacy aliases
    `metric_name` and `evidence` are accepted to keep the current pipeline and
    dashboard stubs working while the backend moves away from group emulation.
    """

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(validation_alias=AliasChoices("name", "metric_name"))
    score: int = Field(ge=0, le=100)
    confidence_low: int = Field(ge=0, le=100)
    confidence_high: int = Field(ge=0, le=100)
    rationale: str
    evidence_ids: List[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("evidence_ids", "evidence"),
    )
    method: str = ""
    weakness: str = ""

    @computed_field
    @property
    def metric_name(self) -> str:
        return self.name

    @computed_field
    @property
    def evidence(self) -> List[str]:
        return self.evidence_ids


class IdeaEvaluation(BaseModel):
    """Full quantitative scorecard for an original hypothesis or variant."""

    hypothesis_text: str
    parsed: ParsedHypothesis
    metrics: List[MetricScore] = Field(default_factory=list)
    composite_score: int = Field(ge=0, le=100)
    verdict: Literal["reject", "revise", "promising", "strong"]
    key_weaknesses: List[str] = Field(default_factory=list)
    key_strengths: List[str] = Field(default_factory=list)
    metric_weights: Dict[str, float] = Field(default_factory=dict)
    evidence_summary: str = ""


class Scorecard(BaseModel):
    """Display-oriented aggregate scorecard used by the current pipeline."""

    composite_score: int = Field(ge=0, le=100)
    verdict: str
    metric_scores: List[MetricScore] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    evidence_summary: str
    metric_weights: Dict[str, float] = Field(default_factory=dict)
    weighted_contributions: Dict[str, float] = Field(default_factory=dict)


class Variant(BaseModel):
    variant_id: str
    hypothesis_text: str
    operator: str
    rationale: str
    impact_scores: Dict[str, int] = Field(default_factory=dict)

    impact_forecast: Optional[ImpactForecast] = None

    composite_score: int = Field(default=0, ge=0, le=100)
    scorecard: Optional[Scorecard] = None
    rank: Optional[int] = None

    is_pareto_selected: bool = False
    dominance_explanation: str = ""


class VariantEvaluation(BaseModel):
    """Evaluation and Pareto status for a generated hypothesis variant."""

    variant: Variant
    evaluation: IdeaEvaluation
    improvement_over_original: int
    is_pareto_selected: bool = False
    dominance_explanation: str = ""


class GroundednessCheck(BaseModel):
    group_id: str
    group_name: str
    is_grounded: bool
    flagged_inconsistencies: List[str] = Field(default_factory=list)
    evidence: str


class StrategyMemo(BaseModel):
    """Final Denario-facing recommendation built from scores and evidence."""

    recommendation: str
    executive_summary: str
    recommended_hypothesis_text: str = ""
    recommended_variant_id: Optional[str] = None
    original_verdict: Optional[str] = None
    recommended_verdict: Optional[str] = None
    scorecard_summary: List[str] = Field(default_factory=list)
    key_findings: List[str] = Field(default_factory=list)
    selected_variants: List[str] = Field(default_factory=list)
    trade_offs: List[str] = Field(default_factory=list)
    evidence_trail: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    next_steps: List[str] = Field(default_factory=list)
    denario_next_actions: List[str] = Field(default_factory=list)

    def to_markdown(self) -> str:
        sections = [
            "# Strategy Memo",
            f"## Recommendation\n{self.recommendation}",
            f"## Recommended Hypothesis\n{self.recommended_hypothesis_text}" if self.recommended_hypothesis_text else "",
            f"## Executive Summary\n{self.executive_summary}",
            _bullets("Scorecard Summary", self.scorecard_summary),
            _bullets("Key Findings", self.key_findings),
            _bullets("Selected Variants", self.selected_variants),
            _bullets("Trade-offs", self.trade_offs),
            _bullets("Evidence Trail", self.evidence_trail),
            _bullets("Risks", self.risks),
            _bullets("Next Steps", self.next_steps),
            _bullets("Denario Next Actions", self.denario_next_actions),
        ]
        return "\n\n".join(section for section in sections if section)


def _bullets(title: str, values: List[str]) -> str:
    if not values:
        return ""
    body = "\n".join(f"- {value}" for value in values)
    return f"## {title}\n{body}"
