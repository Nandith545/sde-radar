# Working on SDE Radar

This is the practical guide to making a change to this project — for you in
six months, or for anyone you hand the repo to. The short version:

> Never commit straight to `main`. Branch → commit → PR → CI green → merge.

That one rule is what makes the history readable and gives you a safety net,
because `main` is what deploys to production.

---

## First-time setup

```bash
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>

# Backend
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt   # includes runtime deps + test/lint tooling
cp .env.example .env          # fill in DATABASE_URL; API keys are optional
alembic upgrade head          # create the schema

# Frontend (second terminal)
cd frontend
npm install

# Optional but recommended: catch formatting/secret mistakes before commit
pip install pre-commit && pre-commit install
```

Then run the two dev servers — see the "Run it locally" section of the
[README](README.md).

---

## Making a change

### 1. Branch off `main`

```bash
git checkout main
git pull                       # always start from the latest main
git checkout -b feat/company-filter
```

Branch naming — the prefix tells you at a glance what a branch was for:

| Prefix      | Use for                                    |
|-------------|--------------------------------------------|
| `feat/`     | a new feature                               |
| `fix/`      | a bug fix                                   |
| `refactor/` | restructuring with no behavior change       |
| `docs/`     | documentation only                          |
| `chore/`    | dependencies, CI, tooling                   |

### 2. Commit as you go

Write the commit message for the person reading `git log` later — which is
usually you, trying to work out why something is the way it is.

```
Add company-name filter to the dashboard

The job list gets noisy past ~100 postings and the existing search only
matched titles. This adds a company dropdown built from the current result
set, so filtering doesn't require a round trip to the server.
```

The rule of thumb: **the subject line says what, the body says why.** The
"what" is already visible in the diff; the "why" is the part that's lost
forever if you don't write it down.

### 3. Run the checks before you push

One command runs everything CI runs — finding a break in ~60 seconds at your
desk beats finding it in ~4 minutes after you've pushed:

```bash
./scripts/verify.sh
```

It picks a scratch database (Postgres if one is reachable, otherwise a
throwaway SQLite file), runs the dedup regression test, lints and builds the
frontend, boots the server, drives a real browser through the whole user
journey, and drops screenshots — desktop and phone-sized — into
`.verify-artifacts/`. Look at those: the mobile shot catches layout
regressions that are invisible in a desktop browser window.

If you'd rather run the pieces individually:

```bash
cd backend  && pytest                                   # 128 tests
cd backend  && ruff check app/ tests/                   # lint
cd backend  && ruff format app/ tests/                  # format
cd backend  && mypy                                     # type check
cd backend  && alembic check                            # migration drift
cd frontend && npm run lint && npm run build            # lint + type-check
cd frontend && BASE_URL=http://localhost:8000 npm run test:e2e
```

**If you changed `models.py`, generate a migration in the same commit:**

```bash
cd backend && alembic revision --autogenerate -m "add company filter column"
```

`alembic check` fails the build otherwise. That is deliberate — a model change
without a migration deploys perfectly and then breaks against the real
database, which is a miserable thing to debug at 1am.

### 4. Push and open a pull request

```bash
git push -u origin feat/company-filter
```

GitHub prints a link to open the PR. The
[PR template](.github/pull_request_template.md) fills in automatically —
answering its questions is what makes the change reviewable later.

### 5. Wait for CI, then merge

Every PR runs: backend tests against a real Postgres, frontend lint/build,
the Playwright end-to-end journey, and CodeQL security analysis. Merge when
it's green.

**Use "Squash and merge."** Your ten "wip" commits collapse into one clean
commit, so the history reads as one entry per change instead of a stream of
noise.

---

## The three environments

There are three places your code runs, and they exist to catch different
things:

| Where | How you get there | Database | Catches |
|-------|-------------------|----------|---------|
| **Local** (`./scripts/verify.sh`) | run it | scratch Postgres or SQLite | Broken tests, type errors, layout regressions — in about a minute |
| **Staging** (`staging` branch) | `git push origin staging` | SQLite, wiped on each deploy | Anything that only shows up in a real deployed container, on a real URL, on your actual phone |
| **Production** (`main` branch) | merge to `main`, after CI passes | Free Postgres, persistent | — |

