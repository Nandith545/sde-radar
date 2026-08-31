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
cd backend  && pytest                            # 348 tests
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

**Filtering by board matches every board a posting was seen on**, not
`job.source`. `GET /api/jobs?source=<board>` and the `/boards/:source` page
it backs both test membership of the `sources` list, because dedup merges one
req across boards — keying off `source` (the board that happened to find it
first) would drop the posting from whichever board answered second. There is
a test that fails if someone "simplifies" it back.

`GET /api/jobs/sources` drives the board dropdown and is derived from the job
pool, not from `REGISTRY`: it answers "which boards have something to show in
this window", where `/api/sources` answers "which connectors are configured".
The two differ in both directions — a configured board can be empty, and a
board whose credentials were removed still has its jobs in the pool. `seed` is
a valid board name for filtering even though it has no connector module; it
is the only one a fresh install has.

**Region data is bundled, not geocoded** (`services/regions.py`). Country →
state/province → city for the eight countries `_COUNTRY_ALIASES` recognises,
because a preference has to be settable *before* a job from that place has
been ingested. The live counts annotating each option come from the pool at
request time (`/api/regions/{country}`); the vocabulary itself is static.
Country slugs match `infer_country`'s exactly, so a saved preference compares
against an inferred posting with no translation layer.

Three rules there are load-bearing:

- **A city in two subdivisions resolves to neither.** Portland is in Oregon
  and Maine, Springfield in Illinois and Missouri. Picking a favourite would
  file half those postings under a state they aren't in, so a bare ambiguous
  name reports unknown — the same fail-quiet stance as work mode and country.
  A code in the string ("Portland, OR") resolves before this ever applies.
- **Two-letter tokens are only read as codes where addresses use them**
  (`has_coded_addresses`). Doing it for Germany would turn any stray "BE"
  into Berlin.
- **Cities carry aliases** (`Munich=München`, `Bengaluru=Bangalore`). Boards
  disagree about which name to use, and two rows for one city — with the
  count split across them — is a picker bug.

**`target_states` is cleared when `target_country` changes**, in both the API
and the picker. "WA" is Washington in the US and Western Australia in
Australia; carrying it across silently changes what the user asked for. An
empty list means *all* states, not none — that's what every existing user was
backfilled with.

**Postal codes fill the profile address; they never filter jobs.** No
connector returns one and `JobListing` has no column for one, so a
postal-code job filter could only ever match nothing. Only the US, Canada and
Australia are supported, because those are the schemes that map to a
subdivision cleanly — UK outward codes, German PLZ, Indian PINs and Dutch
ranges all cross boundaries often enough that a table would be quietly wrong
about someone's own address.

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

**Jobs older than 30 days are never shown.** `MAX_AGE_DAYS` in
`services/job_facets.py` is a ceiling, not a default -- `_matched_jobs`
clamps whatever the caller asks for. Two consequences worth knowing:

- **The bundled seed pool ages out.** Its dates are fixed, so the number of
  visible seed jobs shrinks over time and will eventually reach zero. A
  dashboard that looks empty on a fresh install with no configured
  connectors is this, not a bug. Re-date `seed_jobs.py` if you want it to
  keep demoing.
- **Test fixtures must use relative dates.** `build_job` computes `posted`
  from `date.today()`. A hardcoded date drifts past the window and starts
  failing the suite on a calendar day when nobody touched the code.

There is no "last hour" filter. Every connector truncates its timestamp to
a date (`[:10]`), so `posted` has day granularity; an hour window could only
be answered from `created_at`, which is when *we* first saw the posting
rather than when it went up.

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

- **Both environments are deployed and live** on Render, and the CI-gated
  deploy works end to end: squash merge to `main` → CI green → the Deploy
  workflow fires `RENDER_DEPLOY_HOOK` → production rebuilds.
  - production: <https://sde-radar.onrender.com> (Postgres)
  - staging: <https://sde-radar-staging.onrender.com> (SQLite, resets on
    every deploy)
- **Adzuna is configured in production** and reports active on
  `/api/sources`.

- **Greenhouse and Lever were verified live** (Stripe returns 127 jobs,
  Gopuff's Lever board parses cleanly), which the original four connectors
  never were at build time. Both are per-company: set `GREENHOUSE_COMPANIES`
  / `LEVER_COMPANIES` to comma-separated slugs. Keyless, so no quota.

Still unverified:

- **The Jooble connector has never hit a live API.** No `JOOBLE_API_KEY` is
  set, so `is_configured()` returns False and it's skipped entirely. The
  respx tests assert it parses Jooble's *documented* response shape, which
  is not the same as the live API still returning it. When you add a key,
  hit `POST /api/jobs/refresh` and watch the logs — a drifted shape yields
  zero Jooble jobs rather than an error, because per-listing parsing is
  wrapped in try/except.
- **Adzuna is configured but its live response has never been eyeballed.**
  Same failure mode: it degrades quietly rather than failing loudly.

## Green CI is not the same as a working app

The end-to-end smoke test registered a fresh account on every run and never
logged in. Login was broken in production — the API client forced
`Content-Type: application/json` onto the OAuth2 password form, so FastAPI
returned 422 and the UI showed it as a failed sign-in — and all seven checks
passed anyway, because no test ever exercised that path. Registering and
logging in are different code paths (JSON vs. form-urlencoded); covering one
says nothing about the other.

The smoke test now signs out and signs back in. When adding coverage for a
fix, check that the new test *fails* without the fix — otherwise it only
documents the bug rather than catching it.

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
