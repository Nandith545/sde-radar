"""Cross-source deduplication — the core of the multi-board feature.

Migrated from the original standalone test_dedup.py script into real pytest
cases, so each behaviour fails independently instead of the whole script
aborting on the first bad assertion.
"""

import pytest

from app import models
from app.services.dedup import (
    make_dedup_key,
    normalize_company,
    normalize_location,
    normalize_title,
)
from app.services.job_ingestion import _ingest_raw_jobs
from app.services.sources.base import RawJob


def raw(**overrides) -> RawJob:
    fields = {
        "source": "adzuna",
        "external_id": "1",
        "title": "Senior Software Engineer",
        "company": "Acme Corp",
        "location": "Seattle, WA",
        "description": "Build things.",
        "comp_min": None,
        "comp_max": None,
        "comp_unit": "year",
        "job_type": "Full-time",
        "posted": "2026-08-20",
        "url": "https://example.com/1",
    }
    fields.update(overrides)
    return RawJob(**fields)


# ---- Normalisation ------------------------------------------------------


@pytest.mark.parametrize(
    ("raw_name", "expected"),
    [
        ("Acme Corp", "acme"),
        ("Acme Corporation", "acme"),
        ("Acme, Inc.", "acme"),
        ("ACME LLC", "acme"),
        ("Acme Ltd", "acme"),
    ],
)
def test_company_normalisation_strips_legal_suffixes(raw_name: str, expected: str) -> None:
    assert normalize_company(raw_name) == expected


def test_location_normalisation_keeps_only_the_city() -> None:
    assert normalize_location("Seattle, WA") == normalize_location("Seattle, Washington, USA")


def test_dedup_key_is_stable_across_cosmetic_differences() -> None:
    a = make_dedup_key("Senior Software Engineer", "Acme Corp", "Seattle, WA")
    b = make_dedup_key("senior software engineer", "Acme, Inc.", "Seattle, WA")
    assert a == b


def test_normalize_title_is_case_and_punctuation_insensitive() -> None:
    assert normalize_title("Senior Software Engineer!") == normalize_title("senior software engineer")


# ---- Ingestion and merging ---------------------------------------------


def test_identical_posting_on_two_boards_collapses_to_one_row(db) -> None:
    result = _ingest_raw_jobs(
        db,
        [
            raw(source="adzuna", external_id="a1"),
            raw(source="jooble", external_id="j1"),
        ],
    )
    assert result["added"] == 1
    assert result["merged_into_existing"] == 1
    assert db.query(models.JobListing).count() == 1

    job = db.query(models.JobListing).one()
    assert sorted(e["name"] for e in job.sources) == ["adzuna", "jooble"]


def test_fuzzy_title_variant_at_the_same_company_merges(db) -> None:
    _ingest_raw_jobs(db, [raw(source="adzuna", external_id="a1", title="Senior Software Engineer")])
    _ingest_raw_jobs(db, [raw(source="remotive", external_id="r1", title="Sr. Software Engineer")])

    assert db.query(models.JobListing).count() == 1


def test_similar_title_at_a_different_company_does_not_merge(db) -> None:
    """The dangerous false positive: fuzzy matching must stay scoped to one
    company, or unrelated jobs get silently collapsed."""
    _ingest_raw_jobs(db, [raw(source="adzuna", external_id="a1", company="Acme Corp")])
    result = _ingest_raw_jobs(
        db, [raw(source="jooble", external_id="j1", company="Initech LLC", title="Sr. Software Engineer")]
    )

    assert result["added"] == 1
    assert result["merged_into_existing"] == 0
    assert db.query(models.JobListing).count() == 2


def test_reingesting_the_same_posting_is_an_update_not_a_duplicate(db) -> None:
    _ingest_raw_jobs(db, [raw(source="adzuna", external_id="a1", posted="2026-08-20")])
    result = _ingest_raw_jobs(db, [raw(source="adzuna", external_id="a1", posted="2026-08-25")])

    assert result == {"added": 0, "merged_into_existing": 0, "same_source_updates": 1}
    job = db.query(models.JobListing).one()
    assert job.posted == "2026-08-25"  # newer date wins
    assert sum(1 for e in job.sources if e["name"] == "adzuna") == 1


def test_a_real_salary_is_never_clobbered_by_a_blank_one(db) -> None:
    _ingest_raw_jobs(db, [raw(source="adzuna", external_id="a1", comp_min=140000, comp_max=180000)])
    _ingest_raw_jobs(db, [raw(source="jooble", external_id="j1", comp_min=None, comp_max=None)])

    job = db.query(models.JobListing).one()
    assert job.comp_min == 140000
    assert job.comp_max == 180000


def test_the_longer_description_wins(db) -> None:
    _ingest_raw_jobs(db, [raw(source="adzuna", external_id="a1", description="Short.")])
    _ingest_raw_jobs(
        db, [raw(source="jooble", external_id="j1", description="A considerably longer description.")]
    )

    assert "considerably longer" in db.query(models.JobListing).one().description


def test_canonical_title_does_not_flap_between_refreshes(db) -> None:
    """Regression: an earlier version overwrote title on every merge, so the
    displayed name changed depending on which board answered last."""
    _ingest_raw_jobs(db, [raw(source="adzuna", external_id="a1", title="Senior Software Engineer")])
    _ingest_raw_jobs(db, [raw(source="remotive", external_id="r1", title="Sr. Software Engineer")])

    assert db.query(models.JobListing).one().title == "Senior Software Engineer"


def test_genuinely_different_jobs_stay_separate(db) -> None:
    result = _ingest_raw_jobs(
        db,
        [
            raw(source="adzuna", external_id="a1", title="Senior Software Engineer", company="Acme"),
            raw(source="adzuna", external_id="a2", title="Data Engineer", company="Globex"),
            raw(source="adzuna", external_id="a3", title="Product Manager", company="Initech"),
        ],
    )
    assert result["added"] == 3
    assert db.query(models.JobListing).count() == 3


def test_malformed_source_entries_do_not_merge_unrelated_jobs(db) -> None:
    """Entries missing name/external_id must be skipped rather than keyed on
    None, which would make every incomplete row collide."""
    db.add_all(
        [
            models.JobListing(
                external_id="x:1",
                source="x",
                sources=[{"url": "no name or id"}],
                title="Job One",
                company="Company One",
                location="Seattle, WA",
                company_norm="company one",
                title_norm="job one",
                dedup_key="company one|job one|seattle",
            ),
            models.JobListing(
                external_id="x:2",
                source="x",
                sources=[{"url": "also incomplete"}],
                title="Job Two",
                company="Company Two",
                location="Seattle, WA",
                company_norm="company two",
                title_norm="job two",
                dedup_key="company two|job two|seattle",
            ),
        ]
    )
    db.commit()

    _ingest_raw_jobs(db, [raw(source="new", external_id="n1", title="Job Three", company="Company Three")])
    assert db.query(models.JobListing).count() == 3
