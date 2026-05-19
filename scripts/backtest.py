from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config import MAX_API_TIMEOUT, OPENALEX_EMAIL
from backend.impact_forecaster import impact_forecaster
from backend.llm_client import LLMUnavailable, complete_structured
from backend.pipeline import run_pipeline, run_scorecard_pipeline
from backend.schemas import ImpactForecast, Paper, ParsedHypothesis
from backend.tools.api_cache import cached_get_json
from backend.tools.semantic_scholar import get_paper_citations


OPENALEX_WORKS_URL = "https://api.openalex.org/works"
PREDICTION_CUTOFF_YEAR = 2018
RETRIEVAL_CUTOFF_YEAR = PREDICTION_CUTOFF_YEAR - 1
GROUND_TRUTH_YEAR = 2024
DIMENSIONS = ("volume", "velocity", "reach", "depth", "disruption", "translation")

TOPIC_QUERIES = [
    ("cs", "transformer attention deep learning"),
    ("cs", "BERT transformer language representation learning"),
    ("cs", "convolutional neural network image recognition"),
    ("cs", "graph neural network deep learning"),
    ("cs", "generative adversarial network deep learning"),
    ("cs", "diffusion model generative deep learning"),
    # AI-assisted biology (kept for continuity)
    ("bio", "deep learning protein prediction"),
    ("bio", "convolutional neural network medical imaging"),
    ("bio", "machine learning genomics neural network"),
    ("bio", "deep learning drug discovery"),
    # Pure biology — no ML framing
    ("bio", "CRISPR gene editing genome"),
    ("bio", "single cell RNA sequencing transcriptomics"),
    ("bio", "cancer immunotherapy T cell"),
    ("bio", "antibiotic resistance bacterial pathogen"),
    ("bio", "protein folding structure function"),
    # AI-assisted materials (kept for continuity)
    ("materials", "machine learning materials discovery"),
    ("materials", "deep learning molecule generation"),
    ("materials", "neural network crystal structure prediction"),
    ("materials", "artificial intelligence materials science"),
    # Pure materials — no ML framing
    ("materials", "metal organic framework gas adsorption"),
    ("materials", "lithium ion battery cathode electrolyte"),
    ("materials", "perovskite solar cell efficiency"),
    ("materials", "high entropy alloy mechanical properties"),
    ("materials", "catalyst hydrogen evolution reaction"),
]

AI_KEYWORDS = (
    "machine learning",
    "deep learning",
    "neural",
    "transformer",
    "attention",
    "bert",
    "convolutional",
    "cnn",
    "diffusion",
    "generative",
    "generative adversarial",
    "representation learning",
    "graph neural",
    "reinforcement learning",
)

TRANSLATION_KEYWORDS = (
    "clinical",
    "trial",
    "patient",
    "policy",
    "patent",
    "guideline",
    "diagnosis",
    "therapy",
    "drug",
    "material",
    "battery",
    "robot",
    "autonomous",
    "deployment",
)

TOP_VENUES = (
    "neurips",
    "nips",
    "icml",
    "iclr",
    "cvpr",
    "acl",
    "emnlp",
    "aaai",
    "ijcai",
    "nature",
    "science",
    "cell",
)


