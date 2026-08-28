# SDE Radar

<!-- Replace <your-username>/<your-repo> in these two URLs after you push,
     and the badges will show live build status on the repo home page. -->
[![CI](https://github.com/<your-username>/<your-repo>/actions/workflows/ci.yml/badge.svg)](https://github.com/<your-username>/<your-repo>/actions/workflows/ci.yml)
[![Security](https://github.com/<your-username>/<your-repo>/actions/workflows/security.yml/badge.svg)](https://github.com/<your-username>/<your-repo>/actions/workflows/security.yml)

A multi-user job-tracking application: anyone can create an account, upload
their resume, and get a personalized, scored list of Seattle-area software
engineering jobs with an application-status pipeline (New → Saved → Applied →
Interviewing → Offer / Rejected).

Built as a full-stack showcase project:

- **Backend:** Python, FastAPI, SQLAlchemy, PostgreSQL, JWT auth (passlib/bcrypt)
- **Frontend:** React + TypeScript (Vite), React Router
- **Job data:** live listings from four independent job-board connectors — [Adzuna](https://developer.adzuna.com/), [Jooble](https://jooble.org/api/about), [Remotive](https://remotive.com/), and [Arbeitnow](https://www.arbeitnow.com/) — merged into one pool with cross-source deduplication, plus a bundled seed dataset so the app works immediately with zero external setup
- **Matching engine:** a transparent, explainable scoring heuristic — skill overlap between your resume and each posting, target-title and target-city bonuses, and automatic flags for junior-level or part-time/contract postings — not a black box
- **Deploy target:** [Render](https://render.com) via a single Dockerfile + `render.yaml` blueprint (one web service + one managed Postgres database)
- **CI/CD:** GitHub Actions — tests, lint, type-check and a real-browser end-to-end run on every pull request; CodeQL security analysis; production deploys gated on a green build

---

## How matching works

On upload, your resume (PDF or text) is scanned against a ~50-term technical
skills taxonomy (`backend/app/services/skills.py`) to build your skill
profile, plus a best-effort "years of experience" extraction. Each job
posting is tagged the same way from its title + description. The match score
is:

```
score = (skill overlap coverage × 65) + (min(overlap count, 8) × 4)
        + 12 if the title matches one of your target titles
        + 8  if the location matches your target city
        − 10 if it looks part-time/contract
        − 15 if the title reads junior/entry-level
```

clamped to 0–100. The "why it matches" text and any caution flags are
generated from the same signals, so nothing is hidden.

---

## Project layout

```
backend/
  app/
    main.py              FastAPI app, CORS, static frontend mount, scheduler
    config.py             Environment-driven settings
    database.py            SQLAlchemy engine/session
    models.py               User, Resume, JobListing, UserJobMatch
    schemas.py                Pydantic request/response models
    security.py               Password hashing + JWT
    deps.py                    get_current_user dependency
    routers/
      auth.py                  register / login / me
      resume.py                 upload + fetch resume
      jobs.py                    list/patch matched jobs, manual refresh
    services/
      skills.py                 skills taxonomy + extraction
      resume_parser.py           PDF/text → skills + years of experience
      matching.py                 the scoring engine
      job_ingestion.py            orchestrates all connectors + upsert logic
      dedup.py                     cross-source duplicate detection
      seed_jobs.py                  bundled fallback job pool
      sources/
        base.py                      RawJob shape + connector protocol
        adzuna.py, jooble.py,         one module per job board
        remotive.py, arbeitnow.py
        salary_parse.py              free-text salary → structured range
  requirements.txt
frontend/
  src/
    api.ts                 typed fetch client
    context/AuthContext.tsx
    pages/ (Login, Register, Dashboard)
    components/ (JobCard, ResumeUpload)
    styles.css
  vite.config.ts            builds straight into ../backend/static
Dockerfile                  multi-stage: build frontend, then Python runtime
render.yaml                 Render blueprint (web service + Postgres)
```

---

## Run it locally

**Backend** (needs Python 3.11+ and a Postgres database, or nothing — it
falls back to a local SQLite file if `DATABASE_URL` is unset):

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # edit if you're using Postgres locally
uvicorn app.main:app --reload
```

**Frontend** (in a second terminal — the Vite dev server proxies `/api` to
`localhost:8000`):

```bash
cd frontend
npm install
npm run dev
```

Open the printed `localhost:5173` URL. Register an account, upload a resume
(a plain-text or text-based PDF), and the dashboard will populate from the
bundled seed job pool immediately.

### Job board connectors + deduplication

The app pulls from four independent job boards and merges the results into
one shared pool:

| Connector  | Needs an API key?                                          |
|------------|-------------------------------------------------------------|
| Adzuna     | Yes — free at <https://developer.adzuna.com/>               |
| Jooble     | Yes — free at <https://jooble.org/api/about>                 |
| Remotive   | No — always on                                               |
| Arbeitnow  | No — always on                                               |

1. To enable Adzuna and/or Jooble, set `ADZUNA_APP_ID` + `ADZUNA_APP_KEY`
   and/or `JOOBLE_API_KEY` in your `.env` (or Render environment variables).
   Each connector is independent — enable one, some, or all of them.
2. The app pulls fresh listings from every configured connector on startup
   and every 6 hours automatically; any signed-in user can also hit "Refresh
   jobs" in the dashboard to pull listings for their own target city/titles
   on demand. `GET /api/sources` reports which connectors are currently
   active, and the dashboard shows the same thing as a status strip.
3. **The same real posting often appears on more than one board** — the
   ingestion pipeline (`job_ingestion.py` + `dedup.py`) catches this two
   ways: an exact match on normalized company + title + city, and a fuzzy
   title match (via `difflib`, scoped strictly to the same normalized
   company so it never merges different companies) for wording differences
   like "Sr. Software Engineer" vs "Senior Software Engineer". Matched
   postings collapse into a single card, which lists every board it was
   found on and keeps the best available data from each (e.g. a real salary
   range from one source isn't overwritten by a blank one from another).

Without any keys configured, the app still runs fully on Remotive +
Arbeitnow (no setup needed) plus the bundled 23-posting seed pool.

**Honest caveat:** the Jooble, Remotive, and Arbeitnow connectors are built
against each provider's documented/public API shape, but weren't
live-verified against real traffic while building this (the dev sandbox
used had no outbound network access to third-party APIs). Every connector
wraps its parsing in a per-item try/except so one unexpected field can't take
down a whole refresh — check your Render logs after the first live deploy
with real credentials, and open an issue/adjust the relevant `sources/*.py`
file if a field name has drifted from what's coded.

---

## Putting it on GitHub

```bash
# Create an EMPTY repo on GitHub first (no README, no .gitignore, no
# license) so the first push doesn't conflict. Then:
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

The CI pipeline starts running on that first push — check the **Actions**
tab. Then two settings worth doing once, in the repo's **Settings**:

- **Branches → Add branch protection rule** for `main`: require a pull
  request, and require the `Backend tests`, `Frontend lint & build` and
  `End-to-end (Playwright)` status checks to pass. This is what makes the
  workflow in [CONTRIBUTING.md](CONTRIBUTING.md) enforced rather than
  merely suggested — it stops you pushing a broken `main` at 1am.
- Update the two badge URLs at the top of this README with your username
  and repo name.

For day-to-day work after that — branching, commit messages, PRs, reading
the history back later — see **[CONTRIBUTING.md](CONTRIBUTING.md)**.

---

## Deploying to Render

1. **In Render**, click **New → Blueprint**, connect your GitHub account, and
   pick the repo you just pushed. Render reads `render.yaml` automatically
   and provisions:
   - a free web service built from the `Dockerfile`
   - a free Postgres database, wired to the web service via `DATABASE_URL`
   - an auto-generated `JWT_SECRET`

2. Render will prompt for the optional variables left blank in
   `render.yaml` — `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`, and `JOOBLE_API_KEY`.
   Leave them empty to launch on Remotive + Arbeitnow + the seed pool, or
   paste in free credentials for Adzuna and/or Jooble for broader live
   coverage.

3. Click **Apply**. First build takes a few minutes (it's compiling the React
   app and installing Python deps inside Docker). You'll get a public
   `https://<your-service>.onrender.com` URL — that's the link for your
   resume/portfolio and the one you'd send friends.

4. **Wire up the CI-gated deploy** (one time). `render.yaml` sets
   `autoDeploy: false`, so Render won't deploy on push by itself — GitHub
   Actions triggers it only after CI passes:
   - In Render: **your service → Settings → Deploy Hook**, copy the URL.
   - In GitHub: **Settings → Secrets and variables → Actions → New
     repository secret**, name it `RENDER_DEPLOY_HOOK`, paste the URL.

   Until that secret exists the deploy job fails with a clear message and
   nothing else breaks — CI still runs, you just deploy from Render's
   dashboard manually.

**Free-tier notes:** Render's free web services spin down after 15 minutes of
inactivity (the first request after a quiet period takes ~30–50s to wake back
up), and free Postgres databases expire after 30 days unless upgraded. Both
are fine for a demo/portfolio project; upgrade to a paid instance if you want
it always-warm.

---

## The pipeline

Everything under `.github/` — what runs, when, and why:

| Workflow | Triggers | What it does |
|----------|----------|--------------|
| `ci.yml` | every push to `main`, every PR | Backend dedup test against a real Postgres 16 service; frontend lint + type-check + production build; full Playwright end-to-end journey (register → upload resume → match → status change → reload → sign out) against the real stack |
| `security.yml` | pushes, PRs, weekly Monday scan | CodeQL static analysis for Python and TypeScript (results in the Security tab); `pip-audit` + `npm audit` for known CVEs in dependencies |
| `deploy.yml` | after CI succeeds on `main` | Fires the Render deploy hook. Skipped automatically if CI failed |
| `dependabot.yml` | weekly / monthly | Opens grouped dependency-update PRs for pip, npm, GitHub Actions and Docker — each one runs through the same CI before you merge it |

A few deliberate choices worth knowing:

- **The end-to-end test runs against the real stack**, not mocks — real
  Postgres, real FastAPI, real built React bundle, real Chromium. It's the
  slowest job and the one most likely to catch an actual regression.
- **The dependency audit doesn't fail the build.** A new advisory in a
  transitive dependency shouldn't block an unrelated hotfix at 2am;
  Dependabot opens the fix PR instead.
- **Deploys are gated, not automatic.** `main` only reaches production
  after the whole suite is green.

---

## Testing

There's no full pytest suite (noted below as a good next step), but two
scripts exist and are worth running after any change to matching or
ingestion:

- **`backend/test_dedup.py`** — regression test for cross-source
  deduplication. Feeds synthetic multi-board postings straight into the
  ingestion pipeline and asserts duplicates collapse into one row with a
  merged source list. Run with `./venv/bin/python test_dedup.py` (drops and
  recreates every table on whatever `DATABASE_URL` is configured — point it
  at a disposable dev database).
- **`frontend/tests/smoke.mjs`** — Playwright end-to-end test covering the
  full user journey (register → upload resume → see matches → change
  status → reload → status persists → sign out) against a running instance.
  See the comment at the top of the file for exact usage.

---

## Known limitations / good next steps

This is a real, working v1 — not a mockup — but there's an honest list of
what a "v2" would add, worth knowing (and worth mentioning in an interview
if asked "what would you improve"):

- **No database migrations** — tables are created with `Base.metadata.create_all()` at startup rather than Alembic migrations. Fine for a fresh deploy; a schema change later would need a manual migration path.
- **No email verification / password reset flow.**
- **Adzuna's free tier has a modest monthly call quota** — the 6-hour refresh schedule and search-term list in `job_ingestion.py` are tuned to stay well under it, but heavy multi-user traffic calling `/jobs/refresh` a lot would need rate-limiting.
- **Jooble/Remotive/Arbeitnow connectors weren't live-verified** during development (no outbound network access in the build sandbox) — they're built against each provider's documented API shape with defensive per-item parsing, but are worth a log check after your first live deploy.
- **Dedup is heuristic, not perfect** — exact-key + same-company fuzzy title matching catches the common cases (identical postings, minor wording differences) but won't catch a posting reworded enough to fall below the similarity threshold, and in rare cases could theoretically merge two genuinely different roles at the same company with near-identical titles and locations.
- **Resume parsing is keyword-based, not LLM-based** — deliberate, so the app has no per-user inference cost or external AI dependency, but it will miss skills phrased in unusual ways.
- **No "forgot password" / OAuth login** — email+password only, per the current scope.
- **No automated pytest/CI suite** — the two scripts under [Testing](#testing) above cover the highest-risk logic (dedup, the full user journey) but aren't wired into a CI pipeline yet.
