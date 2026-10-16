# ---- Stage 1: build the React frontend ----------------------------------
FROM node:26-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
# vite.config.ts outputs straight into ../backend/static
RUN npm run build

# ---- Stage 2: Python runtime ---------------------------------------------
FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini
COPY --from=frontend-build /app/backend/static ./static

# Don't run as root. If the app is ever compromised, this limits what the
# attacker inherits.
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Migrations run to completion before the server starts, so the app never
# serves traffic against a schema it doesn't match. `exec` replaces the shell
# with uvicorn so it receives SIGTERM directly and shuts down gracefully --
# without it, the shell swallows the signal and the platform hard-kills the
# container after a timeout.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
