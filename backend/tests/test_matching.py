"""The scoring heuristic. These tests pin the *behaviour* users see —
ordering, flags, and explanations — rather than exact point values, so
tuning the weights doesn't produce a wall of false failures.
"""

from app import models
from app.services.matching import score_job


def _user(**overrides) -> models.User:
    fields = {
        "email": "u@example.com",
        "full_name": "U",
        "hashed_password": "x",
        "target_city": "Seattle, WA",
        "target_titles": "Software Engineer, Backend Engineer",
    }
    fields.update(overrides)
    return models.User(**fields)


def _resume(skills: list[str], years: float | None = 8.0) -> models.Resume:
    return models.Resume(filename="r.txt", raw_text="", skills=skills, years_experience=years)


def test_more_skill_overlap_scores_higher(make_job) -> None:
    user = _user()
    resume = _resume(["Java", "Python", "AWS"])

    strong = score_job(make_job(skills=["Java", "Python", "AWS"]), user, resume)
    weak = score_job(make_job(skills=["COBOL", "Fortran", "Delphi"]), user, resume)

    assert strong.score > weak.score


def test_score_is_always_within_bounds(make_job) -> None:
    user = _user()
    resume = _resume(["Java"] * 30)
    # A deliberately extreme case: huge overlap, matching title and city.
    result = score_job(make_job(skills=["Java"] * 30), user, resume)
    assert 0 <= result.score <= 100


def test_no_resume_still_produces_a_valid_score(make_job) -> None:
    result = score_job(make_job(), _user(), None)
    assert 0 <= result.score <= 100
    assert result.reason


def test_junior_titles_are_flagged_and_penalised(make_job) -> None:
    user = _user()
    resume = _resume(["Java", "Python", "AWS"])

    senior = score_job(make_job(title="Senior Software Engineer"), user, resume)
    junior = score_job(make_job(title="Junior Software Engineer"), user, resume)

    assert junior.score < senior.score
    assert junior.flag is not None
    assert "junior" in junior.flag.lower() or "entry" in junior.flag.lower()


def test_part_time_and_contract_roles_are_flagged(make_job) -> None:
    result = score_job(make_job(job_type="Contract"), _user(), _resume(["Java"]))
    assert result.flag is not None
    assert "part-time" in result.flag.lower() or "contract" in result.flag.lower()


def test_matching_title_beats_non_matching_title(make_job) -> None:
    user = _user(target_titles="Backend Engineer")
    resume = _resume(["Java"])

    on_target = score_job(make_job(title="Backend Engineer", skills=["Java"]), user, resume)
    off_target = score_job(make_job(title="Marketing Manager", skills=["Java"]), user, resume)

    assert on_target.score > off_target.score


def test_target_city_boosts_the_score(make_job) -> None:
    user = _user(target_city="Seattle, WA")
    resume = _resume(["Java"])

    local = score_job(make_job(location="Seattle, WA", skills=["Java"]), user, resume)
    remote_city = score_job(make_job(location="Austin, TX", skills=["Java"]), user, resume)

    assert local.score > remote_city.score


def test_reason_names_the_overlapping_skills(make_job) -> None:
    result = score_job(
        make_job(skills=["Java", "Python", "AWS"]), _user(), _resume(["Java", "Python", "AWS"])
    )
    assert "Java" in result.reason


def test_reason_is_honest_when_there_is_no_overlap(make_job) -> None:
    result = score_job(make_job(title="Marketing Manager", skills=["Photoshop"]), _user(), _resume(["Java"]))
    assert result.reason
    assert "Java" not in result.reason


def test_clean_full_time_senior_role_has_no_flag(make_job) -> None:
    result = score_job(
        make_job(title="Senior Software Engineer", job_type="Full-time"), _user(), _resume(["Java"])
    )
    assert result.flag is None


# ---- Work mode and country preferences ---------------------------------


def test_matching_work_mode_scores_higher_than_mismatched(make_job) -> None:
    user = _user(work_mode="remote")
    resume = _resume(["Python"])

    remote = score_job(make_job(location="Remote (US)", skills=["Python"]), user, resume)
    onsite = score_job(make_job(location="Austin, TX — On-site", skills=["Python"]), user, resume)

    assert remote.score > onsite.score
    assert "remote" in remote.reason.lower()
    assert onsite.flag and "onsite" in onsite.flag.lower()


def test_unreadable_work_mode_is_not_penalised(make_job) -> None:
    """The point of "unknown": never hide a job for being hard to classify."""
    user_with_pref = _user(work_mode="remote")
    user_without = _user()
    resume = _resume(["Python"])
    # No remote/onsite/hybrid signal anywhere.
    job = make_job(location="Seattle, WA", title="Software Engineer", skills=["Python"])

    assert score_job(job, user_with_pref, resume).score == score_job(job, user_without, resume).score


def test_job_in_the_wrong_country_is_flagged(make_job) -> None:
    user = _user(target_country="United States", target_city="")
    resume = _resume(["Python"])

    abroad = score_job(make_job(location="Leipzig", skills=["Python"]), user, resume)

    assert abroad.flag and "germany" in abroad.flag.lower()


def test_remote_job_is_never_flagged_for_its_country(make_job) -> None:
    """A remote role isn't really "in" a country, so it shouldn't be punished
    for being listed against one."""
    user = _user(target_country="United States", target_city="")
    resume = _resume(["Python"])

    remote = score_job(make_job(location="Remote (Germany)", skills=["Python"]), user, resume)

    assert not (remote.flag and "germany" in remote.flag.lower())


def test_country_preference_ignores_unrecognised_locations(make_job) -> None:
    user_with_pref = _user(target_country="United States", target_city="")
    user_without = _user(target_city="")
    resume = _resume(["Python"])
    job = make_job(location="Atlantis", skills=["Python"])

    assert score_job(job, user_with_pref, resume).score == score_job(job, user_without, resume).score
