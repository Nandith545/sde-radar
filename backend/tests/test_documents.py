"""Resume and cover-letter versions, and their links to applications."""

from fastapi.testclient import TestClient

RESUME = ("cv.txt", b"Jane Dev\nSenior Software Engineer\nSkills: Python, React", "text/plain")
COVER = ("cover.txt", b"Dear hiring manager,\nI would like to apply.", "text/plain")


def _upload(client: TestClient, headers: dict, file=RESUME, kind="resume", label="") -> dict:
    return client.post(
        "/api/documents",
        files={"file": file},
        data={"kind": kind, "label": label},
        headers=headers,
    ).json()


def test_uploading_a_document_returns_its_metadata(client: TestClient, registered_user: dict) -> None:
    doc = _upload(client, registered_user["headers"], label="Backend-heavy")

    assert doc["kind"] == "resume"
    assert doc["label"] == "Backend-heavy"
    assert doc["filename"] == "cv.txt"
    assert doc["size_bytes"] == len(RESUME[1])


def test_the_listing_never_carries_the_file_bytes(client: TestClient, registered_user: dict) -> None:
    """Rendering a list of filenames shouldn't ship several MB of PDF."""
    _upload(client, registered_user["headers"])

    listing = client.get("/api/documents", headers=registered_user["headers"]).json()
    assert listing and "content" not in listing[0]


def test_uploading_a_revision_keeps_the_previous_version(client: TestClient, registered_user: dict) -> None:
    """The whole feature rests on this: an upload adds, never overwrites."""
    headers = registered_user["headers"]
    first = _upload(client, headers, label="v1")
    second = _upload(client, headers, file=("cv2.txt", b"Jane Dev v2", "text/plain"), label="v2")

    ids = {d["id"] for d in client.get("/api/documents", headers=headers).json()}
    assert first["id"] in ids and second["id"] in ids
    assert first["id"] != second["id"]


def test_the_exact_bytes_come_back(client: TestClient, registered_user: dict) -> None:
    doc = _upload(client, registered_user["headers"])

    response = client.get(f"/api/documents/{doc['id']}/download", headers=registered_user["headers"])
    assert response.status_code == 200
    assert response.content == RESUME[1]


def test_you_cannot_download_someone_elses_document(client: TestClient, registered_user: dict) -> None:
    """Ids are sequential, so without an ownership filter guessing one would
    hand over another user's resume."""
    mine = _upload(client, registered_user["headers"])

    other = client.post(
        "/api/auth/register",
        json={
            "email": "other@example.com",
            "password": "supersecure123",
            "full_name": "Other",
            "target_cities": [],
            "target_titles": "Engineer",
        },
    ).json()
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}

    assert client.get(f"/api/documents/{mine['id']}/download", headers=other_headers).status_code == 404
    assert client.delete(f"/api/documents/{mine['id']}", headers=other_headers).status_code == 404


def test_an_unknown_kind_is_rejected(client: TestClient, registered_user: dict) -> None:
    response = client.post(
        "/api/documents",
        files={"file": RESUME},
        data={"kind": "manifesto"},
        headers=registered_user["headers"],
    )
    assert response.status_code == 422


def test_an_unsupported_extension_is_rejected(client: TestClient, registered_user: dict) -> None:
    response = client.post(
        "/api/documents",
        files={"file": ("resume.docx", b"binary", "application/octet-stream")},
        data={"kind": "resume"},
        headers=registered_user["headers"],
    )
    assert response.status_code == 400


def test_an_empty_file_is_rejected(client: TestClient, registered_user: dict) -> None:
    response = client.post(
        "/api/documents",
        files={"file": ("empty.txt", b"", "text/plain")},
        data={"kind": "resume"},
        headers=registered_user["headers"],
    )
    assert response.status_code == 400


def test_documents_attach_to_an_application(client: TestClient, user_with_resume: dict, seed_jobs) -> None:
    headers = user_with_resume["headers"]
    resume = _upload(client, headers, label="v1")
    cover = _upload(client, headers, file=COVER, kind="cover_letter", label="Generic")
    job_id = client.get("/api/jobs", headers=headers).json()[0]["id"]

    updated = client.patch(
        f"/api/jobs/{job_id}",
        json={
            "status": "applied",
            "resume_document_id": resume["id"],
            "cover_letter_document_id": cover["id"],
        },
        headers=headers,
    ).json()

    assert updated["resume_document_id"] == resume["id"]
    assert updated["cover_letter_document_id"] == cover["id"]


def test_the_attachment_survives_a_reload(client: TestClient, user_with_resume: dict, seed_jobs) -> None:
    """Six weeks later you still need to know which version you sent."""
    headers = user_with_resume["headers"]
    resume = _upload(client, headers, label="v1")
    job_id = client.get("/api/jobs", headers=headers).json()[0]["id"]
    client.patch(
        f"/api/jobs/{job_id}",
        json={"status": "applied", "resume_document_id": resume["id"]},
        headers=headers,
    )

    again = next(j for j in client.get("/api/jobs", headers=headers).json() if j["id"] == job_id)
    assert again["resume_document_id"] == resume["id"]


def test_zero_detaches_a_document(client: TestClient, user_with_resume: dict, seed_jobs) -> None:
    """None means "leave it alone", so there has to be another way to say
    "remove it"."""
    headers = user_with_resume["headers"]
    resume = _upload(client, headers)
    job_id = client.get("/api/jobs", headers=headers).json()[0]["id"]
    client.patch(f"/api/jobs/{job_id}", json={"resume_document_id": resume["id"]}, headers=headers)

    cleared = client.patch(f"/api/jobs/{job_id}", json={"resume_document_id": 0}, headers=headers).json()
    assert cleared["resume_document_id"] is None


def test_you_cannot_attach_a_document_you_do_not_own(
    client: TestClient, user_with_resume: dict, seed_jobs
) -> None:
    headers = user_with_resume["headers"]
    other = client.post(
        "/api/auth/register",
        json={
            "email": "thief@example.com",
            "password": "supersecure123",
            "full_name": "Thief",
            "target_cities": [],
            "target_titles": "Engineer",
        },
    ).json()
    victim_doc = _upload(client, headers)
    job_id = client.get("/api/jobs", headers=headers).json()[0]["id"]

    response = client.patch(
        f"/api/jobs/{job_id}",
        json={"resume_document_id": victim_doc["id"]},
        headers={"Authorization": f"Bearer {other['access_token']}"},
    )
    assert response.status_code == 404


def test_deleting_an_attached_document_is_refused(
    client: TestClient, user_with_resume: dict, seed_jobs
) -> None:
    """It's the record of what was sent -- deleting it would leave the
    application pointing at nothing."""
    headers = user_with_resume["headers"]
    resume = _upload(client, headers)
    job_id = client.get("/api/jobs", headers=headers).json()[0]["id"]
    client.patch(f"/api/jobs/{job_id}", json={"resume_document_id": resume["id"]}, headers=headers)

    response = client.delete(f"/api/documents/{resume['id']}", headers=headers)
    assert response.status_code == 409
    assert "attached" in response.json()["detail"].lower()


def test_an_unattached_document_can_be_deleted(client: TestClient, registered_user: dict) -> None:
    doc = _upload(client, registered_user["headers"])

    assert client.delete(f"/api/documents/{doc['id']}", headers=registered_user["headers"]).status_code == 204
    assert client.get("/api/documents", headers=registered_user["headers"]).json() == []


def test_documents_require_authentication(client: TestClient) -> None:
    assert client.get("/api/documents").status_code == 401
    assert client.post("/api/documents", files={"file": RESUME}).status_code == 401
