"""Scores a job listing against a user's parsed resume + stated preferences.

The score is a transparent, explainable heuristic (not a black box) so the
frontend can show *why* a job scored the way it did -- this mirrors how the
single-user SDE Radar prototype presented its matches.
"""

from dataclasses import dataclass

from ..models import JobListing, Resume, User
from .job_facets import (
    annual_comp,
    infer_country,
    infer_seniority,
    infer_work_mode,
    normalize_country,
    seniority_distance,
    seniority_from_years,
)
from .regions import infer_subdivision, state_label

# Seniority vocabulary now lives in job_facets alongside the other inference.
# SENIOR_WORDS was declared here and never read by anything.
PART_TIME_WORDS = ["part-time", "part time", "contract", "contractor", "temporary", "gig"]


@dataclass
class MatchResult:
    score: int
    reason: str
    flag: str | None


def _city_matches(job_location: str, target_city: str) -> bool:
    if not job_location or not target_city:
        return False
    job_l = job_location.lower()
    return any(len(part) > 2 and part in job_l for part in target_city.lower().replace(",", " ").split())


def _any_city_matches(job_location: str, target_cities: list[str]) -> bool:
    """True if the posting is in any of the user's cities.

    An empty list means no location preference, which matches everything --
    the same thing an empty single city used to mean.
    """
    if not target_cities:
        return False
    return any(_city_matches(job_location, city) for city in target_cities)


def score_job(job: JobListing, user: User, resume: Resume | None) -> MatchResult:
    resume_skills = set((resume.skills if resume else []) or [])
    job_skills = set(job.skills or [])

    overlap = resume_skills & job_skills
    overlap_count = len(overlap)

    coverage = overlap_count / len(job_skills) if job_skills else 0.0

    score = coverage * 65 + min(overlap_count, 8) * 4

    title_l = (job.title or "").lower()
    target_titles = [t.strip().lower() for t in (user.target_titles or "").split(",") if t.strip()]
    title_hit = any(t in title_l for t in target_titles) if target_titles else False
    if title_hit:
        score += 12

    if _any_city_matches(job.location, user.target_cities or []):
        score += 8

    flag_parts = []

    # Work mode and country are inferred from free text, so both only ever
    # act on a confident reading. "unknown" leaves the score untouched rather
    # than penalising a posting we simply could not classify -- a job hidden
    # for being unreadable is worse than one shown without a bonus.
    mode_hit = False
    if user.work_mode:
        job_mode = infer_work_mode(job.location or "", job.title or "", job.description or "")
        if job_mode == user.work_mode:
            score += 10
            mode_hit = True
        elif job_mode != "unknown":
            score -= 12
            flag_parts.append(f"This looks {job_mode}, and you asked for {user.work_mode}.")

    if user.target_country:
        wanted = normalize_country(user.target_country)
        job_country = infer_country(job.location or "")
        # A remote role is not really "in" a country for our purposes, so it
        # is never flagged as being in the wrong one.
        if (
            job_country != "unknown"
            and wanted
            and job_country != wanted
            and infer_work_mode(job.location or "", job.title or "") != "remote"
        ):
            score -= 15
            flag_parts.append(f"This looks like it's in {job_country.title()}, not {user.target_country}.")

    # State/province, on the same terms as country: only a confident reading
    # counts, and an empty target_states means every state rather than none.
    # A posting whose subdivision cannot be read from its location string --
    # "Remote (USA)", "Unspecified", a bare ambiguous city -- is left alone.
    wanted_states = user.target_states or []
    if wanted_states and user.target_country:
        country = normalize_country(user.target_country)
        job_state = infer_subdivision(job.location or "", country)
        if job_state and infer_work_mode(job.location or "", job.title or "") != "remote":
            if job_state in wanted_states:
                score += 6
            else:
                score -= 12
                flag_parts.append(f"This is in {state_label(country, job_state)}, which you didn't select.")
    if any(w in title_l for w in PART_TIME_WORDS) or (job.job_type or "").lower() in (
        "part-time",
        "contract",
    ):
        flag_parts.append("Looks like part-time or contract work, not a full-time role.")
        score -= 10
    # Seniority used to cost every junior-titled posting a flat 15 points, for
    # everyone -- which penalised entry-level candidates for being shown the
    # jobs they actually wanted. It is now a comparison against the level the
    # user is looking for, stated in settings or, failing that, read off their
    # resume. A user with neither gets no seniority adjustment at all.
    wanted_level = user.seniority or seniority_from_years(resume.years_experience if resume else None)
    if wanted_level:
        job_level = infer_seniority(job.title or "")
        gap = seniority_distance(job_level, wanted_level)
        if gap == 0:
            score += 10
        elif gap > 0:
            # Two rungs apart (entry vs senior) is a harder miss than one.
            score -= 8 * gap
            if user.seniority:
                flag_parts.append(
                    f"This reads {job_level}-level, and you're looking for {wanted_level}-level."
                )
            else:
                years = resume.years_experience if resume else None
                flag_parts.append(
                    f"This reads {job_level}-level; your resume shows {years:g} years of experience."
                )

    # Salary is only ever applied when the posting actually publishes a range.
    # Most don't, and treating a missing range as "fails your floor" would
    # hide the majority of the board for a reason the user cannot see.
    if user.min_salary:
        pay = annual_comp(job.comp_min, job.comp_max, job.comp_unit or "year")
        if pay is not None:
            if pay >= user.min_salary:
                score += 8
            else:
                score -= 18
                flag_parts.append(f"Pays up to ${pay:,.0f}, below your ${user.min_salary:,.0f} minimum.")

    score = max(0, min(100, round(score)))

    if overlap_count:
        top = sorted(overlap)[:4]
        reason = (
            f"Overlaps on {', '.join(top)}"
            + (f" (+{overlap_count - 4} more)" if overlap_count > 4 else "")
            + "."
        )
        if title_hit:
            reason += " Title matches one of your target roles."
        if mode_hit:
            reason += f" It's {user.work_mode}, which is what you asked for."
    elif title_hit:
        reason = "Title matches one of your target roles, but no specific skill overlap was detected in the description."
    else:
        reason = "Limited overlap with your resume's listed skills."

    flag = " ".join(flag_parts) if flag_parts else None
    return MatchResult(score=score, reason=reason, flag=flag)


