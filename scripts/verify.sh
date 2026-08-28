#!/usr/bin/env bash
#
# Runs the same checks CI runs, locally, in one command.
#
#   ./scripts/verify.sh
#
# The point is to find out something is broken in ~60 seconds at your desk
# instead of ~4 minutes after you've already pushed. If this passes, CI is
# very likely to pass too.
#
# Database: uses a scratch Postgres if one is reachable (closest to what CI
# and production run), otherwise falls back to a throwaway SQLite file so the
# script still works with zero setup. Override explicitly with:
#
#   VERIFY_DATABASE_URL=postgresql://user:pass@host:5432/scratch ./scripts/verify.sh
#
# WARNING: the dedup test DROPS AND RECREATES every table on whichever
# database this ends up using. Never point it at real data.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
REPO_ROOT="$(pwd)"

# ---- pretty output -------------------------------------------------------
if [ -t 1 ]; then
  BOLD=$'\033[1m'; GREEN=$'\033[32m'; RED=$'\033[31m'; YELLOW=$'\033[33m'; DIM=$'\033[2m'; RESET=$'\033[0m'
else
  BOLD=""; GREEN=""; RED=""; YELLOW=""; DIM=""; RESET=""
fi

STEP=0
step()  { STEP=$((STEP + 1)); printf "\n%s[%d/5] %s%s\n" "$BOLD" "$STEP" "$1" "$RESET"; }
ok()    { printf "  %s✓%s %s\n" "$GREEN" "$RESET" "$1"; }
warn()  { printf "  %s!%s %s\n" "$YELLOW" "$RESET" "$1"; }
info()  { printf "  %s%s%s\n" "$DIM" "$1" "$RESET"; }

SERVER_PID=""
cleanup() {
  local code=$?
  if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
  fi
  if [ $code -ne 0 ]; then
    printf "\n%s✗ VERIFY FAILED%s — fix the above before pushing.\n" "$RED$BOLD" "$RESET"
    if [ -f /tmp/sde-radar-verify-server.log ]; then
      printf "\n%sLast 30 lines of server log:%s\n" "$DIM" "$RESET"
      tail -30 /tmp/sde-radar-verify-server.log
    fi
  fi
}
trap cleanup EXIT

# ---- python interpreter --------------------------------------------------
if [ -x "backend/venv/bin/python" ]; then
  PY="$REPO_ROOT/backend/venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PY="$(command -v python3)"
else
  echo "No python3 found. Create the venv first: cd backend && python3 -m venv venv && pip install -r requirements.txt"
  exit 1
fi

# ---- pick a database -----------------------------------------------------
step "Selecting a scratch database"

# DB_KIND records who owns the scratch database, which decides whether this
# script is allowed to wipe it between phases:
#   pg      - a Postgres database this script created (safe to recreate)
#   sqlite  - a throwaway file this script created (safe to delete)
#   managed - supplied via VERIFY_DATABASE_URL (we never drop what we didn't make)
DB_KIND="managed"
PG_ADMIN="postgresql://sderadar:devpassword@localhost:5432/postgres"

if [ -n "${VERIFY_DATABASE_URL:-}" ]; then
  DB_URL="$VERIFY_DATABASE_URL"
  ok "Using VERIFY_DATABASE_URL from your environment"
  warn "Won't auto-reset a database this script didn't create."
else
  # Try to reach a local Postgres; start it if we have the privileges.
  if ! pg_isready -q 2>/dev/null; then
    if command -v service >/dev/null 2>&1 && [ "$(id -u)" = "0" ]; then
      service postgresql start >/dev/null 2>&1 || true
      sleep 2
    fi
  fi

  PG_SCRATCH="postgresql://sderadar:devpassword@localhost:5432/sderadar_verify"
  PG_READY=0

  if pg_isready -q 2>/dev/null && psql "$PG_ADMIN" -c "SELECT 1" >/dev/null 2>&1; then
    psql "$PG_ADMIN" -c "DROP DATABASE IF EXISTS sderadar_verify" >/dev/null 2>&1 || true
    psql "$PG_ADMIN" -c "CREATE DATABASE sderadar_verify" >/dev/null 2>&1 || true
    # Don't assume the CREATE worked -- the role may lack CREATEDB. Actually
    # connect to the scratch database before committing to the Postgres path,
    # otherwise the failure surfaces much later as a confusing stack trace.
    if psql "$PG_SCRATCH" -c "SELECT 1" >/dev/null 2>&1; then
      PG_READY=1
    fi
  fi

  if [ "$PG_READY" = "1" ]; then
    DB_URL="$PG_SCRATCH"
    DB_KIND="pg"
    ok "Using scratch Postgres (matches CI and production)"
  else
    SQLITE_FILE="$(mktemp -t sde-radar-verify-XXXXXX.db)"
    rm -f "$SQLITE_FILE"
    DB_URL="sqlite:///$SQLITE_FILE"
    DB_KIND="sqlite"
    ok "Using throwaway SQLite at $SQLITE_FILE"
    warn "No usable local Postgres — CI still runs these tests on Postgres 16."
  fi
