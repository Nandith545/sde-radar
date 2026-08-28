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
pip install -r requirements.txt
cp .env.example .env          # fill in DATABASE_URL; API keys are optional

# Frontend (second terminal)
cd frontend
npm install
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

Same things CI will run — catching them locally is faster than waiting on
a red build:

```bash
# Backend: dedup/ingestion regression test
cd backend && ./venv/bin/python test_dedup.py

# Frontend: lint + type-check + build
cd frontend && npm run lint && npm run build

# End-to-end (needs the backend running on :8000)
cd frontend && BASE_URL=http://localhost:8000 npm run test:e2e
```

⚠️ `test_dedup.py` **drops and recreates every table** on whatever
`DATABASE_URL` points at. Point it at a scratch database, never at anything
you care about.

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
it's green. Merging to `main` triggers a production deploy automatically.

**Use "Squash and merge."** Your ten "wip" commits collapse into one clean
commit on `main`, so the history reads as one entry per change instead of a
stream of noise.

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

The app calls `Base.metadata.create_all()` at startup. This is worth
understanding because it has one sharp edge:

- ✅ It **creates tables** that don't exist yet — so a fresh deploy works.
- ❌ It does **not add columns** to a table that already exists.

So if you add a column to `models.py`, a database that's already running
won't get it, and you'll see errors about a missing column. Your options:

1. **Development:** just drop and recreate the local database.
2. **Production:** run the `ALTER TABLE` by hand against the Render Postgres
   instance before deploying the code that needs it.
3. **Properly:** adopt [Alembic](https://alembic.sqlalchemy.org/) for real
   migrations. This is the top item on the "next steps" list in the README,
   and the right move if this project outgrows being a portfolio piece.

Whichever you pick, note it in the PR's "Database / migration impact"
section so the deploy doesn't surprise you.

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