### Promoting a change

```bash
# 1. Local check
./scripts/verify.sh

# 2. Push your branch, open a PR, let CI run
git push -u origin feat/company-filter

# 3. Try it on staging (deploys automatically, ~3-5 min)
git checkout staging && git merge feat/company-filter && git push
#    -> https://sde-radar-staging.onrender.com  (click through it, on a phone too)

# 4. Happy? Merge the PR into main. CI runs again, then production deploys.
```

Staging is deliberately ungated — it deploys on every push, because fast
feedback is the entire point of a test environment. Production is the
opposite: it only deploys after the full suite goes green.

Two things to know about staging:

- **Its data resets on every deploy and restart.** It runs on SQLite in an
  ephemeral container (Render's free tier only allows one free Postgres, and
  production has it). For a test environment this is mostly a feature — you
  always start from the clean seed pool — but don't put anything there you
  expect to still exist tomorrow.
- **It's a free instance, so it sleeps.** The first request after ~15 minutes
  of inactivity takes 30–50 seconds to wake up. That's the free tier, not
  your change being slow.

Because staging runs SQLite and production runs Postgres, staging can't catch
a Postgres-specific bug. That's what CI is for — it runs the test suite
against a real Postgres 16 on every PR.

---

## Reading the history later

This is the payoff for the discipline above — some commands worth knowing:

```bash
git log --oneline --graph         # the shape of the history
git log -p backend/app/models.py  # every change to one file, with diffs
git log -S "dedup_key"            # commits that added/removed that string
git blame backend/app/services/dedup.py   # who last touched each line, and when
```

On GitHub itself: the **Insights → Network** graph shows branches over time,
and clicking any line in a file then "View git blame" walks you back to the
PR that introduced it — including the discussion on it. That's the reason
for writing real PR descriptions: they become the explanation attached to
the code, permanently.

---

## Changing the database models

Alembic owns the schema. Change `models.py`, then generate a migration **in
the same commit**:

```bash
cd backend
alembic revision --autogenerate -m "add company filter column"
alembic upgrade head            # apply it locally
```

Read the generated file before committing it — autogenerate is good but not
infallible, particularly with column renames (which it sees as a drop plus an
add, silently destroying the data).

`alembic check` runs in CI and in `verify.sh`, so a model change without a
matching migration fails the build. That is the point: without it, the change
deploys perfectly and then breaks against the real database.

Useful commands:

```bash
alembic current                 # which revision the database is on
alembic history --verbose       # every migration, newest first
alembic downgrade -1            # undo the last one
alembic upgrade head --sql      # print the SQL instead of running it
```

That last one is worth knowing before letting a migration near production.

---

## Adding a new job board connector

The connector layer is deliberately pluggable — adding a board is one file
plus one line, with no changes to ingestion or dedup:

1. Create `backend/app/services/sources/<board>.py` exposing three things:
   - `NAME: str` — the identifier shown on source badges in the UI
   - `is_configured() -> bool` — whether required credentials are present
     (return `True` unconditionally if the board needs no key)
   - `fetch(search_terms: list[str], where: str) -> list[RawJob]`
2. Add the module to `REGISTRY` in
   `backend/app/services/sources/__init__.py`.
3. If it needs an API key, add it to `config.py`, `backend/.env.example`,
   `render.yaml`, and the README's connector table.

Wrap per-listing parsing in `try`/`except` (as the existing connectors do)
so one malformed posting can't take down a whole refresh. Dedup and the
source badges then work automatically.

---

## Secrets — the one thing not to get wrong

This is a public repo. Never commit real credentials.

- `backend/.env` is gitignored. Keep it that way.
- Real values live in **Render** (environment variables) for production, and
  in **GitHub Actions secrets** for CI.
- `.env.example` documents *which* variables exist, always with empty or
  placeholder values.

If you ever do commit a secret by accident: rotate the key immediately at
the provider. Deleting the commit is not enough — once it's been pushed to a
public repo, treat it as compromised.
