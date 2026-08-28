"""Resume upload and retrieval."""

import io

import pytest
from fastapi.testclient import TestClient

RESUME = b"""Jane Dev
Senior Software Engineer with 9 years of experience
Skills: Python, Java, AWS, Docker, Kubernetes, React
"""


def test_upload_requires_authentication(client: TestClient) -> None:
    response = client.post("/api/resume", files={"file": ("r.txt", RESUME, "text/plain")})
    assert response.status_code == 401


def test_upload_extracts_skills_and_experience(client: TestClient, registered_user: dict) -> None:
    response = client.post(
        "/api/resume",
        files={"file": ("resume.txt", RESUME, "text/plain")},
        headers=registered_user["headers"],
    )
    assert response.status_code == 200

    body = response.json()
    assert body["filename"] == "resume.txt"
    assert "Python" in body["skills"]
    assert body["years_experience"] == 9.0


def test_upload_flips_has_resume_on_the_profile(client: TestClient, registered_user: dict) -> None:
    headers = registered_user["headers"]
    assert client.get("/api/auth/me", headers=headers).json()["has_resume"] is False

    client.post("/api/resume", files={"file": ("r.txt", RESUME, "text/plain")}, headers=headers)
    assert client.get("/api/auth/me", headers=headers).json()["has_resume"] is True


def test_reuploading_replaces_rather_than_duplicates(client: TestClient, registered_user: dict) -> None:
    headers = registered_user["headers"]
    client.post("/api/resume", files={"file": ("first.txt", RESUME, "text/plain")}, headers=headers)

    second = b"Jane Dev\n3 years of experience\nSkills: Go, Terraform"
    response = client.post(
        "/api/resume", files={"file": ("second.txt", second, "text/plain")}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["filename"] == "second.txt"
    assert "Go" in response.json()["skills"]

    fetched = client.get("/api/resume", headers=headers).json()
    assert fetched["filename"] == "second.txt"


@pytest.mark.parametrize("filename", ["resume.exe", "resume.docx", "resume.png", "resume"])
def test_disallowed_file_types_are_rejected(client: TestClient, registered_user: dict, filename: str) -> None:
    response = client.post(
        "/api/resume",
        files={"file": (filename, RESUME, "application/octet-stream")},
        headers=registered_user["headers"],
    )
    assert response.status_code == 400


def test_oversized_upload_is_rejected(client: TestClient, registered_user: dict) -> None:
    big = io.BytesIO(b"x" * (6 * 1024 * 1024))  # 6MB, over the 5MB cap
    response = client.post(
        "/api/resume",
        files={"file": ("big.txt", big, "text/plain")},
        headers=registered_user["headers"],
    )
    assert response.status_code == 400
    assert "too large" in response.json()["detail"].lower()


def test_file_with_no_recognisable_skills_is_rejected_clearly(
    client: TestClient, registered_user: dict
) -> None:
    response = client.post(
        "/api/resume",
        files={"file": ("empty.txt", b"Hello, I like long walks on the beach.", "text/plain")},
        headers=registered_user["headers"],
    )
    assert response.status_code == 422
    assert "skills" in response.json()["detail"].lower()


def test_getting_a_resume_before_uploading_returns_404(client: TestClient, registered_user: dict) -> None:
    assert client.get("/api/resume", headers=registered_user["headers"]).status_code == 404


def test_resumes_are_not_visible_across_accounts(client: TestClient, registered_user: dict) -> None:
    client.post(
        "/api/resume", files={"file": ("r.txt", RESUME, "text/plain")}, headers=registered_user["headers"]
    )

    other = client.post(
        "/api/auth/register",
        json={
            "email": "other@example.com",
            "password": "supersecure123",
            "full_name": "Other",
            "target_cities": ["Seattle, WA"],
            "target_titles": "Software Engineer",
        },
    )
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    assert client.get("/api/resume", headers=other_headers).status_code == 404
