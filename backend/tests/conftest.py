"""Shared pytest fixtures.

Every test gets a completely fresh database. The suite runs against SQLite
in a temp file by default so it needs zero setup and runs fast; point
TEST_DATABASE_URL at a Postgres instance to exercise the same tests against
what production actually runs (CI does exactly that).
"""

import os
from collections.abc import Generator, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base, get_db
from app.main import app


@pytest.fixture()
def db_engine(tmp_path) -> Iterator:
    url = os.getenv("TEST_DATABASE_URL")
    if url:
        engine = create_engine(url, pool_pre_ping=True)
    else:
        # StaticPool + a single shared connection means the TestClient's
        # threadpool sees the same in-memory database the test does.
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def db(db_engine) -> Iterator[Session]:
    """A session for tests that exercise the service layer directly."""
    factory = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_engine) -> Iterator[TestClient]:
    """An API client wired to the test database.

    The app's real `get_db` dependency is overridden rather than monkeypatched
    so nothing global leaks between tests.
    """
    factory = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)

    def override_get_db() -> Generator[Session, None, None]:
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    # Deliberately NOT using `with TestClient(...)`: the context manager runs
    # the app's lifespan, which calls create_all() and seed_if_empty() against
    # the real module-level engine -- bypassing this override entirely. That
    # made the suite create a stray dev.db, and on a machine with DATABASE_URL
    # pointed at a real database it would seed that instead. It also starts the
    # background refresh scheduler, which tests have no use for.
    #
    # raise_server_exceptions=False so tests can assert on 500 responses
    # rather than the exception escaping into the test itself.
    test_client = TestClient(app, raise_server_exceptions=False)
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


# ---- Factories ---------------------------------------------------------

SAMPLE_RESUME_TEXT = b"""Jordan Example
Senior Software Engineer with 8 years of experience

Skills: Java, Spring Boot, Python, TypeScript, React, AWS, Kafka, Docker,
Kubernetes, PostgreSQL.
"""


@pytest.fixture()
def registered_user(client: TestClient) -> dict:
    """Registers a user and returns credentials plus an auth header."""
    payload = {
        "email": "test@example.com",
        "password": "supersecure123",
        "full_name": "Test User",
        "target_city": "Seattle, WA",
        "target_titles": "Software Engineer, Backend Engineer",
    }
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {
        **payload,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture()
def user_with_resume(client: TestClient, registered_user: dict) -> dict:
    response = client.post(
        "/api/resume",
        files={"file": ("resume.txt", SAMPLE_RESUME_TEXT, "text/plain")},
        headers=registered_user["headers"],
    )
    assert response.status_code == 200, response.text
    return registered_user


def build_job(**overrides) -> models.JobListing:
    """Builds a JobListing with sensible defaults; override what matters."""
    fields = {
        "external_id": "test:1",
        "source": "test",
        "sources": [{"name": "test", "external_id": "1", "url": ""}],
        "title": "Senior Software Engineer",
        "company": "Acme Corp",
        "location": "Seattle, WA",
        "description": "Build distributed systems in Java and Python on AWS.",
        "comp_min": 150000.0,
        "comp_max": 200000.0,
        "comp_unit": "year",
        "job_type": "Full-time",
        "posted": "2026-08-01",
        "url": "https://example.com/job/1",
        "skills": ["Java", "Python", "AWS"],
        "dedup_key": "acme|senior software engineer|seattle",
        "company_norm": "acme",
        "title_norm": "senior software engineer",
    }
    fields.update(overrides)
    return models.JobListing(**fields)


@pytest.fixture()
def make_job():
    """Factory fixture wrapping `build_job`.

    Exposed as a fixture rather than a plain import because conftest isn't an
    importable package from the test modules.
    """
    return build_job


@pytest.fixture()
def seed_jobs(db_engine) -> list[models.JobListing]:
    """Puts a small, varied job pool in the database.

    Deliberately hand-built rather than reusing the bundled SEED_JOBS, so a
    change to the shipped seed data can't silently alter test expectations.
    """
    factory = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = factory()
    jobs = [
        build_job(
            external_id="test:1",
            title="Senior Software Engineer",
            company="Acme Corp",
            location="Seattle, WA",
            skills=["Java", "Python", "AWS"],
            company_norm="acme",
            title_norm="senior software engineer",
            dedup_key="acme|senior software engineer|seattle",
            sources=[{"name": "adzuna", "external_id": "1", "url": ""}],
        ),
        build_job(
            external_id="test:2",
            title="Backend Engineer",
            company="Globex",
            location="Bellevue, WA",
            skills=["Python", "PostgreSQL"],
            company_norm="globex",
            title_norm="backend engineer",
            dedup_key="globex|backend engineer|bellevue",
            sources=[{"name": "jooble", "external_id": "2", "url": ""}],
        ),
        build_job(
            external_id="test:3",
            title="Junior Frontend Developer",
            company="Initech",
            location="Austin, TX",
            skills=["JavaScript"],
            company_norm="initech",
            title_norm="junior frontend developer",
            dedup_key="initech|junior frontend developer|austin",
            sources=[{"name": "remotive", "external_id": "3", "url": ""}],
        ),
    ]
    session.add_all(jobs)
    session.commit()
    for job in jobs:
        session.refresh(job)
    session.close()
    return jobs
