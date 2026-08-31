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


# ---- Pipeline stages ---------------------------------------------------


def test_a_job_can_move_through_every_stage(client: TestClient, user_with_resume: dict, seed_jobs) -> None:
    """The lifecycle the board draws: saved -> applied -> interviewing ->
    offer -> archived."""
    headers = user_with_resume["headers"]
    job_id = client.get("/api/jobs", headers=headers).json()[0]["id"]

    for stage in ["saved", "applied", "interviewing", "offer", "archived"]:
        response = client.patch(f"/api/jobs/{job_id}", json={"status": stage}, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == stage


def test_archived_survives_a_reload(client: TestClient, user_with_resume: dict, seed_jobs) -> None:
    headers = user_with_resume["headers"]
    job_id = client.get("/api/jobs", headers=headers).json()[0]["id"]
    client.patch(f"/api/jobs/{job_id}", json={"status": "archived"}, headers=headers)

    again = next(j for j in client.get("/api/jobs", headers=headers).json() if j["id"] == job_id)
    assert again["status"] == "archived"


def test_archived_and_rejected_are_distinct_states(
    client: TestClient, user_with_resume: dict, seed_jobs
) -> None:
    """The board groups them in one column, but they record different events:
    rejected happened to you, archived was your decision."""
    headers = user_with_resume["headers"]
    jobs = client.get("/api/jobs", headers=headers).json()

    client.patch(f"/api/jobs/{jobs[0]['id']}", json={"status": "archived"}, headers=headers)
    client.patch(f"/api/jobs/{jobs[1]['id']}", json={"status": "rejected"}, headers=headers)

    fresh = {j["id"]: j["status"] for j in client.get("/api/jobs", headers=headers).json()}
    assert fresh[jobs[0]["id"]] == "archived"
    assert fresh[jobs[1]["id"]] == "rejected"


def test_an_unknown_status_is_rejected(client: TestClient, user_with_resume: dict, seed_jobs) -> None:
    headers = user_with_resume["headers"]
    job_id = client.get("/api/jobs", headers=headers).json()[0]["id"]
    assert client.patch(f"/api/jobs/{job_id}", json={"status": "banana"}, headers=headers).status_code == 422


def test_a_tracked_job_stays_visible_when_preferences_stop_matching(
    client: TestClient, user_with_resume: dict, seed_jobs
) -> None:
    """A saved job must not disappear from the board because the user changed
    their target city -- the board is a record of what they did, not a feed."""
    headers = user_with_resume["headers"]
    job_id = client.get("/api/jobs", headers=headers).json()[0]["id"]
    client.patch(f"/api/jobs/{job_id}", json={"status": "applied"}, headers=headers)

    client.patch("/api/auth/me", json={"target_cities": ["Nowhere, ZZ"]}, headers=headers)

    still_there = next(
        (j for j in client.get("/api/jobs", headers=headers).json() if j["id"] == job_id), None
    )
    assert still_there is not None
    assert still_there["status"] == "applied"


# ---- Filtering by job board -------------------------------------------


def test_filtering_by_source_returns_only_that_board(
    client: TestClient, user_with_resume: dict, seed_jobs
) -> None:
    headers = user_with_resume["headers"]
    jobs = client.get("/api/jobs?source=adzuna", headers=headers).json()

    assert jobs
    for job in jobs:
        assert "adzuna" in job["sources"]
    # And it is genuinely a subset -- the fixture pool spans three boards.
    assert len(jobs) < len(client.get("/api/jobs", headers=headers).json())


def test_a_job_seen_on_two_boards_appears_under_both(
    client: TestClient, user_with_resume: dict, db, make_job
) -> None:
    """Dedup merges one req across boards. Filtering on the board that found
    it second must still find it, so this cannot key off `job.source`."""
    db.add(
        make_job(
            external_id="adzuna:99",
            source="adzuna",
            sources=[
                {"name": "adzuna", "external_id": "99", "url": ""},
                {"name": "greenhouse", "external_id": "99", "url": ""},
            ],
        )
    )
    db.commit()

    headers = user_with_resume["headers"]
    from_adzuna = client.get("/api/jobs?source=adzuna", headers=headers).json()
    from_greenhouse = client.get("/api/jobs?source=greenhouse", headers=headers).json()

    assert {j["id"] for j in from_adzuna} & {j["id"] for j in from_greenhouse}


def test_source_all_is_the_same_as_no_filter(client: TestClient, user_with_resume: dict, seed_jobs) -> None:
    headers = user_with_resume["headers"]
    everything = client.get("/api/jobs", headers=headers).json()
    explicit = client.get("/api/jobs?source=all", headers=headers).json()

    assert [j["id"] for j in explicit] == [j["id"] for j in everything]


def test_an_unknown_source_is_rejected_rather_than_returning_nothing(
    client: TestClient, user_with_resume: dict, seed_jobs
) -> None:
    """An empty page and a bad board name are different facts, and the user
    can only act on one of them."""
    response = client.get("/api/jobs?source=linkedout", headers=user_with_resume["headers"])
    assert response.status_code == 422
    assert "greenhouse" in response.json()["detail"]


def test_seed_postings_are_filterable(client: TestClient, user_with_resume: dict, db, make_job) -> None:
    """The bundled pool has no connector module, but it is the only board a
    fresh install with no credentials has."""
    db.add(make_job(external_id="seed:1", source="seed", sources=[]))
    db.commit()

    jobs = client.get("/api/jobs?source=seed", headers=user_with_resume["headers"]).json()
    assert [j["sources"] for j in jobs] == [["seed"]]


def test_source_and_window_filters_compose(client: TestClient, user_with_resume: dict, db, make_job) -> None:
    import datetime

    db.add(
        make_job(
            external_id="adzuna:old",
            source="adzuna",
            sources=[{"name": "adzuna", "external_id": "old", "url": ""}],
            posted=(datetime.date.today() - datetime.timedelta(days=20)).isoformat(),
        )
    )
    db.commit()

    headers = user_with_resume["headers"]
    month = client.get("/api/jobs?source=adzuna&posted_within=30d", headers=headers).json()
    week = client.get("/api/jobs?source=adzuna&posted_within=7d", headers=headers).json()

    assert {j["id"] for j in week} < {j["id"] for j in month}


# ---- The board picker --------------------------------------------------


def test_job_sources_counts_the_boards_present_in_the_pool(
    client: TestClient, user_with_resume: dict, seed_jobs
) -> None:
    facets = client.get("/api/jobs/sources", headers=user_with_resume["headers"]).json()

    assert {f["name"] for f in facets} == {"adzuna", "jooble", "remotive"}
    assert all(f["count"] == 1 for f in facets)


def test_job_sources_lists_busiest_first(client: TestClient, user_with_resume: dict, db, make_job) -> None:
    for i in range(3):
        db.add(
            make_job(
                external_id=f"lever:{i}",
                source="lever",
                sources=[{"name": "lever", "external_id": str(i), "url": ""}],
            )
        )
    db.add(
        make_job(
            external_id="remotive:1",
            source="remotive",
            sources=[{"name": "remotive", "external_id": "1", "url": ""}],
        )
    )
    db.commit()

    facets = client.get("/api/jobs/sources", headers=user_with_resume["headers"]).json()
    assert [f["name"] for f in facets] == ["lever", "remotive"]
    assert [f["count"] for f in facets] == [3, 1]


def test_job_sources_counts_match_what_the_filter_returns(
    client: TestClient, user_with_resume: dict, seed_jobs
) -> None:
    """The count on a dropdown option has to be the number of jobs the page
    it opens will actually list, or the picker lies."""
    headers = user_with_resume["headers"]
    for facet in client.get("/api/jobs/sources", headers=headers).json():
        listed = client.get(f"/api/jobs?source={facet['name']}", headers=headers).json()
        assert len(listed) == facet["count"], facet["name"]


def test_job_sources_omits_boards_with_nothing_in_the_window(
    client: TestClient, user_with_resume: dict, db, make_job
) -> None:
    """A board that leads to an empty page is not offered as a choice."""
    import datetime

    db.add(
        make_job(
            external_id="jooble:stale",
            source="jooble",
            sources=[{"name": "jooble", "external_id": "stale", "url": ""}],
            posted=(datetime.date.today() - datetime.timedelta(days=25)).isoformat(),
        )
    )
    db.commit()

    headers = user_with_resume["headers"]
    assert "jooble" in {f["name"] for f in client.get("/api/jobs/sources", headers=headers).json()}
    narrow = client.get("/api/jobs/sources?posted_within=7d", headers=headers).json()
    assert "jooble" not in {f["name"] for f in narrow}


def test_job_sources_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/jobs/sources").status_code == 401
