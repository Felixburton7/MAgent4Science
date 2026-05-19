from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.cartographer import cartographer
from backend.pipeline import _impact_metric_scores
from backend.schemas import ImpactDimension, ImpactForecast, MetricScore, Paper, ParsedHypothesis


class MetricContractTests(unittest.TestCase):
    def test_metric_aliases_validate_to_canonical_fields(self) -> None:
        metric = MetricScore.model_validate(
            {
                "metric_name": "novelty",
                "score": 71,
                "confidence_low": 63,
                "confidence_high": 79,
                "rationale": "Alias compatibility.",
                "evidence": ["doi:10.123/example"],
                "method": "test:v1",
            }
        )

        self.assertEqual(metric.name, "novelty")
        self.assertEqual(metric.evidence_ids, ["doi:10.123/example"])
        self.assertEqual(metric.method, "test:v1")

    def test_impact_metric_scores_have_method_and_evidence(self) -> None:
        forecast = ImpactForecast(
            volume=_dim(60),
            velocity=_dim(61),
            reach=_dim(62),
            depth=_dim(63),
            disruption=_dim(64),
            translation=_dim(65),
            overall_summary="summary",
        )
        state = {
            "papers": [
                Paper(
                    paper_id="p1",
                    title="Example",
                    doi="10.123/example",
                    relevance_score=1.0,
                )
            ]
        }

        metrics = _impact_metric_scores(forecast, state)

        self.assertEqual(len(metrics), 6)
        self.assertTrue(all(metric.method for metric in metrics))
        self.assertTrue(all(metric.evidence_ids == ["doi:10.123/example"] for metric in metrics))


class RetrievalCutoffTests(unittest.IsolatedAsyncioTestCase):
    async def test_cartographer_filters_sources_by_cutoff_year(self) -> None:
        openalex_payload = {
            "meta": {"count": 2},
            "results": [
                _openalex_work("Older paper", 2017, "https://openalex.org/W1"),
                _openalex_work("Future paper", 2019, "https://openalex.org/W2"),
            ],
        }
        semantic_payload = [
            {
                "title": "Semantic older paper",
                "paperId": "s1",
                "year": 2017,
                "abstract": "sparse autoencoder residual stream",
                "citationCount": 99,
                "externalIds": {"DOI": "10.123/s1"},
                "authors": [],
            },
            {
                "title": "Semantic future paper",
                "paperId": "s2",
                "year": 2019,
                "abstract": "sparse autoencoder residual stream",
                "citationCount": 99,
                "externalIds": {"DOI": "10.123/s2"},
                "authors": [],
            },
        ]

        with (
            patch("backend.cartographer.search_works", return_value=openalex_payload) as openalex,
            patch("backend.cartographer.search_paper_records", return_value=semantic_payload),
        ):
            result = await cartographer(
                {
                    "raw_hypothesis": "Sparse autoencoder residual stream",
                    "parsed": ParsedHypothesis(
                        claim="Sparse autoencoder residual stream",
                        mechanism="unspecified",
                        context="unspecified",
                        population="unspecified",
                        method="unspecified",
                    ),
                    "information_cutoff_year": 2017,
                }
            )

        self.assertIn("to_publication_date:2017-12-31", openalex.call_args.kwargs["filter"])
        self.assertTrue(all((paper.year or 0) <= 2017 for paper in result["papers"]))
        self.assertTrue(all(paper.citation_count < 99 for paper in result["papers"]))
        self.assertEqual(result["retrieval_report"].cutoff_year, 2017)


def _dim(score: int) -> ImpactDimension:
    return ImpactDimension(
        score=score,
        confidence_low=max(0, score - 5),
        confidence_high=min(100, score + 5),
        rationale=f"score {score}",
    )


def _openalex_work(title: str, year: int, work_id: str) -> dict:
    return {
        "display_name": title,
        "publication_year": year,
        "id": work_id,
        "doi": "",
        "authorships": [],
        "abstract_inverted_index": {
            "sparse": [0],
            "autoencoder": [1],
            "residual": [2],
            "stream": [3],
        },
        "cited_by_count": 99,
        "counts_by_year": [{"year": year, "cited_by_count": 4}],
        "relevance_score": 10,
        "concepts": [],
    }


if __name__ == "__main__":
    unittest.main()
