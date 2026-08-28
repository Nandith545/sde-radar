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

- [ ] `./scripts/verify.sh` passes locally
- [ ] CI is green (lint, types, tests, migration check, end-to-end)
- [ ] I ran the app locally and clicked through the change
- [ ] New behaviour has a test covering it
- [ ] If I changed the database models, the migration is in this PR
- [ ] If I added a new config/env var, I added it to `backend/.env.example`,
      `render.yaml`, and the README

## Database / migration impact

<!-- If you changed models.py, this PR must include the Alembic migration
     (`alembic revision --autogenerate -m "..."`). CI's `alembic check` will
     fail otherwise. Note anything a reviewer should watch for — especially
     column renames, which autogenerate turns into a drop plus an add and so
     silently destroy the existing data. Delete this section if your change
     doesn't touch models.py. -->

N/A

## Screenshots

<!-- For any UI change, before/after screenshots. Delete if not applicable. -->
