"""Scores a job listing against a user's parsed resume + stated preferences.

The score is a transparent, explainable heuristic (not a black box) so the
frontend can show *why* a job scored the way it did -- this mirrors how the
single-user SDE Radar prototype presented its matches.
"""

from dataclasses import dataclass

from ..models import JobListing, Resume, User
from .job_facets import infer_country, infer_work_mode, normalize_country

SENIOR_WORDS = ["senior", "staff", "principal", "lead", "l5", "l6", "sde ii", "sde2", "sde 2", "iii", "iv"]
JUNIOR_WORDS = ["junior", "jr.", "jr ", "entry level", "intern", "internship", "new grad"]
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

    if _city_matches(job.location, user.target_city):
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
    if any(w in title_l for w in PART_TIME_WORDS) or (job.job_type or "").lower() in (
        "part-time",
        "contract",
    ):
        flag_parts.append("Looks like part-time or contract work, not a full-time role.")
        score -= 10
    if any(w in title_l for w in JUNIOR_WORDS):
        flag_parts.append("Title suggests a junior/entry-level position.")
        score -= 15
    if (
        resume
        and resume.years_experience
        and resume.years_experience >= 7
        and any(w in title_l for w in JUNIOR_WORDS)
    ):
        flag_parts.append("Your resume shows senior-level experience; this posting reads entry-level.")

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
