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
./scripts/verify.sh              # everything CI runs. Use this before pushing.

cd backend && alembic upgrade head               # apply migrations (required before first run)
cd backend && uvicorn app.main:app --reload      # API on :8000
cd frontend && npm run dev                       # Vite dev server on :5173, proxies /api

# Individual gates
cd backend  && pytest                            # 128 tests
cd backend  && ruff check app/ tests/ && ruff format app/ tests/
cd backend  && mypy
cd backend  && alembic check                     # models vs migrations drift
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

**Alembic owns the schema, not `create_all()`.** If you change `models.py`,
generate a migration in the same commit:

```bash
cd backend && alembic revision --autogenerate -m "what changed"
```

`alembic check` runs in CI and in `verify.sh`, so drift fails the build rather
than surfacing as a runtime error against a real database. The app refuses to
start if tables are missing, with a message telling you to run `upgrade head`.

**Tests use a throwaway database** — SQLite in memory by default, or whatever
`TEST_DATABASE_URL` points at (CI points it at Postgres 16). The `client`
fixture deliberately does *not* run the app's lifespan, because that would
create/seed the real database behind the dependency override.

**Staging runs SQLite, production runs Postgres.** Render's free tier allows
only one free Postgres per workspace. So staging can't catch a
Postgres-specific bug — CI covers that by running the suite against real
Postgres 16 on every PR.

**Login throttling is per-process and in-memory** (`app/rate_limit.py`).
It stops casual credential stuffing against one instance. Scale past one
replica and each keeps its own tally, so the effective limit multiplies. The
fix at that point is Redis or an edge limiter — noted, deliberately deferred.

**Skill extraction is keyword-based, not LLM-based** (`services/skills.py`).
That's deliberate: no per-user inference cost, no external AI dependency. It
will miss unusually-phrased skills. Don't "fix" this by adding an LLM call
without discussing the cost tradeoff.

## Not yet verified

Most of this was built in a sandbox without Docker or outbound network
access. Verified locally on 2026-08-27:

- **The Dockerfile builds and runs.** `docker build -t sde-radar .` produces
  a 638MB image; the container applies migrations, seeds, starts the
  scheduler, and serves the React bundle and API against Postgres 16.
- **Remotive and Arbeitnow hit their live APIs** and parse into `RawJob`
  with title/company/location/external_id populated.

Still unverified:

- **The Jooble connector has never hit a live API** — no `JOOBLE_API_KEY`
  yet, so `is_configured()` returns False and it's skipped entirely.
  Same for Adzuna (`ADZUNA_APP_ID`/`ADZUNA_APP_KEY` are empty). The respx
  tests assert both parse each provider's *documented* response shape, but
  that is not the same as the live API still returning it. Once you have
  keys, test with `POST /api/jobs/refresh` and watch the logs.
- **Nothing has been deployed to Render yet.**

## Local setup gotchas

**Use Python 3.11 for the venv**, matching CI, the Dockerfile, ruff's
`target-version` and mypy. On 3.14 `psycopg2-binary==2.9.10` has no wheel
and falls back to a source build that fails without `pg_config`:

```bash
cd backend && uv venv --python 3.11 venv
uv pip install --python ./venv/bin/python -r requirements.txt -r requirements-dev.txt
```

**Node must be ≥20.19** — `vite@8.2.2` refuses to run on older 20.x. If
`node --version` reports 20.17, `/usr/local/bin/node` (from the official
.pkg installer) is shadowing a newer Homebrew node; put
`/usr/local/opt/node/bin` first on `PATH`.

**A local Postgres is needed for `alembic check`** — it's the one gate that
can't run against SQLite:

```bash
docker run -d --name sde-radar-pg -e POSTGRES_USER=sderadar \
  -e POSTGRES_PASSWORD=<the one in backend/.env> \
  -e POSTGRES_DB=sderadar -p 5432:5432 postgres:16
```

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
