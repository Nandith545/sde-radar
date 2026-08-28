import logging
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .config import settings
from .database import Base, engine, SessionLocal
from .routers import auth, resume, jobs
from .services.job_ingestion import seed_if_empty, refresh_from_all_sources
from .services.sources import active_sources, REGISTRY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def _refresh_job_pool():
    db = SessionLocal()
    try:
        refresh_from_all_sources(db)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
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
    CORSMiddleware, allow_origins=origins, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
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
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "static"
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa_catch_all(full_path: str):
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
