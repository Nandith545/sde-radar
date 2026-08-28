"""Job listing, scoring and status-tracking endpoints."""

import datetime

from fastapi.testclient import TestClient


def test_listing_jobs_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/jobs").status_code == 401


def test_jobs_are_returned_sorted_by_descending_score(
    client: TestClient, user_with_resume: dict, seed_jobs
) -> None:
    response = client.get("/api/jobs", headers=user_with_resume["headers"])
    assert response.status_code == 200

    jobs = response.json()
    assert len(jobs) > 1
    scores = [j["score"] for j in jobs]
    assert scores == sorted(scores, reverse=True)


def test_each_job_carries_its_explanation_and_sources(
    client: TestClient, user_with_resume: dict, seed_jobs
) -> None:
    job = client.get("/api/jobs", headers=user_with_resume["headers"]).json()[0]

    assert job["reason"]
    assert isinstance(job["sources"], list)
    assert job["sources"]
    assert job["status"] == "new"


def test_updating_status_persists(client: TestClient, user_with_resume: dict, seed_jobs) -> None:
    headers = user_with_resume["headers"]
    job_id = client.get("/api/jobs", headers=headers).json()[0]["id"]

    patched = client.patch(f"/api/jobs/{job_id}", json={"status": "applied"}, headers=headers)
    assert patched.status_code == 200
    assert patched.json()["status"] == "applied"

    refetched = next(j for j in client.get("/api/jobs", headers=headers).json() if j["id"] == job_id)
    assert refetched["status"] == "applied"


def test_updating_notes_persists(client: TestClient, user_with_resume: dict, seed_jobs) -> None:
    headers = user_with_resume["headers"]
    job_id = client.get("/api/jobs", headers=headers).json()[0]["id"]

    client.patch(f"/api/jobs/{job_id}", json={"notes": "Referred by Priya"}, headers=headers)
    refetched = next(j for j in client.get("/api/jobs", headers=headers).json() if j["id"] == job_id)
    assert refetched["notes"] == "Referred by Priya"


def test_patching_status_alone_does_not_wipe_notes(
    client: TestClient, user_with_resume: dict, seed_jobs
) -> None:
    headers = user_with_resume["headers"]
    job_id = client.get("/api/jobs", headers=headers).json()[0]["id"]

    client.patch(f"/api/jobs/{job_id}", json={"notes": "Keep me"}, headers=headers)
    client.patch(f"/api/jobs/{job_id}", json={"status": "interviewing"}, headers=headers)

    refetched = next(j for j in client.get("/api/jobs", headers=headers).json() if j["id"] == job_id)
    assert refetched["notes"] == "Keep me"
    assert refetched["status"] == "interviewing"


def test_patching_an_unknown_job_returns_404(client: TestClient, registered_user: dict) -> None:
    response = client.patch(
        "/api/jobs/999999", json={"status": "applied"}, headers=registered_user["headers"]
    )
    assert response.status_code == 404


def test_invalid_status_is_rejected(client: TestClient, user_with_resume: dict, seed_jobs) -> None:
    headers = user_with_resume["headers"]
    job_id = client.get("/api/jobs", headers=headers).json()[0]["id"]
    assert client.patch(f"/api/jobs/{job_id}", json={"status": "banana"}, headers=headers).status_code == 422


def test_statuses_are_per_user_not_global(client: TestClient, user_with_resume: dict, seed_jobs) -> None:
    """The job pool is shared between users; the pipeline status must not be.
    A leak here would show one user another user's applications."""
    headers_a = user_with_resume["headers"]
    job_id = client.get("/api/jobs", headers=headers_a).json()[0]["id"]
    client.patch(f"/api/jobs/{job_id}", json={"status": "offer", "notes": "private"}, headers=headers_a)

    second = client.post(
        "/api/auth/register",
        json={
            "email": "other@example.com",
            "password": "supersecure123",
            "full_name": "Other User",
            "target_cities": ["Seattle, WA"],
            "target_titles": "Software Engineer",
        },
    )
    headers_b = {"Authorization": f"Bearer {second.json()['access_token']}"}

    seen_by_b = next(j for j in client.get("/api/jobs", headers=headers_b).json() if j["id"] == job_id)
    assert seen_by_b["status"] == "new"
    assert seen_by_b["notes"] == ""


def test_stats_reflect_the_pipeline(client: TestClient, user_with_resume: dict, seed_jobs) -> None:
    headers = user_with_resume["headers"]
    jobs = client.get("/api/jobs", headers=headers).json()

    client.patch(f"/api/jobs/{jobs[0]['id']}", json={"status": "applied"}, headers=headers)
    client.patch(f"/api/jobs/{jobs[1]['id']}", json={"status": "interviewing"}, headers=headers)

    stats = client.get("/api/jobs/stats", headers=headers).json()
    assert stats["total"] == len(jobs)
    assert stats["applied"] == 1
    assert stats["interviewing"] == 1
    assert 0 <= stats["avg_score"] <= 100


def test_stats_on_an_empty_pool_do_not_divide_by_zero(client: TestClient, registered_user: dict) -> None:
    stats = client.get("/api/jobs/stats", headers=registered_user["headers"]).json()
    assert stats["total"] == 0
    assert stats["avg_score"] == 0


def test_health_and_sources_are_public(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}

    sources = client.get("/api/sources").json()
    names = {s["name"] for s in sources}
    assert {"adzuna", "jooble", "remotive", "arbeitnow"} <= names
    assert all(isinstance(s["active"], bool) for s in sources)


# ---- Freshness filtering -----------------------------------------------


def test_stale_jobs_are_never_returned(client: TestClient, user_with_resume: dict, seed_jobs) -> None:
    """The 30-day ceiling is a product rule, not a default."""
    from app.services.job_facets import MAX_AGE_DAYS

    jobs = client.get("/api/jobs", headers=user_with_resume["headers"]).json()
    today = datetime.date.today()
    for job in jobs:
        if job["posted"]:
            age = (today - datetime.date.fromisoformat(job["posted"])).days
            assert age <= MAX_AGE_DAYS, f"{job['title']} is {age} days old"


def test_a_narrower_window_returns_a_subset(client: TestClient, user_with_resume: dict, seed_jobs) -> None:
    month = client.get("/api/jobs?posted_within=30d", headers=user_with_resume["headers"]).json()
    week = client.get("/api/jobs?posted_within=7d", headers=user_with_resume["headers"]).json()

    assert len(week) <= len(month)
    assert {j["id"] for j in week} <= {j["id"] for j in month}


def test_results_are_ordered_newest_first(client: TestClient, user_with_resume: dict, seed_jobs) -> None:
    jobs = client.get("/api/jobs", headers=user_with_resume["headers"]).json()
    dated = [j["posted"] for j in jobs if j["posted"]]
    assert dated == sorted(dated, reverse=True)


def test_the_ceiling_cannot_be_raised_by_the_caller(
    client: TestClient, user_with_resume: dict, seed_jobs
) -> None:
    """A caller passing an unknown window is rejected rather than quietly
    served everything."""
    response = client.get("/api/jobs?posted_within=365d", headers=user_with_resume["headers"])
    assert response.status_code == 422


def test_an_unknown_window_names_the_valid_ones(
    client: TestClient, user_with_resume: dict, seed_jobs
) -> None:
    detail = client.get("/api/jobs?posted_within=nonsense", headers=user_with_resume["headers"]).json()[
        "detail"
    ]
    assert "1d" in detail and "30d" in detail
