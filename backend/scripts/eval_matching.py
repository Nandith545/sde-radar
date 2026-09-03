"""Measure ranking quality of score_job against a labelled scenario.

Run it:

    cd backend && ./venv/bin/python scripts/eval_matching.py
    ./venv/bin/python scripts/eval_matching.py --baseline evals/baseline.json
    ./venv/bin/python scripts/eval_matching.py --save-baseline evals/baseline.json

Why this exists: the scorer has roughly a dozen weights, and until now the
only way to judge a change to one of them was to look at a result list and
form an impression. That is not a measurement -- it cannot tell a real
improvement from a rearrangement, and it cannot catch a change that helps the
jobs you looked at while hurting the ones you didn't.

A scenario is one candidate plus a pool of postings graded 0/1/2 for that
candidate (see evals/seattle_backend.json). The harness scores the pool,
ranks it, and reports nDCG@10 -- which rewards putting strongly-relevant
postings near the top -- alongside precision@5 and the specific pairs the
ranking got backwards. The inversions are usually the useful output: they
name the posting that outranked something better and by how much.

Deliberately not a pytest gate on the metric itself. The grades are one
person's judgement and will be edited; a hard threshold on a subjective
number produces failures that get suppressed rather than fixed. Instead
tests/test_eval_harness.py checks that the harness runs and the scenario
parses, and a floor is asserted well below the current score so a collapse
is caught without pinning the exact value.

Uses the bundled seed pool, so it needs no database and runs anywhere.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import models
from app.services.matching import score_job
from app.services.seed_jobs import SEED_JOBS
from app.services.skills import extract_skills


def _build(scenario: dict) -> tuple[models.User, models.Resume, list[models.JobListing]]:
    p = scenario["profile"]
    user = models.User(
        email="eval@example.com",
        full_name="Eval",
        hashed_password="x",
        target_titles=p["target_titles"],
        target_cities=p["target_cities"],
        target_country=p["target_country"],
        target_states=p["target_states"],
        work_mode=p["work_mode"],
        seniority=p["seniority"],
        min_salary=p["min_salary"],
    )
    resume = models.Resume(
        filename="eval.txt",
        raw_text="",
        skills=p["resume_skills"],
        years_experience=p["years_experience"],
    )
    jobs = []
    for raw in SEED_JOBS:
        if raw["external_id"] not in scenario["labels"]:
            continue
        job = models.JobListing(**raw, source="seed", sources=[])
        # Tagged exactly as job_ingestion tags a real posting.
        job.skills = extract_skills(f"{job.title}\n{job.description}")
        jobs.append(job)
    return user, resume, jobs


def _ndcg(grades: list[int], k: int) -> float:
    def dcg(gs: list[int]) -> float:
        return sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(gs[:k]))

    ideal = dcg(sorted(grades, reverse=True))
    return dcg(grades) / ideal if ideal else 0.0


def evaluate(scenario: dict) -> dict:
    user, resume, jobs = _build(scenario)
    labels = scenario["labels"]

    ranked = sorted(
        ((score_job(j, user, resume).score, j) for j in jobs),
        key=lambda pair: -pair[0],
    )
    grades = [labels[j.external_id] for _, j in ranked]

    at5 = grades[:5]
    inversions = [
        (hi_i + 1, lo_i + 1, ranked[lo_i][1].title, ranked[hi_i][1].title, grades[lo_i], grades[hi_i])
        for lo_i in range(len(grades))
        for hi_i in range(lo_i + 1, len(grades))
        if grades[hi_i] > grades[lo_i]
    ]
    return {
        "ndcg@10": round(_ndcg(grades, 10), 4),
        "precision@5": round(sum(1 for g in at5 if g == 2) / 5, 4),
        "inversions": len(inversions),
        "ranked": [
            {"rank": i + 1, "score": s, "grade": labels[j.external_id], "title": j.title}
            for i, (s, j) in enumerate(ranked)
        ],
        "worst_inversions": sorted(inversions, key=lambda t: t[1] - t[0])[:5],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("scenario", nargs="?", default="evals/seattle_backend.json")
    ap.add_argument("--baseline", help="compare against a saved run")
    ap.add_argument("--save-baseline", help="write this run's metrics for later comparison")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    scenario = json.loads(Path(args.scenario).read_text())
    result = evaluate(scenario)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"\n{scenario['name']}\n")
        print(f"  {'#':>3}  {'score':>5}  {'grade':>5}  title")
        for row in result["ranked"]:
            marker = "  <-- poor fit, ranked high" if row["grade"] == 0 and row["rank"] <= 8 else ""
            print(f"  {row['rank']:>3}  {row['score']:>5}  {row['grade']:>5}  {row['title'][:52]}{marker}")
        print(f"\n  nDCG@10      {result['ndcg@10']}")
        print(f"  precision@5  {result['precision@5']}")
        print(f"  inversions   {result['inversions']}")
        if result["worst_inversions"]:
            print("\n  Worst inversions (better posting ranked below a worse one):")
            for hi, lo, lo_title, hi_title, lo_g, hi_g in result["worst_inversions"]:
                print(f"    #{lo} grade {lo_g}  {lo_title[:34]:36} beat  #{hi} grade {hi_g}  {hi_title[:34]}")

    if args.save_baseline:
        Path(args.save_baseline).write_text(
            json.dumps({k: result[k] for k in ("ndcg@10", "precision@5", "inversions")}, indent=2)
        )
        print(f"\n  baseline written to {args.save_baseline}")

    if args.baseline:
        old = json.loads(Path(args.baseline).read_text())
        print("\n  vs baseline:")
        for key in ("ndcg@10", "precision@5", "inversions"):
            delta = result[key] - old[key]
            arrow = "same" if delta == 0 else f"{delta:+g}"
            print(f"    {key:<12} {old[key]} -> {result[key]}  ({arrow})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
