"""Work-mode and country inference.

The behaviour worth pinning is the refusal to guess: an unreadable posting
must come back "unknown" so the caller can skip the preference, rather than
being quietly classified and then quietly penalised.
"""

import datetime

import pytest

from app.services.job_facets import (
    FRESHNESS_WINDOWS,
    MAX_AGE_DAYS,
    annual_comp,
    infer_country,
    infer_seniority,
    infer_work_mode,
    job_age_days,
    normalize_country,
    seniority_distance,
    seniority_from_years,
)


@pytest.mark.parametrize(
    ("location", "title", "expected"),
    [
        ("Remote (US)", "Software Engineer", "remote"),
        ("Anywhere", "Backend Engineer", "remote"),
        ("Seattle, WA", "Software Engineer (Hybrid)", "hybrid"),
        ("Berlin, Germany — Hybrid", "Engineer", "hybrid"),
        ("Austin, TX", "On-site Platform Engineer", "onsite"),
        ("Seattle, WA", "Software Engineer", "unknown"),
        ("", "", "unknown"),
    ],
)
def test_work_mode_inference(location: str, title: str, expected: str) -> None:
    assert infer_work_mode(location, title) == expected


def test_hybrid_wins_over_remote() -> None:
    """A hybrid posting nearly always says "remote" too; the reverse is rare."""
    assert infer_work_mode("Hybrid — 2 days remote", "Engineer") == "hybrid"


def test_description_is_consulted_only_after_location_and_title() -> None:
    # "remote" here describes a perk, not the role, so a location that already
    # settles the question must win.
    assert infer_work_mode("On-site, Austin TX", "Engineer", "We offer remote Fridays") == "onsite"
    # With nothing stronger available, the description is allowed to decide.
    assert infer_work_mode("", "Engineer", "This role is fully remote") == "remote"


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        ("Seattle, WA", "united states"),
        ("Austin, TX", "united states"),
        ("New York, United States", "united states"),
        ("Leipzig", "germany"),
        ("Berlin, Germany", "germany"),
        ("London", "united kingdom"),
        ("Bengaluru", "india"),
        ("Toronto", "canada"),
        ("Atlantis", "unknown"),
        ("", "unknown"),
    ],
)
def test_country_inference(location: str, expected: str) -> None:
    assert infer_country(location) == expected


def test_unrecognised_location_is_unknown_not_a_default() -> None:
    """The whole design rests on this: no guess means no penalty."""
    assert infer_country("Somewhere Nobody Listed") == "unknown"


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("USA", "united states"),
        ("usa", "united states"),
        ("United States", "united states"),
        ("Germany", "germany"),
        ("UK", "united kingdom"),
        ("", ""),
    ],
)
def test_user_input_normalizes_onto_the_same_vocabulary(typed: str, expected: str) -> None:
    assert normalize_country(typed) == expected


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Junior Software Engineer", "entry"),
        ("Software Engineer Intern", "entry"),
        ("New Grad Software Engineer", "entry"),
        ("Senior Software Engineer", "senior"),
        ("Staff Engineer", "senior"),
        ("Principal Engineer", "senior"),
        ("Software Engineer III", "senior"),
        ("Software Engineer", "mid"),
        ("Backend Engineer", "mid"),
    ],
)
def test_seniority_inference(title: str, expected: str) -> None:
    assert infer_seniority(title) == expected


def test_an_unmarked_title_reads_as_mid_not_unknown() -> None:
    """Employers label junior and senior and leave mid bare, so the absence of
    a marker is signal here -- unlike work mode, where absence means nothing."""
    assert infer_seniority("Software Engineer") == "mid"


def test_senior_wins_when_a_title_carries_both_markers() -> None:
    assert infer_seniority("Senior Engineer, New Grad Mentorship") == "senior"


@pytest.mark.parametrize(
    ("years", "expected"),
    [
        (None, ""),
        (0.5, "entry"),
        (1.9, "entry"),
        (2.0, "mid"),
        (6.9, "mid"),
        (7.0, "senior"),
        (15.0, "senior"),
    ],
)
def test_seniority_from_resume_years(years: float | None, expected: str) -> None:
    assert seniority_from_years(years) == expected


def test_seniority_distance() -> None:
    assert seniority_distance("mid", "mid") == 0
    assert seniority_distance("entry", "mid") == 1
    assert seniority_distance("entry", "senior") == 2
    assert seniority_distance("nonsense", "mid") == -1


@pytest.mark.parametrize(
    ("cmin", "cmax", "unit", "expected"),
    [
        (150000, 200000, "year", 200000),
        (150000, None, "year", 150000),
        (None, None, "year", None),
        (0, 0, "year", None),
        (80, 100, "hour", 100 * 2080),
    ],
)
def test_annual_comp(cmin, cmax, unit, expected) -> None:
    assert annual_comp(cmin, cmax, unit) == expected


def test_a_posting_without_salary_is_unknown_not_zero() -> None:
    """The distinction the salary floor depends on: most boards omit pay."""
    assert annual_comp(None, None, "year") is None


# ---- Freshness ---------------------------------------------------------


def _dt(iso: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(iso).replace(tzinfo=datetime.UTC)


def test_age_prefers_the_boards_own_posted_date() -> None:
    now = _dt("2026-08-28")
    # created_at is much later than posted; posted must win.
    assert job_age_days("2026-08-21", _dt("2026-08-28"), now) == 7


def test_age_falls_back_to_created_at_when_posted_is_empty() -> None:
    """Arbeitnow blanks `posted` when the timestamp won't parse. created_at is
    a real upper bound -- we can't have ingested a job before it existed."""
    now = _dt("2026-08-28")
    assert job_age_days("", _dt("2026-08-26"), now) == 2


def test_age_falls_back_when_posted_is_unparseable() -> None:
    now = _dt("2026-08-28")
    assert job_age_days("not-a-date", _dt("2026-08-26"), now) == 2


def test_age_handles_naive_datetimes_from_sqlite() -> None:
    """SQLite returns naive datetimes even for timezone=True columns."""
    now = _dt("2026-08-28")
    naive = datetime.datetime(2026, 8, 26)
    assert job_age_days("", naive, now) == 2


def test_a_future_posted_date_is_clamped_to_zero() -> None:
    now = _dt("2026-08-28")
    assert job_age_days("2026-09-05", _dt("2026-08-28"), now) == 0


def test_freshness_windows_do_not_offer_an_hour_option() -> None:
    """`posted` is date-only -- every connector truncates with [:10] -- so an
    hour window could only be answered against created_at, which is when we
    first saw the posting rather than when it went up."""
    assert "1h" not in FRESHNESS_WINDOWS
    assert set(FRESHNESS_WINDOWS) == {"1d", "7d", "14d", "30d"}
    assert max(FRESHNESS_WINDOWS.values()) == MAX_AGE_DAYS


def test_the_two_spellings_of_sde_ii_agree() -> None:
    """Amazon posts both forms of the same req. "sde ii" was in the senior
    vocabulary and the spelled-out title was not, so the same job read senior
    or mid depending on which way the employer abbreviated it -- an
    eighteen-point swing for a candidate whose level sat one rung away."""
    assert infer_seniority("SDE II") == infer_seniority("Software Development Engineer II")


def test_a_generic_engineer_ii_is_still_mid() -> None:
    """Only Amazon's ladder puts II that high; elsewhere it is a mid rung,
    and widening the rule to every "II" would relabel much of the pool."""
    assert infer_seniority("Software Engineer II") == "mid"
