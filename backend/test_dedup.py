"""Regression test for cross-source dedup + multi-board ingestion.

Not wired into a pytest suite (no test infra exists for this project yet) --
run directly with the venv interpreter against a scratch/dev database:

    ./venv/bin/python test_dedup.py

It feeds synthetic RawJob fixtures -- deliberately including near-duplicate
postings across different fake sources -- straight into _ingest_raw_jobs()
and asserts the pool ends up with the expected number of *canonical* rows,
each with the right merged `sources` list. This exercises the exact
behavior the job-board-connectors feature is for: pulling from multiple
boards without showing the user the same posting twice.

WARNING: this drops and recreates every table on whatever DATABASE_URL is
configured (via .env / the environment) -- point it at a disposable dev
database, never at anything with real data.
"""
import sys

from app.database import Base, engine, SessionLocal
from app.services.job_ingestion import _ingest_raw_jobs
from app.services.sources.base import RawJob
from app import models

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

db = SessionLocal()

failures = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        failures.append(label)


# ---------------------------------------------------------------------
# Round 1: three postings.
#   A) Same job, same company, exact same title/location, on adzuna + jooble
#      with different external ids -> should collapse to ONE row.
#   B) Same job, slightly different title wording ("Sr." vs "Senior") on
#      remotive -> should fuzzy-match into the SAME row as (A).
#   C) A genuinely different job at a different company -> its own row.
# ---------------------------------------------------------------------
batch1 = [
    RawJob(
        source="adzuna", external_id="adz-1001", title="Senior Software Engineer",
        company="Acme Corp", location="Seattle, WA",
        description="Build distributed systems at Acme.", comp_min=140000, comp_max=180000,
        comp_unit="year", job_type="Full-time", posted="2026-08-20", url="https://adzuna.example/1001",
    ),
    RawJob(
        source="jooble", external_id="joo-77", title="Senior Software Engineer",
        company="Acme Corp", location="Seattle, WA",
        description="Build distributed systems at Acme, on the platform team.",
        comp_min=None, comp_max=None, comp_unit="year", job_type="Full-time",
        posted="2026-08-22", url="https://jooble.example/77",
    ),
    RawJob(
        source="remotive", external_id="rem-42", title="Sr. Software Engineer",
        company="Acme Corp", location="Seattle, WA",
        description="Short blurb.", comp_min=None, comp_max=None, comp_unit="year",
        job_type="Full-time", posted="2026-08-18", url="https://remotive.example/42",
    ),
    RawJob(
        source="arbeitnow", external_id="arb-9", title="Data Engineer",
        company="Globex Inc", location="Seattle, WA",
        description="Own the data pipeline.", comp_min=120000, comp_max=150000,
        comp_unit="year", job_type="Full-time", posted="2026-08-19", url="https://arbeitnow.example/9",
    ),
]

result1 = _ingest_raw_jobs(db, batch1)
print("Round 1 result:", result1)

jobs = db.query(models.JobListing).all()
check("Round 1 collapses 4 raw postings into 2 canonical rows", len(jobs) == 2)

acme = next((j for j in jobs if j.company == "Acme Corp"), None)
globex = next((j for j in jobs if j.company == "Globex Inc"), None)

check("Acme row exists", acme is not None)
check("Globex row exists", globex is not None)

if acme:
    source_names = sorted(e["name"] for e in acme.sources)
    check(
        f"Acme row merged all 3 sources (got {source_names})",
        source_names == ["adzuna", "jooble", "remotive"],
    )
    check("Acme row kept the real comp range from adzuna (not clobbered by later blank ones)",
          acme.comp_min == 140000 and acme.comp_max == 180000)
    check("Acme row picked up the longer description from jooble",
          "platform team" in acme.description)
    check("Acme row title stayed the canonical 'Senior Software Engineer' (first-seen wins, no flapping)",
          acme.title == "Senior Software Engineer")

if globex:
    check("Globex row has exactly 1 source (arbeitnow)", [e["name"] for e in globex.sources] == ["arbeitnow"])

# ---------------------------------------------------------------------
# Round 2: re-ingest the SAME adzuna posting again (simulating the next
# scheduled refresh pulling the identical listing) -> must NOT create a
# new row or a duplicate source entry, only a same-source update.
# ---------------------------------------------------------------------
batch2 = [
    RawJob(
        source="adzuna", external_id="adz-1001", title="Senior Software Engineer",
        company="Acme Corp", location="Seattle, WA",
        description="Build distributed systems at Acme.", comp_min=140000, comp_max=180000,
        comp_unit="year", job_type="Full-time", posted="2026-08-25", url="https://adzuna.example/1001",
    ),
]
result2 = _ingest_raw_jobs(db, batch2)
print("Round 2 result:", result2)
check("Round 2 is a same-source update, not a new row or new merge",
      result2["added"] == 0 and result2["merged_into_existing"] == 0 and result2["same_source_updates"] == 1)

jobs_after = db.query(models.JobListing).all()
check("Still exactly 2 canonical rows after re-ingesting the same posting", len(jobs_after) == 2)

acme_after = next((j for j in jobs_after if j.company == "Acme Corp"), None)
if acme_after:
    check("Re-ingest didn't duplicate the adzuna source entry",
          sum(1 for e in acme_after.sources if e["name"] == "adzuna") == 1)
    check("Re-ingest picked up the newer 'posted' date", acme_after.posted == "2026-08-25")

# ---------------------------------------------------------------------
# Round 3: a job at a DIFFERENT company with a similar-sounding title should
# NOT fuzzy-merge across companies (fuzzy match must stay scoped to the same
# normalized company).
# ---------------------------------------------------------------------
batch3 = [
    RawJob(
        source="jooble", external_id="joo-999", title="Sr. Software Engineer",
        company="Initech LLC", location="Seattle, WA",
        description="Different company, similar title.", comp_min=None, comp_max=None,
        comp_unit="year", job_type="Full-time", posted="2026-08-21", url="https://jooble.example/999",
    ),
]
result3 = _ingest_raw_jobs(db, batch3)
print("Round 3 result:", result3)
check("Different-company similar-title posting creates a NEW row (no cross-company fuzzy match)",
      result3["added"] == 1 and result3["merged_into_existing"] == 0)

jobs_final = db.query(models.JobListing).all()
check("3 canonical rows total after round 3", len(jobs_final) == 3)

db.close()

print()
if failures:
    print(f"{len(failures)} CHECK(S) FAILED:")
    for f in failures:
        print(" -", f)
    sys.exit(1)
else:
    print("All checks passed.")