class HypothesisExtraction(ParsedHypothesis):
    hypothesis: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the 2018 -> 2024 historical impact backtest.")
    parser.add_argument("--limit", type=int, default=30, help="Number of 2018 AI papers to backtest.")
    parser.add_argument("--output-dir", default="backtest_outputs", help="Directory for dataset, CSV, and plot.")
    parser.add_argument("--max-citing-works", type=int, default=120, help="Max OpenAlex citing works per paper.")
    parser.add_argument("--refresh-dataset", action="store_true", help="Ignore cached dataset JSON and pull again.")
    parser.add_argument("--skip-plot", action="store_true", help="Compute metrics without writing the PNG plot.")
    parser.add_argument("--disable-llm", action="store_true", help="Force deterministic fallback scoring for reproducible validation.")
    parser.add_argument(
        "--with-variants",
        action="store_true",
        help="Also run mutation and variant re-scoring for every backtest record. Slower; not required for Spearman validation.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    if args.disable_llm:
        os.environ["MAGENT_DISABLE_LLM"] = "1"

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = output_dir / "backtest_dataset.json"

    if dataset_path.exists() and not args.refresh_dataset:
        records = json.loads(dataset_path.read_text())
        records = records[: args.limit]
    else:
        records = collect_dataset(args.limit, args.max_citing_works)
        dataset_path.write_text(json.dumps(records, indent=2, sort_keys=True))

    results = []
    for idx, record in enumerate(records, start=1):
        print(f"[{idx}/{len(records)}] forecasting: {record['metadata']['title'][:90]}")
        prediction_state = await run_prediction_state(record, include_variants=args.with_variants)
        prediction = prediction_state["forecast"]
        baseline_gpt = await run_single_call_baseline(record)
        row = build_result_row(record, prediction, baseline_gpt)
        row.update(build_variant_improvement_summary(prediction_state))
        results.append(row)

    add_linear_regression_baseline(results)
    add_mean_and_random_baselines(results)
    correlations = compute_correlations(results)

    csv_path = output_dir / "backtest_results.csv"
    write_results_csv(csv_path, results)
    corr_path = output_dir / "spearman_correlations.json"
    corr_path.write_text(json.dumps(correlations, indent=2, sort_keys=True))
    variant_path = output_dir / "variant_improvement_summary.json"
    variant_path.write_text(json.dumps(build_variant_improvement_export(results), indent=2, sort_keys=True))

    plot_path = output_dir / "predicted_vs_actual_scatter.png"
    if not args.skip_plot:
        write_scatter_plot(plot_path, results, correlations)

    print("\nSpearman correlations:")
    for dimension in DIMENSIONS:
        values = correlations[dimension]
        print(
            f"  {dimension:12s} forecaster={values['forecaster']:.3f} "
            f"citation_1y={values['citation_1y']:.3f} "
            f"single_call={values['single_call']:.3f} "
            f"linear={values['linear_regression']:.3f} "
            f"mean={values['mean_baseline']:.3f} "
            f"random={values['random_baseline']:.3f}"
        )
    print(f"\nDataset: {dataset_path}")
    print(f"Results: {csv_path}")
    print(f"Variant summary: {variant_path}")
    if not args.skip_plot:
        print(f"Scatter plot: {plot_path}")


def collect_dataset(limit: int, max_citing_works: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    seen_titles: set[str] = set()
    area_counts = {"cs": 0, "bio": 0, "materials": 0}
    quotas = area_quotas(limit)

    def try_add(work: dict[str, Any], area: str, query: str, enforce_quota: bool) -> bool:
        if len(records) >= limit:
            return False
        if enforce_quota and area_counts[area] >= quotas[area]:
            return False
        work_id = work.get("id")
        if not work_id or work_id in seen:
            return False
        metadata = metadata_from_work(work, area, query)
        if not metadata["abstract"] or not is_ai_paper(metadata):
            return False
        title_key = normalized_title(metadata["title"])
        if title_key in seen_titles:
            return False
        seen.add(work_id)
        seen_titles.add(title_key)
        area_counts[area] += 1
        ground_truth = collect_ground_truth(work, max_citing_works)
        records.append(
            {
                "metadata": metadata,
                "ground_truth": ground_truth,
                "prediction_cutoff_year": PREDICTION_CUTOFF_YEAR,
                "ground_truth_year": GROUND_TRUTH_YEAR,
                "date_filtering": (
                    "Prediction inputs include only the focal title and abstract as the "
                    "pre-publication hypothesis. Literature retrieval is restricted to "
                    f"evidence available through {RETRIEVAL_CUTOFF_YEAR}. Citation outcomes "
                    "are stored separately and are not passed to the pipeline."
                ),
            }
        )
        return True

    for target_area in ("cs", "bio", "materials"):
        for area, query in TOPIC_QUERIES:
            if area != target_area or area_counts[target_area] >= quotas[target_area]:
                continue
            for work in search_2018_works(query, per_page=16):
                try_add(work, area, query, enforce_quota=True)

    if len(records) < limit:
        for area, query in TOPIC_QUERIES:
            if len(records) >= limit:
                break
            for work in search_2018_works(query, per_page=16):
                if len(records) >= limit:
                    break
                try_add(work, area, query, enforce_quota=False)

    if len(records) < limit:
        print(f"Warning: collected {len(records)} records, below requested limit {limit}.")
    return records


def area_quotas(limit: int) -> dict[str, int]:
    base = limit // 3
    remainder = limit % 3
    areas = ["cs", "bio", "materials"]
    return {area: base + (1 if idx < remainder else 0) for idx, area in enumerate(areas)}


def search_2018_works(query: str, per_page: int) -> list[dict[str, Any]]:
    params = {
        "search": query,
        "filter": "from_publication_date:2018-01-01,to_publication_date:2018-12-31",
        "per-page": per_page,
    }
    data = openalex_get(OPENALEX_WORKS_URL, params)
    return data.get("results", [])


def collect_ground_truth(work: dict[str, Any], max_citing_works: int) -> dict[str, Any]:
    counts = counts_by_year(work)
    work_key = openalex_key(work["id"])
    citing_works = fetch_citing_works(work_key, max_citing_works)
    if not citing_works:
        citing_works = semantic_scholar_citing_fallback(work)

    concepts = set()
    review_citations = 0
    translation_citations = 0
    citing_citation_counts_2024: list[int] = []
    focal_refs = set(work.get("referenced_works") or [])
    independent = 0
    developmental = 0

    for citing in citing_works:
        for concept in extract_concepts(citing):
            concepts.add(concept.lower())
        title = (citing.get("title") or "").lower()
        source = source_name(citing).lower()
        all_text = " ".join([title, source, " ".join(extract_concepts(citing)).lower()])
        citing_type = (citing.get("type") or "").lower()
        if citing_type == "review" or "review" in title or "survey" in title:
            review_citations += 1
        if any(keyword in all_text for keyword in TRANSLATION_KEYWORDS):
            translation_citations += 1

        citing_citation_counts_2024.append(sum_counts_to_year(counts_by_year(citing), GROUND_TRUTH_YEAR))
        refs = set(citing.get("referenced_works") or [])
        if focal_refs and refs:
            overlap = refs.intersection(focal_refs)
            if overlap:
                developmental += 1
            else:
                independent += 1

    compared = independent + developmental
    disruption_proxy = ((independent - developmental) / compared) if compared else 0.0
    citing_h_index_proxy = h_index(citing_citation_counts_2024)

    return {
        "total_citations_2024": sum_counts_to_year(counts, GROUND_TRUTH_YEAR),
        "citations_by_year": {str(year): value for year, value in sorted(counts.items()) if year <= GROUND_TRUTH_YEAR},
        "citations_at_1y": counts.get(2018, 0) + counts.get(2019, 0),
        "citations_first_24_months": counts.get(2018, 0) + counts.get(2019, 0),
        "distinct_citing_concepts": len(concepts),
        "citing_review_count": review_citations,
        "citing_paper_h_index_proxy": citing_h_index_proxy,
        "depth_proxy": citing_h_index_proxy + (2 * review_citations),
        "disruption_proxy": disruption_proxy,
        "translation_citation_proxy": translation_citations,
        "citing_works_sampled": len(citing_works),
    }


def fetch_citing_works(work_key: str, max_citing_works: int) -> list[dict[str, Any]]:
    params = {
        "filter": f"cites:{work_key},from_publication_date:2018-01-01,to_publication_date:2024-12-31",
        "per-page": min(max_citing_works, 200),
    }
    try:
        data = openalex_get(OPENALEX_WORKS_URL, params)
    except Exception as exc:
        print(f"OpenAlex citing lookup failed for {work_key}: {exc}")
        return []
    return data.get("results", [])[:max_citing_works]


def semantic_scholar_citing_fallback(work: dict[str, Any]) -> list[dict[str, Any]]:
    doi = (work.get("doi") or "").replace("https://doi.org/", "")
    if not doi:
        return []
    try:
        papers = get_paper_citations(f"DOI:{doi}", limit=100, year_to=GROUND_TRUTH_YEAR)
    except Exception:
        return []

    converted = []
    for paper in papers:
        converted.append(
            {
                "id": paper.get("paperId"),
                "title": paper.get("title"),
                "publication_year": paper.get("year"),
                "counts_by_year": [],
                "type": "",
                "concepts": [{"display_name": field} for field in (paper.get("fieldsOfStudy") or [])],
                "referenced_works": [],
                "primary_location": {"source": {"display_name": paper.get("venue") or ""}},
            }
        )
    return converted


async def run_prediction_state(record: dict[str, Any], *, include_variants: bool) -> dict[str, Any]:
    metadata = record["metadata"]
    extraction = await extract_hypothesis(metadata)
    runner = run_pipeline if include_variants else run_scorecard_pipeline
    return await runner(
        extraction.hypothesis,
        information_cutoff_year=RETRIEVAL_CUTOFF_YEAR,
        backtest_metadata=sanitized_metadata(metadata),
    )


def build_variant_improvement_summary(state: dict[str, Any]) -> dict[str, Any]:
    scorecard = state.get("scorecard")
    ranked = state.get("ranked_variants", [])
    top = ranked[0] if ranked else None
    original = next((variant for variant in ranked if variant.variant_id == "original"), None)
    original_score = int(getattr(scorecard, "composite_score", 0) or 0)
    top_score = int(getattr(top, "composite_score", original_score) or 0) if top else original_score
    return {
        "pipeline_status": "ok" if ranked else "scored_only",
        "original_composite_score": original_score,
        "top_candidate_id": getattr(top, "variant_id", "") if top else "",
        "top_candidate_operator": getattr(top, "operator", "") if top else "",
        "top_candidate_score": top_score,
        "variant_improvement": top_score - original_score,
        "original_dominated": bool(original and not original.is_pareto_selected),
        "pareto_selected_count": sum(1 for variant in ranked if variant.is_pareto_selected),
    }


async def extract_hypothesis(metadata: dict[str, Any]) -> HypothesisExtraction:
    title = metadata["title"]
    abstract = metadata["abstract"]
    prompt = json.dumps(
        {
            "title": title,
            "abstract": abstract,
            "publication_year": metadata["year"],
            "rule": "Use only title and abstract. Do not infer from later citations or later literature.",
        },
        indent=2,
    )
    try:
        return await complete_structured(
            "parser",
            "Extract the paper's central hypothesis from 2018-only metadata.",
            prompt,
            HypothesisExtraction,
            temperature=0.1,
        )
    except (LLMUnavailable, ValueError, TypeError):
        first_sentence = abstract.split(". ")[0].strip()
        claim = first_sentence if first_sentence else title
        return HypothesisExtraction(
            hypothesis=f"The paper tests whether {title}.",
            claim=claim,
            mechanism="mechanism described in the abstract",
            context=metadata.get("venue") or metadata.get("area") or "AI research",
            population=", ".join(metadata.get("concepts", [])[:3]) or "AI systems or datasets",
            method="method described in the title and abstract",
        )


async def run_single_call_baseline(record: dict[str, Any]) -> ImpactForecast:
    metadata = sanitized_metadata(record["metadata"])
    prompt = json.dumps(
        {
            "task": "Predict six-dimensional impact from one direct GPT-5 call.",
            "metadata_2018_only": metadata,
            "dimensions": DIMENSIONS,
            "cutoff_year": PREDICTION_CUTOFF_YEAR,
        },
        indent=2,
    )
    try:
        return await complete_structured(
            "strategist",
            "You are a single-call baseline. Predict impact without multi-agent decomposition.",
            prompt,
            ImpactForecast,
            temperature=0.2,
        )
    except (LLMUnavailable, ValueError, TypeError):
        state = {
            "raw_hypothesis": metadata["title"],
            "parsed": ParsedHypothesis(
                claim=metadata["title"],
                mechanism="unspecified",
                context=metadata.get("venue") or "AI research",
                population=", ".join(metadata.get("concepts", [])[:2]) or "AI systems",
                method="unspecified",
            ),
            "backtest_metadata": metadata,
            "information_cutoff_year": PREDICTION_CUTOFF_YEAR,
        }
        result = await impact_forecaster(state)
        forecast = result["forecast"]
        return dampen_forecast(forecast, 0.82)


def build_result_row(
    record: dict[str, Any],
    prediction: ImpactForecast,
    baseline_gpt: ImpactForecast,
) -> dict[str, Any]:
    metadata = record["metadata"]
    truth = record["ground_truth"]
    row: dict[str, Any] = {
        "paper_id": metadata["paper_id"],
        "title": metadata["title"],
        "area": metadata["area"],
        "venue": metadata.get("venue", ""),
        "citation_1y_baseline": truth["citations_at_1y"],
        "author_count": len(metadata.get("authors", []) or []),
        "venue_prestige": venue_prestige(metadata.get("venue", "")),
        "abstract_length": len((metadata.get("abstract") or "").split()),
        "concept_count": len(metadata.get("concepts", []) or []),
    }
    actual_map = {
        "volume": truth["total_citations_2024"],
        "velocity": truth["citations_first_24_months"],
        "reach": truth["distinct_citing_concepts"],
        "depth": truth["depth_proxy"],
        "disruption": truth["disruption_proxy"],
        "translation": truth["translation_citation_proxy"],
    }
    for dimension in DIMENSIONS:
        row[f"actual_{dimension}"] = actual_map[dimension]
        row[f"predicted_{dimension}"] = getattr(prediction, dimension).score
        row[f"predicted_{dimension}_raw"] = getattr(prediction, dimension).predicted_value
        row[f"single_call_{dimension}"] = getattr(baseline_gpt, dimension).score
    return row


def add_linear_regression_baseline(results: list[dict[str, Any]]) -> None:
    if not results:
        return
    features = np.array(
        [
            [
                1.0,
                row["citation_1y_baseline"],
                row["author_count"],
                row["venue_prestige"],
                row["abstract_length"],
                row["concept_count"],
            ]
            for row in results
        ],
        dtype=float,
    )
    for dimension in DIMENSIONS:
        y = np.array([row[f"actual_{dimension}"] for row in results], dtype=float)
        predictions = leave_one_out_linear_predictions(features, y)
        for row, pred in zip(results, predictions):
            row[f"linear_{dimension}"] = float(pred)


def add_mean_and_random_baselines(results: list[dict[str, Any]]) -> None:
    if not results:
        return
    rng = np.random.default_rng(42)
    for dimension in DIMENSIONS:
        actual = np.array([row[f"actual_{dimension}"] for row in results], dtype=float)
        mean_value = float(np.mean(actual)) if len(actual) else 0.0
        if len(actual) > 1:
            random_values = rng.permutation(actual)
        else:
            random_values = actual
        for idx, row in enumerate(results):
            row[f"mean_{dimension}"] = mean_value
            row[f"random_{dimension}"] = float(random_values[idx]) if len(random_values) else 0.0


def leave_one_out_linear_predictions(features: np.ndarray, y: np.ndarray) -> np.ndarray:
    n_rows = len(y)
    predictions = np.zeros(n_rows, dtype=float)
    if n_rows < 3:
        predictions[:] = float(np.mean(y)) if n_rows else 0.0
        return predictions
    for idx in range(n_rows):
        mask = np.ones(n_rows, dtype=bool)
        mask[idx] = False
        beta, *_ = np.linalg.lstsq(features[mask], y[mask], rcond=None)
        predictions[idx] = float(features[idx] @ beta)
    return predictions


def compute_correlations(results: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    correlations: dict[str, dict[str, float]] = {}
    for dimension in DIMENSIONS:
        actual = [row[f"actual_{dimension}"] for row in results]
        correlations[dimension] = {
            "forecaster": spearman(actual, [row[f"predicted_{dimension}"] for row in results]),
            "citation_1y": spearman(actual, [row["citation_1y_baseline"] for row in results]),
            "single_call": spearman(actual, [row[f"single_call_{dimension}"] for row in results]),
            "linear_regression": spearman(actual, [row.get(f"linear_{dimension}", 0.0) for row in results]),
            "mean_baseline": spearman(actual, [row.get(f"mean_{dimension}", 0.0) for row in results]),
            "random_baseline": spearman(actual, [row.get(f"random_{dimension}", 0.0) for row in results]),
        }
    return correlations


def build_variant_improvement_export(results: list[dict[str, Any]]) -> dict[str, Any]:
    improvements = [float(row.get("variant_improvement", 0)) for row in results]
    dominated = [bool(row.get("original_dominated")) for row in results]
    return {
        "records": [
            {
                "paper_id": row.get("paper_id"),
                "title": row.get("title"),
                "original_composite_score": row.get("original_composite_score"),
                "top_candidate_id": row.get("top_candidate_id"),
                "top_candidate_operator": row.get("top_candidate_operator"),
                "top_candidate_score": row.get("top_candidate_score"),
                "variant_improvement": row.get("variant_improvement"),
                "original_dominated": row.get("original_dominated"),
                "pareto_selected_count": row.get("pareto_selected_count"),
                "pipeline_status": row.get("pipeline_status"),
            }
            for row in results
        ],
        "summary": {
            "record_count": len(results),
            "mean_variant_improvement": float(np.mean(improvements)) if improvements else 0.0,
            "median_variant_improvement": float(np.median(improvements)) if improvements else 0.0,
            "original_dominated_rate": float(sum(dominated) / len(dominated)) if dominated else 0.0,
        },
    }


def write_results_csv(path: Path, results: list[dict[str, Any]]) -> None:
    if not results:
        path.write_text("")
        return
    fieldnames = list(results[0].keys())
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)


def write_scatter_plot(path: Path, results: list[dict[str, Any]], correlations: dict[str, dict[str, float]]) -> None:
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 3, figsize=(15, 9))
    fig.suptitle("2018 AI Paper Backtest: Predicted Impact vs 2024 Ground Truth", fontsize=15)
    for ax, dimension in zip(axes.flatten(), DIMENSIONS):
        actual = [row[f"actual_{dimension}"] for row in results]
        predicted = [row[f"predicted_{dimension}"] for row in results]
        ax.scatter(actual, predicted, s=42, alpha=0.78, edgecolor="white", linewidth=0.5)
        ax.set_title(f"{dimension.title()} (rho={correlations[dimension]['forecaster']:.2f})")
        ax.set_xlabel("Actual 2024 metric")
        ax.set_ylabel("Predicted score")
        ax.grid(True, alpha=0.25)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(path, dpi=180)
    plt.close(fig)


def metadata_from_work(work: dict[str, Any], area: str, query: str) -> dict[str, Any]:
    return {
        "paper_id": work["id"],
        "openalex_key": openalex_key(work["id"]),
        "doi": (work.get("doi") or "").replace("https://doi.org/", ""),
        "title": work.get("title") or work.get("display_name") or "Untitled",
        "authors": author_names(work),
        "year": work.get("publication_year"),
        "publication_date": work.get("publication_date"),
        "venue": source_name(work),
        "abstract": abstract_text(work),
        "concepts": extract_concepts(work)[:12],
        "area": area,
        "selection_query": query,
        "referenced_works_count": len(work.get("referenced_works") or []),
    }


def sanitized_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    allowed = (
        "paper_id",
        "openalex_key",
        "doi",
        "title",
        "authors",
        "year",
        "publication_date",
        "venue",
        "abstract",
        "concepts",
        "area",
        "selection_query",
        "referenced_works_count",
    )
    return {key: metadata.get(key) for key in allowed}


def paper_from_metadata(metadata: dict[str, Any]) -> Paper:
    return Paper(
        paper_id=metadata["paper_id"],
        title=metadata["title"],
        authors=metadata.get("authors", []),
        year=metadata.get("year"),
        abstract=metadata.get("abstract", ""),
        url=metadata.get("paper_id", ""),
        citation_count=0,
        relevance_score=1.0,
        cluster=metadata.get("area", "ai"),
    )


def is_ai_paper(metadata: dict[str, Any]) -> bool:
    title = (metadata.get("title", "") or "").strip().lower()
    if not title or title == "untitled" or "invited talk" in title:
        return False
    title_and_concepts = " ".join(
        [
            metadata.get("title", ""),
            " ".join(metadata.get("concepts", [])),
        ]
    ).lower()
    abstract = (metadata.get("abstract", "") or "").lower()
    if any(keyword in title_and_concepts for keyword in AI_KEYWORDS):
        return True
    return sum(1 for keyword in AI_KEYWORDS if keyword in abstract) >= 2


def openalex_get(endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
    request_params = dict(params)
    if OPENALEX_EMAIL:
        request_params["mailto"] = OPENALEX_EMAIL
    headers = {"User-Agent": "MAgent4Science/0.1 historical-backtest"}
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            data, _from_cache = cached_get_json(
                "openalex",
                endpoint,
                request_params,
                headers=headers,
                timeout=MAX_API_TIMEOUT,
            )
            return data
        except Exception as exc:
            last_error = exc
            time.sleep(0.8 * (attempt + 1))
    raise RuntimeError(f"OpenAlex request failed after retries: {last_error}")


def abstract_text(work: dict[str, Any]) -> str:
    inverted = work.get("abstract_inverted_index") or {}
    if not inverted:
        return ""
    positions: dict[int, str] = {}
    for word, offsets in inverted.items():
        for offset in offsets:
            positions[int(offset)] = word
    return " ".join(positions[idx] for idx in sorted(positions))


def author_names(work: dict[str, Any]) -> list[str]:
    names = []
    for authorship in work.get("authorships", []) or []:
        author = authorship.get("author") or {}
        name = author.get("display_name")
        if name:
            names.append(name)
    return names


def source_name(work: dict[str, Any]) -> str:
    primary = work.get("primary_location") or {}
    source = primary.get("source") or {}
    if source.get("display_name"):
        return source["display_name"]
    host_venue = work.get("host_venue") or {}
    return host_venue.get("display_name") or ""


def extract_concepts(work: dict[str, Any]) -> list[str]:
    names = []
    for concept in work.get("concepts", []) or []:
        name = concept.get("display_name")
        if name:
            names.append(name)
    for topic in work.get("topics", []) or []:
        name = topic.get("display_name")
        if name:
            names.append(name)
    seen = set()
    deduped = []
    for name in names:
        key = name.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(name)
    return deduped


def counts_by_year(work: dict[str, Any]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for item in work.get("counts_by_year") or []:
        year = item.get("year")
        cited_by_count = item.get("cited_by_count")
        if year is not None and cited_by_count is not None:
            counts[int(year)] = int(cited_by_count)
    return counts


def sum_counts_to_year(counts: dict[int, int], year_to: int) -> int:
    return sum(value for year, value in counts.items() if year <= year_to)


def h_index(citation_counts: list[int]) -> int:
    sorted_counts = sorted((count for count in citation_counts if count >= 0), reverse=True)
    index = 0
    for index, count in enumerate(sorted_counts, start=1):
        if count < index:
            return index - 1
    return index


def openalex_key(openalex_id: str) -> str:
    return openalex_id.rstrip("/").rsplit("/", 1)[-1]


def normalized_title(title: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in title).split())


def venue_prestige(venue: str) -> int:
    text = (venue or "").lower()
    if any(name in text for name in TOP_VENUES):
        return 3
    if text:
        return 1
    return 0


def dampen_forecast(forecast: ImpactForecast, factor: float) -> ImpactForecast:
    updates = {}
    for dimension in DIMENSIONS:
        value = getattr(forecast, dimension)
        score = int(max(0, min(100, round(value.score * factor + 50 * (1 - factor)))))
        low = max(0, score - 20)
        high = min(100, score + 20)
        updates[dimension] = value.model_copy(
            update={
                "score": score,
                "confidence_low": low,
                "confidence_high": high,
                "rationale": "Single-call baseline fallback with damped heuristic signal.",
            }
        )
    return forecast.model_copy(update=updates)


def spearman(actual: list[float], predicted: list[float]) -> float:
    if len(actual) < 2 or len(predicted) < 2:
        return 0.0
    actual_ranks = rankdata(actual)
    predicted_ranks = rankdata(predicted)
    return pearson(actual_ranks, predicted_ranks)


def rankdata(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    idx = 0
    while idx < len(indexed):
        end = idx + 1
        while end < len(indexed) and indexed[end][1] == indexed[idx][1]:
            end += 1
        rank = (idx + 1 + end) / 2.0
        for original_idx, _value in indexed[idx:end]:
            ranks[original_idx] = rank
        idx = end
    return ranks


def pearson(left: list[float], right: list[float]) -> float:
    left_arr = np.array(left, dtype=float)
    right_arr = np.array(right, dtype=float)
    left_arr = left_arr - left_arr.mean()
    right_arr = right_arr - right_arr.mean()
    denom = float(np.linalg.norm(left_arr) * np.linalg.norm(right_arr))
    if denom == 0.0:
        return 0.0
    return float(np.dot(left_arr, right_arr) / denom)


if __name__ == "__main__":
    asyncio.run(main())
