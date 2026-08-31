"""The scoring heuristic. These tests pin the *behaviour* users see —
ordering, flags, and explanations — rather than exact point values, so
tuning the weights doesn't produce a wall of false failures.
"""

from app import models
from app.services.matching import preference_mismatch, score_job


def _user(**overrides) -> models.User:
    fields = {
        "email": "u@example.com",
        "full_name": "U",
        "hashed_password": "x",
        "target_cities": ["Seattle, WA"],
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
    user = _user(target_cities=["Seattle, WA"])
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
    user = _user(target_country="United States", target_cities=[])
    resume = _resume(["Python"])

    abroad = score_job(make_job(location="Leipzig", skills=["Python"]), user, resume)

    assert abroad.flag and "germany" in abroad.flag.lower()


def test_remote_job_is_never_flagged_for_its_country(make_job) -> None:
    """A remote role isn't really "in" a country, so it shouldn't be punished
    for being listed against one."""
    user = _user(target_country="United States", target_cities=[])
    resume = _resume(["Python"])

    remote = score_job(make_job(location="Remote (Germany)", skills=["Python"]), user, resume)

    assert not (remote.flag and "germany" in remote.flag.lower())


def test_country_preference_ignores_unrecognised_locations(make_job) -> None:
    user_with_pref = _user(target_country="United States", target_cities=[])
    user_without = _user(target_cities=[])
    resume = _resume(["Python"])
    job = make_job(location="Atlantis", skills=["Python"])

    assert score_job(job, user_with_pref, resume).score == score_job(job, user_without, resume).score


# ---- Seniority ---------------------------------------------------------


def test_entry_level_candidate_is_not_punished_for_entry_level_jobs(make_job) -> None:
    """The behaviour this replaced: a flat penalty on every junior title meant
    a new grad was scored down on exactly the roles they should be shown."""
    grad = _user(seniority="entry")
    resume = _resume(["Python"], years=0.5)

    junior = score_job(make_job(title="Junior Software Engineer", skills=["Python"]), grad, resume)
    staff = score_job(make_job(title="Staff Software Engineer", skills=["Python"]), grad, resume)

    assert junior.score > staff.score
    assert junior.flag is None or "entry" not in junior.flag.lower()


def test_stated_preference_beats_resume_derived_one(make_job) -> None:
    """Someone stepping down a level should be able to say so."""
    resume = _resume(["Python"], years=12.0)
    by_resume = _user()
    by_choice = _user(seniority="entry")
    job = make_job(title="Junior Software Engineer", skills=["Python"])

    assert score_job(job, by_choice, resume).score > score_job(job, by_resume, resume).score


def test_seniority_gap_is_proportional(make_job) -> None:
    user = _user(seniority="senior")
    resume = _resume(["Python"])

    senior = score_job(make_job(title="Senior Engineer", skills=["Python"]), user, resume)
    mid = score_job(make_job(title="Software Engineer", skills=["Python"]), user, resume)
    entry = score_job(make_job(title="Junior Engineer", skills=["Python"]), user, resume)

    assert senior.score > mid.score > entry.score


def test_no_preference_and_no_resume_means_no_seniority_adjustment(make_job) -> None:
    user = _user()
    junior = score_job(make_job(title="Junior Engineer", skills=["Python"]), user, None)
    senior = score_job(make_job(title="Senior Engineer", skills=["Python"]), user, None)
    assert junior.score == senior.score


# ---- Salary floor ------------------------------------------------------


def test_jobs_below_the_salary_floor_are_flagged(make_job) -> None:
    user = _user(min_salary=180000)
    resume = _resume(["Python"])

    low = score_job(make_job(comp_min=90000, comp_max=110000, skills=["Python"]), user, resume)

    assert low.flag is not None and "below your" in low.flag.lower()


def test_jobs_above_the_salary_floor_score_higher(make_job) -> None:
    user = _user(min_salary=180000)
    resume = _resume(["Python"])

    high = score_job(make_job(comp_min=200000, comp_max=250000, skills=["Python"]), user, resume)
    low = score_job(make_job(comp_min=90000, comp_max=110000, skills=["Python"]), user, resume)

    assert high.score > low.score


def test_a_job_with_no_published_salary_is_not_penalised(make_job) -> None:
    """Most postings omit pay. Treating that as failing the floor would hide
    most of the board for a reason the user can never see."""
    with_floor = _user(min_salary=180000)
    without = _user()
    resume = _resume(["Python"])
    job = make_job(comp_min=None, comp_max=None, skills=["Python"])

    assert score_job(job, with_floor, resume).score == score_job(job, without, resume).score


def test_hourly_pay_is_annualised_before_comparison(make_job) -> None:
    user = _user(min_salary=180000)
    resume = _resume(["Python"])

    # $100/hr is ~$208k a year, comfortably over the floor.
    hourly = score_job(make_job(comp_min=90, comp_max=100, comp_unit="hour", skills=["Python"]), user, resume)

    assert not (hourly.flag and "below your" in hourly.flag.lower())


# ---- Preference filtering ----------------------------------------------


def test_a_job_in_another_city_does_not_match(make_job) -> None:
    user = _user(target_cities=["Seattle, WA"])
    assert preference_mismatch(make_job(location="Austin, TX"), user) is not None


def test_a_job_in_the_target_city_matches(make_job) -> None:
    user = _user(target_cities=["Seattle, WA"])
    assert preference_mismatch(make_job(location="Seattle, WA"), user) is None


def test_remote_jobs_survive_a_city_filter(make_job) -> None:
    """A remote role is available from anywhere, so filtering it out because
    it isn't literally in your city removes the jobs most worth seeing."""
    user = _user(target_cities=["Seattle, WA"])
    assert preference_mismatch(make_job(location="Remote (US)"), user) is None


def test_wanting_onsite_still_excludes_remote(make_job) -> None:
    """The remote exemption must not override an explicit onsite preference."""
    user = _user(target_cities=["Seattle, WA"], work_mode="onsite")
    assert preference_mismatch(make_job(location="Remote (US)"), user) is not None


def test_no_city_preference_filters_nothing_by_location(make_job) -> None:
    user = _user(target_cities=[])
    assert preference_mismatch(make_job(location="Austin, TX"), user) is None


def test_a_job_in_the_wrong_country_does_not_match(make_job) -> None:
    user = _user(target_cities=[], target_country="United States")
    assert preference_mismatch(make_job(location="Leipzig"), user) is not None


def test_an_unrecognised_country_is_not_filtered_out(make_job) -> None:
    """Same rule as scoring: never act on a location we couldn't read."""
    user = _user(target_cities=[], target_country="United States")
    assert preference_mismatch(make_job(location="Atlantis"), user) is None


def test_pay_below_the_floor_does_not_match(make_job) -> None:
    user = _user(target_cities=[], min_salary=180000)
    assert preference_mismatch(make_job(comp_min=90000, comp_max=110000), user) is not None


def test_an_unpublished_salary_range_is_not_filtered_out(make_job) -> None:
    user = _user(target_cities=[], min_salary=180000)
    assert preference_mismatch(make_job(comp_min=None, comp_max=None), user) is None


def test_seniority_is_scored_but_never_filtered(make_job) -> None:
    """Titles are vague about level, and an adjacent rung is usually still
    worth seeing -- so seniority stays out of the hard filter."""
    user = _user(target_cities=[], seniority="senior")
    assert preference_mismatch(make_job(title="Junior Software Engineer"), user) is None


def test_the_mismatch_reason_says_what_was_wrong(make_job) -> None:
    user = _user(target_cities=["Seattle, WA"])
    reason = preference_mismatch(make_job(location="Austin, TX"), user)
    assert reason and "Austin" in reason and "Seattle" in reason


def test_any_of_several_cities_counts_as_a_match(make_job) -> None:
    user = _user(target_cities=["Seattle, WA", "Bellevue, WA"])
    assert preference_mismatch(make_job(location="Bellevue, WA"), user) is None
    assert preference_mismatch(make_job(location="Seattle, WA"), user) is None
    assert preference_mismatch(make_job(location="Austin, TX"), user) is not None


def test_several_cities_still_boost_the_score(make_job) -> None:
    user = _user(target_cities=["Seattle, WA", "Bellevue, WA"])
    resume = _resume(["Python"])
    here = score_job(make_job(location="Bellevue, WA", skills=["Python"]), user, resume)
    away = score_job(make_job(location="Austin, TX", skills=["Python"]), user, resume)
    assert here.score > away.score


def test_the_mismatch_reason_lists_every_city(make_job) -> None:
    user = _user(target_cities=["Seattle, WA", "Bellevue, WA"])
    reason = preference_mismatch(make_job(location="Austin, TX"), user)
    assert reason and "Seattle" in reason and "Bellevue" in reason


def test_no_cities_means_anywhere(make_job) -> None:
    user = _user(target_cities=[])
    assert preference_mismatch(make_job(location="Anywhere At All"), user) is None


# ---- State / province preference ---------------------------------------


def test_a_job_outside_the_selected_states_is_flagged(make_job) -> None:
    user = _user(target_cities=[], target_country="United States", target_states=["WA"])
    resume = _resume(["Java", "Python"])

    result = score_job(make_job(location="Austin, TX"), user, resume)
    assert "Texas" in (result.flag or "")


def test_a_job_inside_the_selected_states_is_not_flagged(make_job) -> None:
    user = _user(target_cities=[], target_country="United States", target_states=["WA", "OR"])
    resume = _resume(["Java", "Python"])

    assert score_job(make_job(location="Seattle, WA"), user, resume).flag is None


def test_selecting_states_ranks_them_above_the_rest(make_job) -> None:
    user = _user(target_cities=[], target_country="United States", target_states=["WA"])
    resume = _resume(["Java", "Python"])

    inside = score_job(make_job(location="Seattle, WA"), user, resume)
    outside = score_job(make_job(location="Austin, TX"), user, resume)
    assert inside.score > outside.score


def test_no_states_selected_means_every_state(make_job) -> None:
    """An empty list is "all states", not "none" -- it is the default every
    existing user was backfilled with."""
    user = _user(target_cities=[], target_country="United States", target_states=[])
    resume = _resume(["Java", "Python"])

    assert score_job(make_job(location="Austin, TX"), user, resume).flag is None


def test_a_posting_whose_state_cannot_be_read_is_left_alone(make_job) -> None:
    """The same asymmetry work mode and country use: a job hidden for being
    unreadable is worse than one shown without a bonus."""
    user = _user(target_cities=[], target_country="United States", target_states=["WA"])
    resume = _resume(["Java", "Python"])

    for location in ("Remote (USA)", "Unspecified", "Portland"):
        result = score_job(make_job(location=location), user, resume)
        assert result.flag is None, location


def test_a_remote_job_is_never_wrong_for_its_state(make_job) -> None:
    user = _user(target_cities=[], target_country="United States", target_states=["WA"])
    resume = _resume(["Java", "Python"])

    result = score_job(make_job(location="Austin, TX (Remote)"), user, resume)
    assert result.flag is None


def test_states_do_nothing_without_a_country(make_job) -> None:
    """Codes are only meaningful inside a country; "WA" alone could be
    Washington or Western Australia."""
    user = _user(target_cities=[], target_country="", target_states=["WA"])
    resume = _resume(["Java", "Python"])

    assert score_job(make_job(location="Austin, TX"), user, resume).flag is None


def test_the_mismatch_reason_names_both_states(make_job) -> None:
    user = _user(target_cities=[], target_country="United States", target_states=["WA"])

    reason = preference_mismatch(make_job(location="Austin, TX"), user)
    assert reason is not None
    assert "Texas" in reason and "Washington" in reason


def test_an_unreadable_location_is_not_a_state_mismatch(make_job) -> None:
    user = _user(target_cities=[], target_country="United States", target_states=["WA"])

    assert preference_mismatch(make_job(location="Unspecified"), user) is None