fi

export DATABASE_URL="$DB_URL"
export JWT_SECRET="local-verify-secret-not-used-anywhere-real"

# ---- 2. backend ----------------------------------------------------------
step "Backend: import check + dedup regression test"
cd "$REPO_ROOT/backend"
"$PY" -c "from app.main import app" >/dev/null
ok "App imports cleanly"
"$PY" test_dedup.py | sed 's/^/  /'
ok "Dedup tests passed"

# ---- 3. frontend ---------------------------------------------------------
step "Frontend: lint, type-check and build"
cd "$REPO_ROOT/frontend"
if [ ! -d node_modules ]; then
  info "node_modules missing — running npm ci"
  npm ci --silent
fi
npm run lint
ok "Lint passed"
npm run build >/dev/null
ok "Type-check and production build passed"

# ---- 4. start the app ----------------------------------------------------
step "Starting the app for end-to-end testing"
cd "$REPO_ROOT/backend"

# Reset the database first. The dedup test above deliberately leaves a
# handful of synthetic rows behind; without this the end-to-end run would
# exercise that odd state instead of a realistic seeded pool. CI gets this
# for free by using a separate job (and separate database) for e2e.
case "$DB_KIND" in
  sqlite)
    rm -f "${DB_URL#sqlite:///}"
    ok "Database reset to a clean slate"
    ;;
  pg)
    psql "$PG_ADMIN" -c "DROP DATABASE IF EXISTS sderadar_verify" >/dev/null 2>&1 || true
    psql "$PG_ADMIN" -c "CREATE DATABASE sderadar_verify" >/dev/null 2>&1 || true
    ok "Database reset to a clean slate"
    ;;
  *)
    warn "Skipping reset on a database this script didn't create"
    ;;
esac

if [ -x "$REPO_ROOT/backend/venv/bin/uvicorn" ]; then
  UVICORN="$REPO_ROOT/backend/venv/bin/uvicorn"
else
  UVICORN="uvicorn"
fi

"$UVICORN" app.main:app --port 8000 > /tmp/sde-radar-verify-server.log 2>&1 &
SERVER_PID=$!

for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/api/health >/dev/null 2>&1; then
    ok "Server healthy after ${i}s (pid $SERVER_PID)"
    break
  fi
  if [ "$i" = "30" ]; then
    echo "Server failed to become healthy within 30s."
    exit 1
  fi
  sleep 1
done

info "Active job-board connectors: $(curl -s http://localhost:8000/api/sources)"

# ---- 5. end-to-end -------------------------------------------------------
step "End-to-end: driving a real browser through the full user journey"
cd "$REPO_ROOT/frontend"

# This sandbox ships Chromium at a fixed path; elsewhere Playwright finds
# its own (run `npx playwright install chromium` once if it complains).
if [ -x /opt/pw-browsers/chromium ]; then
  export PLAYWRIGHT_CHROMIUM_PATH=/opt/pw-browsers/chromium
fi

BASE_URL=http://localhost:8000 npm run test:e2e 2>&1 | sed 's/^/  /'

if [ "${SCREENSHOTS:-1}" = "1" ]; then
  mkdir -p "$REPO_ROOT/.verify-artifacts"
  if BASE_URL=http://localhost:8000 \
     OUT_DIR="$REPO_ROOT/.verify-artifacts" \
     node tests/screenshot.mjs > /tmp/sde-radar-verify-shots.log 2>&1; then
    ok "Screenshots written to .verify-artifacts/"
  else
    warn "Screenshot capture failed (not fatal) — reason:"
    tail -5 /tmp/sde-radar-verify-shots.log | sed 's/^/      /'
  fi
fi

printf "\n%s✓ ALL CHECKS PASSED%s — safe to push.\n" "$GREEN$BOLD" "$RESET"
printf "%sNext: git push, then verify on staging before merging to main.%s\n\n" "$DIM" "$RESET"