def preference_mismatch(job: JobListing, user: User) -> str | None:
    """Why this posting fails the user's stated preferences, or None.

    Only the preferences that are *facts about a job* are treated as
    constraints: where it is, whether it's remote, and whether it publishes
    pay below the stated floor. Seniority stays out of this deliberately --
    "senior" versus "mid" is a judgement the titles themselves are vague
    about, and an adjacent level is usually still worth seeing. It keeps
    influencing the score instead.

    Nothing here drops a listing. The caller is handed a reason so the UI can
    say what it hid and offer to show it, which is the difference between a
    filter and a disappearance.
    """
    mode = infer_work_mode(job.location or "", job.title or "", job.description or "")

    if user.work_mode and mode != "unknown" and mode != user.work_mode:
        return f"This is {mode}, and you asked for {user.work_mode}."

    # A remote role is available from anywhere, so it is exempt from the
    # location checks. If the user specifically wants onsite, the work-mode
    # check above has already excluded it.
    if mode != "remote":
        cities = user.target_cities or []
        if cities and not _any_city_matches(job.location, cities):
            where = job.location or "somewhere unstated"
            wanted = cities[0] if len(cities) == 1 else f"{', '.join(cities[:-1])} or {cities[-1]}"
            return f"This is in {where}, not {wanted}."

        if user.target_country:
            wanted = normalize_country(user.target_country)
            job_country = infer_country(job.location or "")
            if job_country != "unknown" and wanted and job_country != wanted:
                return f"This is in {job_country.title()}, not {user.target_country}."

            job_state = infer_subdivision(job.location or "", wanted)
            states = user.target_states or []
            if states and job_state and job_state not in states:
                picked = [state_label(wanted, code) for code in states]
                names = picked[0] if len(picked) == 1 else f"{', '.join(picked[:-1])} or {picked[-1]}"
                return f"This is in {state_label(wanted, job_state)}, not {names}."

    if user.min_salary:
        pay = annual_comp(job.comp_min, job.comp_max, job.comp_unit or "year")
        # An unpublished range is not a failure -- most boards omit pay.
        if pay is not None and pay < user.min_salary:
            return f"Pays up to ${pay:,.0f}, below your ${user.min_salary:,.0f} minimum."

    return None
