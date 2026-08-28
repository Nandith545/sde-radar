## What changed

<!-- One or two sentences. What does this PR do, in plain language? -->

## Why

<!-- The reason for the change: the bug it fixes, the feature it adds, the
     problem it solves. Future-you reading `git log` in six months will
     thank present-you for writing this down. -->

## How to test it

<!-- Steps a reviewer (or you, later) can follow to confirm it works.
     e.g. "Sign in, hit Refresh jobs, confirm no duplicate cards appear." -->

## Checklist

- [ ] CI is green (backend tests, frontend lint/build, end-to-end)
- [ ] I ran the app locally and clicked through the change
- [ ] If I changed the database models, I noted the migration impact below
- [ ] If I added a new config/env var, I added it to `backend/.env.example`,
      `render.yaml`, and the README

## Database / migration impact

<!-- The app uses `Base.metadata.create_all()`, which creates missing TABLES
     but will NOT add new COLUMNS to a table that already exists. If you
     added or changed a column, say so here and note what has to happen on
     the deployed database (usually a manual `ALTER TABLE`). Delete this
     section if your change doesn't touch models.py. -->

N/A

## Screenshots

<!-- For any UI change, before/after screenshots. Delete if not applicable. -->
