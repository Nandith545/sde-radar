import logging
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect
from starlette.responses import Response

from .config import settings, validate_for_production
from .database import Base, SessionLocal, engine
from .routers import auth, jobs, resume
from .services.job_ingestion import refresh_from_all_sources, seed_if_empty
from .services.sources import REGISTRY, active_sources

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def _refresh_job_pool():
    db = SessionLocal()
    try:
        refresh_from_all_sources(db)
    finally:
        db.close()


def _assert_schema_ready() -> None:
    """Fails fast with an actionable message if migrations haven't been run.

    Much better than the app booting and then throwing "relation does not
    exist" on the first request, which sends you looking in the wrong place.
    """
    inspector = inspect(engine)
    missing = set(Base.metadata.tables) - set(inspector.get_table_names())
    if missing:
        raise RuntimeError(
            f"Database schema is not up to date (missing tables: {', '.join(sorted(missing))}). "
            "Run 'alembic upgrade head' from the backend directory."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Refuse to start a production deploy that's misconfigured, rather than
    # coming up quietly insecure. A crash-looping service in the Render logs
    # with a clear reason is far better than one silently signing tokens with
    # a secret that's published in a public repo.
    if settings.is_production:
        problems = validate_for_production()
        if problems:
            for problem in problems:
                logger.critical("Refusing to start: %s", problem)
            raise RuntimeError("Production configuration is invalid: " + " | ".join(problems))

    # Schema is owned by Alembic, not create_all(). create_all creates missing
    # tables but silently will NOT add columns to tables that already exist,
    # which is how a schema change passes local testing and then breaks a
    # deployed database. Migrations run before the app starts -- see the
    # Dockerfile entrypoint and `alembic upgrade head` in the docs.
    _assert_schema_ready()

    db = SessionLocal()
    try:
        seeded = seed_if_empty(db)
        if seeded:
            logger.info("Seeded job pool with %d bundled listings.", seeded)
    finally:
        db.close()

    sources = active_sources()
    if sources:
        scheduler.add_job(_refresh_job_pool, "interval", hours=6, id="job_refresh", replace_existing=True)
        scheduler.start()
        logger.info("Live refresh scheduled every 6 hours. Active connectors: %s", ", ".join(sources))
    else:
        logger.info("No job-board connectors configured — running on the bundled seed job pool only.")

    yield

    if scheduler.running:
        scheduler.shutdown()


app = FastAPI(title="SDE Radar", lifespan=lifespan)

origins = ["*"] if settings.cors_origins == "*" else [o.strip() for o in settings.cors_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SECURITY_HEADERS = {
    # Don't let a browser second-guess a declared content type.
    "X-Content-Type-Options": "nosniff",
    # This app is never meant to be embedded in someone else's page.
    "X-Frame-Options": "DENY",
    # Don't leak the full URL (which can carry job ids) to outbound job links.
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}


@app.middleware("http")
async def add_security_headers(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    response = await call_next(request)
    for header, value in SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    if settings.is_production:
        # Only in production: sending HSTS from a local http:// dev server
        # pins the browser to https for localhost and is a nuisance to undo.
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Logs the real error, returns an opaque one.

    Stack traces and driver messages can carry table names, query fragments
    and connection strings; none of that belongs in an HTTP response.
    """
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong on our end. Please try again."},
    )


app.include_router(auth.router)
app.include_router(resume.router)
app.include_router(jobs.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/sources")
def sources_status():
    active = set(active_sources())
    return [{"name": mod.NAME, "active": mod.NAME in active} for mod in REGISTRY]


# ---- Serve the built React frontend (single-service deploy) ----------
def safe_static_file(root: Path, url_path: str) -> Path | None:
    """Resolve a URL path to a file *inside* `root`, or None.

    The SPA catch-all takes its path straight from the URL, so a naive
    `root / url_path` resolves "%2e%2e/%2e%2e/.env" (Starlette percent-decodes
    before this sees it) to a real file outside the bundle -- which served
    source, config, and the JWT secret. Resolving the candidate and confirming
    containment closes that: a traversal escapes `root`, fails the
    `is_relative_to` check, and returns None so the caller serves index.html.
    """
    if not url_path:
        return None
    root = root.resolve()
    candidate = (root / url_path).resolve()
    if candidate.is_relative_to(root) and candidate.is_file():
        return candidate
    return None


FRONTEND_DIST = Path(__file__).resolve().parent.parent / "static"
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa_catch_all(full_path: str):
        served = safe_static_file(FRONTEND_DIST, full_path)
        if served is not None:
            return FileResponse(served)
        # Real client-side routes like "/settings" have no file and correctly
        # fall through to the SPA entrypoint.
        return FileResponse(FRONTEND_DIST / "index.html")
