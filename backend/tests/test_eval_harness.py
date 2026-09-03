"""The ranking-quality harness.

Deliberately does not assert an exact nDCG. The relevance grades in the
scenario are one person's judgement and are meant to be edited; pinning the
number would turn every honest relabelling into a failing build, and the
usual response to that is to bump the constant rather than look at the
ranking. What is worth catching is a collapse -- a change that stops the
scorer discriminating at all -- so the floor sits well below where the
harness currently runs.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from eval_matching import evaluate

from app.services.seed_jobs import SEED_JOBS

SCENARIO = Path(__file__).resolve().parent.parent / "evals" / "seattle_backend.json"


def _scenario() -> dict:
    return json.loads(SCENARIO.read_text())


def test_every_seed_job_carries_a_grade() -> None:
    """An unlabelled posting is silently dropped from the metric, which is
    how a scenario quietly stops measuring the thing it claims to."""
    labels = _scenario()["labels"]
    assert {j["external_id"] for j in SEED_JOBS} == set(labels)


def test_grades_are_within_the_documented_scale() -> None:
    assert set(_scenario()["labels"].values()) <= {0, 1, 2}


def test_the_harness_produces_a_full_ranking() -> None:
    result = evaluate(_scenario())
    assert len(result["ranked"]) == len(_scenario()["labels"])
    assert [row["rank"] for row in result["ranked"]] == list(range(1, len(result["ranked"]) + 1))
    scores = [row["score"] for row in result["ranked"]]
    assert scores == sorted(scores, reverse=True)


def test_the_scorer_still_discriminates() -> None:
    """A floor, not a target. Ranking at random scores around 0.5 here, so
    anything near that means the scorer has stopped separating a backend role
    from field robotics."""
    assert evaluate(_scenario())["ndcg@10"] > 0.6
