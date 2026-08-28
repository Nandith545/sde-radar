# CLAUDE.md

Project context for Claude Code. Keep this file current — it's loaded into
every session.

## What this is

SDE Radar: a multi-user job-tracking web app. Users register, upload a
resume, and get a scored, explained list of matching software engineering
jobs pulled from several job boards, with an application-status pipeline
(New → Saved → Applied → Interviewing → Offer / Rejected).

FastAPI + SQLAlchemy + PostgreSQL backend, React + TypeScript (Vite)
frontend, deployed to Render as a single Docker service where FastAPI serves
the built React bundle. It's a portfolio project — the repo is public and
linked from a resume, so code quality and a legible git history matter here
more than they would for a throwaway.

## Commands

```bash
./scripts/verify.sh              # everything CI runs, ~60s. Use this before pushing.

cd backend && uvicorn app.main:app --reload      # API on :8000
cd frontend && npm run dev                       # Vite dev server on :5173, proxies /api

cd backend  && python test_dedup.py              # dedup regression test
cd frontend && npm run lint && npm run build     # lint + typecheck (build = tsc -b && vite build)
```

`verify.sh` writes desktop and mobile screenshots to `.verify-artifacts/`.
Look at the mobile one after any UI change — the layout had zero responsive
breakpoints until recently and regressions there are invisible on desktop.

## Architecture notes

**Frontend builds into the backend.** `vite.config.ts` outputs to
`backend/static/`, which `main.py` mounts. One service, one origin, no CORS
problems in production.

**Job ingestion is a plugin system.** Each board is a module in
`backend/app/services/sources/` exposing exactly three things:

```python
NAME: str                                              # shown on source badges
def is_configured() -> bool                            # credentials present?
def fetch(search_terms: list[str], where: str) -> list[RawJob]
```

Register it in `REGISTRY` in that package's `__init__.py` and everything else
— orchestration, dedup, UI badges — works automatically. Wrap per-listing
parsing in try/except so one malformed posting can't kill a whole refresh.

**Cross-source dedup** (`services/dedup.py`) is two-tier: an exact match on
normalized `company|title|city`, then a fuzzy title match (difflib, 0.87)
**scoped strictly to the same normalized company** — never fuzzy-match across
companies, that's how you merge unrelated jobs.

**Merging is deliberately conservative** (`_apply_fields` in
`job_ingestion.py`). When a duplicate is found:

- title/company/location: **first seen wins**, never overwritten. Without
  this the canonical title flaps between "Senior..." and "Sr..." on every
  refresh depending on which board answered last. This was a real bug.
- comp_min/max: only filled if currently `None` — a real salary range is
  never clobbered by a blank one from a board that lacks salary data.
- description: replaced only if the new one is longer.

**`external_id` is namespaced** `f"{source}:{raw_id}"` to satisfy the unique
constraint, while the `sources` JSON column holds the full list of
`{name, external_id, url}` across every board a posting was matched on.

## Gotchas

**There are no migrations.** `Base.metadata.create_all()` runs at startup. It
creates missing *tables* but will **not** add *columns* to a table that
already exists. If you touch `models.py`, a running database won't pick up
the change — drop and recreate locally, `ALTER TABLE` by hand on Render, or
finally adopt Alembic (the right long-term answer).

**`test_dedup.py` drops and recreates every table** on whatever
`DATABASE_URL` points at. `verify.sh` handles this safely; running it
directly against a database you care about will destroy it.

**Staging runs SQLite, production runs Postgres.** Render's free tier allows
only one free Postgres per workspace. So staging can't catch a
Postgres-specific bug — CI covers that by running the suite against real
Postgres 16 on every PR.

**Skill extraction is keyword-based, not LLM-based** (`services/skills.py`).
That's deliberate: no per-user inference cost, no external AI dependency. It
will miss unusually-phrased skills. Don't "fix" this by adding an LLM call
without discussing the cost tradeoff.

## Not yet verified

Be aware these were built in a sandbox without Docker or outbound network
access, so they have never actually run:

- **The Dockerfile has never been built.** It's what Render deploys. Worth
  running `docker build -t sde-radar .` early.
- **The Jooble, Remotive and Arbeitnow connectors have never hit a live
  API.** They're coded against documented response shapes with defensive
  parsing, but field names may have drifted. Adzuna is the only connector
  with a real-world track record. Test with `POST /api/jobs/refresh` and
  watch the logs.

## Workflow

Branch → commit → PR → CI green → squash merge. Never commit to `main`
directly; it deploys to production. `staging` branch auto-deploys to the
staging site for clicking through before promoting.

Commit messages: subject says *what*, body says *why*. The diff already shows
the what; the why is what's lost otherwise.

Full detail in [CONTRIBUTING.md](CONTRIBUTING.md).

## Secrets

Public repo — never commit real credentials. `backend/.env` is gitignored;
`.env.example` documents variable *names* with empty values. Real values live
in Render (production) and GitHub Actions secrets (CI). If a key ever does
get committed, rotate it at the provider — deleting the commit is not enough.
