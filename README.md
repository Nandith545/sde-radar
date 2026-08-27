# SDE Radar

A multi-user job-tracking application: anyone can create an account, upload
their resume, and get a personalized, scored list of Seattle-area software
engineering jobs with an application-status pipeline (New → Saved → Applied →
Interviewing → Offer / Rejected).

Built as a full-stack showcase project:

- **Backend:** Python, FastAPI, SQLAlchemy, PostgreSQL, JWT auth (passlib/bcrypt)
- **Frontend:** React + TypeScript (Vite), React Router
- **Job data:** live listings via the [Adzuna Jobs API](https://developer.adzuna.com/) (free tier), with a bundled seed dataset so the app works immediately with zero external setup
- **Matching engine:** a transparent, explainable scoring heuristic — skill overlap between your resume and each posting, target-title and target-city bonuses, and automatic flags for junior-level or part-time/contract postings — not a black box
- **Deploy target:** [Render](https://render.com) via a single Dockerfile + `render.yaml` blueprint (one web service + one managed Postgres database)

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
      job_ingestion.py            Adzuna client + upsert logic
      seed_jobs.py                  bundled fallback job pool
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

### Using live job data instead of the seed pool

1. Sign up for a free API key at <https://developer.adzuna.com/> (a couple of
   minutes, no credit card).
2. Set `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` in your `.env` (or Render
   environment variables).
3. The app pulls fresh listings on startup and every 6 hours automatically;
   any signed-in user can also hit "Refresh jobs" in the dashboard to pull
   listings for their own target city/titles on demand.

Without these keys the app is still fully functional and demoable — it just
uses the bundled 23-posting seed pool instead of live data.

---

## Deploying to Render (the one-click path)

1. **Push this repo to your own GitHub.** From this project's root:
   ```bash
   git add -A
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/<your-username>/<your-repo>.git
   git push -u origin main
   ```
   (Create the empty repo on GitHub first — no README/license, so the push
   doesn't conflict.)

2. **In Render**, click **New → Blueprint**, connect your GitHub account, and
   pick the repo you just pushed. Render reads `render.yaml` automatically
   and provisions:
   - a free web service built from the `Dockerfile`
   - a free Postgres database, wired to the web service via `DATABASE_URL`
   - an auto-generated `JWT_SECRET`

3. Render will prompt for the two optional variables left blank in
   `render.yaml` — `ADZUNA_APP_ID` and `ADZUNA_APP_KEY`. Leave them empty to
   launch on the seed data, or paste in free Adzuna credentials for live
   listings.

4. Click **Apply**. First build takes a few minutes (it's compiling the React
   app and installing Python deps inside Docker). You'll get a public
   `https://<your-service>.onrender.com` URL — that's the link for your
   resume/portfolio and the one you'd send friends.

**Free-tier notes:** Render's free web services spin down after 15 minutes of
inactivity (the first request after a quiet period takes ~30–50s to wake back
up), and free Postgres databases expire after 30 days unless upgraded. Both
are fine for a demo/portfolio project; upgrade to a paid instance if you want
it always-warm.

---

## Known limitations / good next steps

This is a real, working v1 — not a mockup — but there's an honest list of
what a "v2" would add, worth knowing (and worth mentioning in an interview
if asked "what would you improve"):

- **No database migrations** — tables are created with `Base.metadata.create_all()` at startup rather than Alembic migrations. Fine for a fresh deploy; a schema change later would need a manual migration path.
- **No email verification / password reset flow.**
- **Adzuna's free tier has a modest monthly call quota** — the 6-hour refresh schedule and search-term list in `job_ingestion.py` are tuned to stay well under it, but heavy multi-user traffic calling `/jobs/refresh` a lot would need rate-limiting.
- **Resume parsing is keyword-based, not LLM-based** — deliberate, so the app has no per-user inference cost or external AI dependency, but it will miss skills phrased in unusual ways.
- **No "forgot password" / OAuth login** — email+password only, per the current scope.
