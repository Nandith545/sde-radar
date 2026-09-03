"""Job-board connectors, with HTTP stubbed at the transport layer via respx.

These payloads mirror each provider's documented response shape. That is an
important caveat: passing here proves the parsing logic is correct *for the
shape we believe the API returns*, not that the live API still returns it.
The value is regression safety — if someone refactors a connector, these
catch it — plus proof that malformed data degrades instead of exploding.
"""

import logging

import httpx
import pytest
import respx

from app.services.sources import (
    active_sources,
    adzuna,
    arbeitnow,
    ashby,
    greenhouse,
    jooble,
    lever,
    remotive,
    smartrecruiters,
)
from app.services.sources.base import RawJob, describe_http_error

# ---- Registry -----------------------------------------------------------


def test_keyless_connectors_are_always_active() -> None:
    assert remotive.is_configured() is True
    assert arbeitnow.is_configured() is True


def test_keyed_connectors_are_inactive_without_credentials(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.adzuna_app_id", "")
    monkeypatch.setattr("app.config.settings.adzuna_app_key", "")
    monkeypatch.setattr("app.config.settings.jooble_api_key", "")
    assert adzuna.is_configured() is False
    assert jooble.is_configured() is False


def test_every_registered_connector_satisfies_the_protocol() -> None:
    """Adding a board is meant to be one file plus one registry line; this
    fails loudly if a new module forgets part of the contract."""
    from app.services.sources import REGISTRY

    for module in REGISTRY:
        assert isinstance(module.NAME, str) and module.NAME
        assert callable(module.is_configured)
        assert callable(module.fetch)


def test_active_sources_reports_only_configured_boards(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.adzuna_app_id", "")
    monkeypatch.setattr("app.config.settings.adzuna_app_key", "")
    monkeypatch.setattr("app.config.settings.jooble_api_key", "")
    active = active_sources()
    assert "remotive" in active
    assert "arbeitnow" in active
    assert "adzuna" not in active


# ---- Remotive -----------------------------------------------------------

REMOTIVE_PAYLOAD = {
    "jobs": [
        {
            "id": 1001,
            "title": "Senior Backend Engineer",
            "company_name": "Remote Co",
            "candidate_required_location": "USA",
            "description": "Python and Django.",
            "salary": "$120,000 - $150,000 a year",
            "job_type": "full_time",
            "publication_date": "2026-08-20T10:00:00",
            "url": "https://remotive.com/jobs/1001",
        }
    ]
}


@respx.mock
def test_remotive_parses_a_documented_response() -> None:
    respx.get(url__startswith="https://remotive.com/api/remote-jobs").mock(
        return_value=httpx.Response(200, json=REMOTIVE_PAYLOAD)
    )

    jobs = remotive.fetch(["Backend Engineer"], "Seattle, WA")

    assert len(jobs) == 1
    job = jobs[0]
    assert isinstance(job, RawJob)
    assert job.source == "remotive"
    assert job.external_id == "1001"
    assert job.title == "Senior Backend Engineer"
    assert job.company == "Remote Co"
    assert job.comp_min == 120000.0
    assert job.comp_max == 150000.0


@respx.mock
def test_remotive_does_not_return_the_same_job_twice_across_search_terms() -> None:
    respx.get(url__startswith="https://remotive.com/api/remote-jobs").mock(
        return_value=httpx.Response(200, json=REMOTIVE_PAYLOAD)
    )

    jobs = remotive.fetch(["Backend Engineer", "Software Engineer", "Python"], "Seattle, WA")
    assert len(jobs) == 1


# ---- Arbeitnow ----------------------------------------------------------


@respx.mock
def test_arbeitnow_filters_by_keyword_and_converts_timestamps() -> None:
    respx.get(url__startswith="https://www.arbeitnow.com/api/job-board-api").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "slug": "backend-engineer-abc",
                        "title": "Backend Engineer",
                        "company_name": "Widgets GmbH",
                        "location": "Seattle",
                        "description": "Go and Postgres.",
                        "remote": False,
                        "tags": ["backend"],
                        "job_types": ["full_time"],
                        "created_at": 1755648000,
                        "url": "https://arbeitnow.com/view/backend-engineer-abc",
                    },
                    {
                        "slug": "chef-de-partie",
                        "title": "Chef de Partie",
                        "company_name": "Restaurant",
                        "location": "Seattle",
                        "remote": False,
                        "tags": ["hospitality"],
                        "created_at": 1755648000,
                        "url": "https://arbeitnow.com/view/chef",
                    },
                ]
            },
        )
    )

    jobs = arbeitnow.fetch(["Backend Engineer"], "Seattle, WA")

    assert [j.title for j in jobs] == ["Backend Engineer"]
    assert jobs[0].posted  # unix timestamp converted to an ISO date
    assert len(jobs[0].posted) == 10


# ---- Failure handling ---------------------------------------------------


@respx.mock
@pytest.mark.parametrize("status", [400, 401, 429, 500, 503])
def test_http_errors_yield_no_jobs_instead_of_raising(status: int) -> None:
    """One board being down must never take down a whole refresh."""
    respx.get(url__startswith="https://remotive.com/api/remote-jobs").mock(
        return_value=httpx.Response(status)
    )
    assert remotive.fetch(["Backend Engineer"], "Seattle, WA") == []


@respx.mock
def test_network_errors_are_swallowed() -> None:
    respx.get(url__startswith="https://remotive.com/api/remote-jobs").mock(
        side_effect=httpx.ConnectError("connection refused")
    )
    assert remotive.fetch(["Backend Engineer"], "Seattle, WA") == []


@respx.mock
def test_malformed_json_yields_no_jobs() -> None:
    respx.get(url__startswith="https://remotive.com/api/remote-jobs").mock(
        return_value=httpx.Response(200, text="this is not json")
    )
    assert remotive.fetch(["Backend Engineer"], "Seattle, WA") == []


@respx.mock
def test_a_single_malformed_listing_does_not_discard_the_good_ones() -> None:
    """The defensive per-item parsing is the whole reason these connectors can
    ship without having been run against the live API."""
    respx.get(url__startswith="https://remotive.com/api/remote-jobs").mock(
        return_value=httpx.Response(
            200,
            json={
                "jobs": [
                    {"id": None, "title": None},  # junk
                    REMOTIVE_PAYLOAD["jobs"][0],  # valid
                ]
            },
        )
    )

    jobs = remotive.fetch(["Backend Engineer"], "Seattle, WA")
    assert len(jobs) == 1
    assert jobs[0].external_id == "1001"


@respx.mock
def test_unexpected_response_envelope_is_handled() -> None:
    """If a provider renames its top-level key, we get nothing -- not a crash."""
    respx.get(url__startswith="https://remotive.com/api/remote-jobs").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    assert remotive.fetch(["Backend Engineer"], "Seattle, WA") == []


# ---- Adzuna -------------------------------------------------------------

ADZUNA_PAYLOAD = {
    "results": [
        {
            "id": 4242,
            "title": "Staff Software Engineer",
            "company": {"display_name": "Acme Corp"},
            "location": {"display_name": "Seattle, WA"},
            "description": "Distributed systems in Java.",
            "salary_min": 180000,
            "salary_max": 240000,
            "contract_time": "full_time",
            "created": "2026-08-18T00:00:00Z",
            "redirect_url": "https://adzuna.com/jobs/4242",
        }
    ]
}


@respx.mock
def test_adzuna_parses_a_documented_response(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.adzuna_app_id", "id")
    monkeypatch.setattr("app.config.settings.adzuna_app_key", "key")
    respx.get(url__startswith="https://api.adzuna.com").mock(
        return_value=httpx.Response(200, json=ADZUNA_PAYLOAD)
    )

    jobs = adzuna.fetch(["Software Engineer"], "Seattle, WA")

    assert len(jobs) == 1
    assert jobs[0].external_id == "4242"
    assert jobs[0].company == "Acme Corp"
    assert jobs[0].comp_min == 180000


@respx.mock
def test_adzuna_skips_listings_with_no_usable_id(monkeypatch) -> None:
    """Regression: `str(item.get("id"))` produced the string "None", so every
    id-less listing collided on one external_id and became a phantom job."""
    monkeypatch.setattr("app.config.settings.adzuna_app_id", "id")
    monkeypatch.setattr("app.config.settings.adzuna_app_key", "key")
    respx.get(url__startswith="https://api.adzuna.com").mock(
        return_value=httpx.Response(
            200,
            json={"results": [{"title": "No id here", "company": {"display_name": "X"}}]},
        )
    )

    assert adzuna.fetch(["Software Engineer"], "Seattle, WA") == []


# ---- Jooble -------------------------------------------------------------


@respx.mock
def test_jooble_parses_a_documented_response(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.jooble_api_key", "testkey")
    respx.post(url__startswith="https://jooble.org/api/").mock(
        return_value=httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "id": "abc123",
                        "title": "Backend Engineer",
                        "company": "Globex",
                        "location": "Seattle, WA",
                        "snippet": "Python and Postgres.",
                        "salary": "$130,000 - $160,000 a year",
                        "type": "Full-time",
                        "updated": "2026-08-19T00:00:00",
                        "link": "https://jooble.org/jdp/abc123",
                    }
                ]
            },
        )
    )

    jobs = jooble.fetch(["Backend Engineer"], "Seattle, WA")

    assert len(jobs) == 1
    assert jobs[0].external_id == "abc123"
    assert jobs[0].comp_min == 130000.0


@respx.mock
def test_jooble_falls_back_to_the_link_when_there_is_no_id(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.jooble_api_key", "testkey")
    respx.post(url__startswith="https://jooble.org/api/").mock(
        return_value=httpx.Response(
            200,
            json={"jobs": [{"title": "Backend Engineer", "link": "https://jooble.org/jdp/xyz"}]},
        )
    )

    jobs = jooble.fetch(["Backend Engineer"], "Seattle, WA")
    assert len(jobs) == 1
    assert jobs[0].external_id == "https://jooble.org/jdp/xyz"


def test_jooble_makes_no_request_without_an_api_key(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.jooble_api_key", "")
    # No respx mock installed: any real request would error, so returning []
    # proves it short-circuits before touching the network.
    assert jooble.fetch(["Backend Engineer"], "Seattle, WA") == []


# ---- Greenhouse & Lever (per-company boards) ---------------------------

_GREENHOUSE_PAYLOAD = {
    "name": "Stripe",
    "jobs": [
        {
            "id": 12345,
            "title": "Senior Software Engineer",
            "updated_at": "2026-08-20T10:00:00-04:00",
            "location": {"name": "Remote - US"},
            "absolute_url": "https://boards.greenhouse.io/stripe/jobs/12345",
            "content": "&lt;p&gt;Build payments infra in &lt;strong&gt;Python&lt;/strong&gt;.&lt;/p&gt;",
        },
        {
            "id": 12346,
            "title": "Product Designer",
            "updated_at": "2026-08-19T10:00:00-04:00",
            "location": {"name": "Seattle, WA"},
            "absolute_url": "https://boards.greenhouse.io/stripe/jobs/12346",
            "content": "Design things.",
        },
    ],
}

_LEVER_PAYLOAD = [
    {
        "id": "abc-123",
        "text": "Backend Engineer",
        "categories": {"location": "Remote", "commitment": "Full-time"},
        "descriptionPlain": "Write Go services.",
        "hostedUrl": "https://jobs.lever.co/acme/abc-123",
        "createdAt": 1755676800000,
    },
    {
        "id": "def-456",
        "text": "Sales Lead",
        "categories": {"location": "New York"},
        "descriptionPlain": "Sell things.",
        "hostedUrl": "https://jobs.lever.co/acme/def-456",
        "createdAt": 1755676800000,
    },
]


def test_greenhouse_is_inactive_without_configured_companies(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.greenhouse_companies", "")
    assert greenhouse.is_configured() is False
    monkeypatch.setattr("app.config.settings.greenhouse_companies", "stripe, gitlab")
    assert greenhouse.is_configured() is True


def test_lever_is_inactive_without_configured_companies(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.lever_companies", "")
    assert lever.is_configured() is False
    monkeypatch.setattr("app.config.settings.lever_companies", "acme")
    assert lever.is_configured() is True


@respx.mock
def test_greenhouse_parses_and_filters(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.greenhouse_companies", "stripe")
    respx.get(url__startswith="https://boards-api.greenhouse.io/v1/boards/stripe/jobs").mock(
        return_value=httpx.Response(200, json=_GREENHOUSE_PAYLOAD)
    )

    jobs = greenhouse.fetch(["engineer"], "remote")

    # Only the engineering role matches the keyword; the designer is dropped.
    assert len(jobs) == 1
    job = jobs[0]
    assert job.title == "Senior Software Engineer"
    assert job.company == "Stripe"
    assert job.external_id == "12345"
    assert job.posted == "2026-08-20"
    # HTML-escaped HTML is unescaped and stripped to plain text.
    assert "Python" in job.description and "<" not in job.description


@respx.mock
def test_greenhouse_one_bad_company_does_not_sink_the_others(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.greenhouse_companies", "broken, stripe")
    respx.get(url__startswith="https://boards-api.greenhouse.io/v1/boards/broken/jobs").mock(
        return_value=httpx.Response(404)
    )
    respx.get(url__startswith="https://boards-api.greenhouse.io/v1/boards/stripe/jobs").mock(
        return_value=httpx.Response(200, json=_GREENHOUSE_PAYLOAD)
    )

    jobs = greenhouse.fetch([], "")
    assert {j.external_id for j in jobs} == {"12345", "12346"}


@respx.mock
def test_lever_parses_and_converts_ms_timestamps(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.lever_companies", "acme")
    respx.get(url__startswith="https://api.lever.co/v0/postings/acme").mock(
        return_value=httpx.Response(200, json=_LEVER_PAYLOAD)
    )

    jobs = lever.fetch(["engineer"], "")

    assert len(jobs) == 1
    job = jobs[0]
    assert job.title == "Backend Engineer"
    assert job.company == "Acme"
    assert job.external_id == "abc-123"
    # 1755676800000 ms -> 2025-08-20
    assert job.posted == "2025-08-20"
    assert job.job_type == "Full-time"


@respx.mock
def test_lever_tolerates_a_non_list_payload(monkeypatch) -> None:
    """The API returns a bare list; anything else must degrade, not crash."""
    monkeypatch.setattr("app.config.settings.lever_companies", "acme")
    respx.get(url__startswith="https://api.lever.co/v0/postings/acme").mock(
        return_value=httpx.Response(200, json={"error": "not found"})
    )
    assert lever.fetch([], "") == []


# ---- Ashby --------------------------------------------------------------

# Mirrors a real board response: field names and value vocabulary were taken
# from api.ashbyhq.com/posting-api/job-board/ramp, not from the docs alone.
_ASHBY_PAYLOAD = {
    "apiVersion": "1",
    "jobs": [
        {
            "id": "34413f8d-26bf-4bbc-8ade-eb309a0e2245",
            "title": "Senior Software Engineer",
            "location": "New York, NY (HQ)",
            "department": "Engineering",
            "employmentType": "FullTime",
            "publishedAt": "2026-08-20T17:12:35.753+00:00",
            "jobUrl": "https://jobs.ashbyhq.com/ramp/34413f8d",
            "applyUrl": "https://jobs.ashbyhq.com/ramp/34413f8d/application",
            "descriptionPlain": "Build distributed systems in Python and Go on AWS.",
            "isRemote": True,
            "isListed": True,
            "compensation": {
                "scrapeableCompensationSalarySummary": "$211.4K - $290.6K",
                "compensationTierSummary": "$211.4K – $290.6K • Offers Equity",
            },
        },
        {
            "id": "aaaa1111",
            "title": "Product Designer",
            "location": "New York, NY",
            "employmentType": "FullTime",
            "publishedAt": "2026-08-21T00:00:00.000+00:00",
            "jobUrl": "https://jobs.ashbyhq.com/ramp/aaaa1111",
            "descriptionPlain": "Design things.",
            "isRemote": False,
            "isListed": True,
        },
        {
            "id": "bbbb2222",
            "title": "Software Engineering Intern",
            "location": "Austin, TX",
            "employmentType": "Intern",
            "publishedAt": "2026-08-22T00:00:00.000+00:00",
            "jobUrl": "https://jobs.ashbyhq.com/ramp/bbbb2222",
            "descriptionPlain": "Intern on the platform team.",
            "isRemote": False,
            "isListed": False,
        },
    ],
}


def test_ashby_is_inactive_without_configured_companies(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.ashby_companies", "")
    assert ashby.is_configured() is False
    monkeypatch.setattr("app.config.settings.ashby_companies", "ramp, vanta")
    assert ashby.is_configured() is True


@respx.mock
def test_ashby_parses_and_filters(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.ashby_companies", "ramp")
    respx.get(url__startswith="https://api.ashbyhq.com/posting-api/job-board/ramp").mock(
        return_value=httpx.Response(200, json=_ASHBY_PAYLOAD)
    )

    jobs = ashby.fetch(["engineer"], "")

    # The designer is dropped on keyword; the intern is dropped as unlisted.
    assert len(jobs) == 1
    job = jobs[0]
    assert job.title == "Senior Software Engineer"
    assert job.company == "Ramp"
    assert job.external_id == "34413f8d-26bf-4bbc-8ade-eb309a0e2245"
    assert job.posted == "2026-08-20"
    assert job.job_type == "Full-time"
    assert "Python" in job.description


@respx.mock
def test_ashby_reads_the_published_salary_range(monkeypatch) -> None:
    """Ashby is one of the few boards that publishes a parseable range, which
    is what makes the salary preference and the compensation sort useful."""
    monkeypatch.setattr("app.config.settings.ashby_companies", "ramp")
    respx.get(url__startswith="https://api.ashbyhq.com/posting-api/job-board/ramp").mock(
        return_value=httpx.Response(200, json=_ASHBY_PAYLOAD)
    )

    job = ashby.fetch(["engineer"], "")[0]
    assert (job.comp_min, job.comp_max, job.comp_unit) == (211400.0, 290600.0, "year")


@respx.mock
def test_ashby_marks_remote_roles_without_doubling_the_hq_label(monkeypatch) -> None:
    """The location field names the office even on a remote req. Without the
    suffix a remote job reads as onsite and is filtered out for anyone
    targeting another city; keeping Ashby's "(HQ)" would render as
    "New York, NY (HQ) (Remote)", which looks like a bug on the card."""
    monkeypatch.setattr("app.config.settings.ashby_companies", "ramp")
    respx.get(url__startswith="https://api.ashbyhq.com/posting-api/job-board/ramp").mock(
        return_value=httpx.Response(200, json=_ASHBY_PAYLOAD)
    )

    assert ashby.fetch(["engineer"], "")[0].location == "New York, NY (Remote)"


@respx.mock
def test_ashby_remote_roles_survive_a_city_filter(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.ashby_companies", "ramp")
    respx.get(url__startswith="https://api.ashbyhq.com/posting-api/job-board/ramp").mock(
        return_value=httpx.Response(200, json=_ASHBY_PAYLOAD)
    )

    assert len(ashby.fetch(["engineer"], "Seattle, WA")) == 1


@respx.mock
def test_ashby_survives_a_malformed_posting(monkeypatch) -> None:
    """One bad posting must not cost the whole board."""
    monkeypatch.setattr("app.config.settings.ashby_companies", "ramp")
    payload = {"jobs": [{"id": None, "title": None}, *_ASHBY_PAYLOAD["jobs"]]}
    respx.get(url__startswith="https://api.ashbyhq.com/posting-api/job-board/ramp").mock(
        return_value=httpx.Response(200, json=payload)
    )

    assert len(ashby.fetch(["engineer"], "")) == 1


@respx.mock
def test_ashby_returns_nothing_on_an_http_error(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.ashby_companies", "ramp")
    respx.get(url__startswith="https://api.ashbyhq.com/posting-api/job-board/ramp").mock(
        return_value=httpx.Response(404, json={"error": "not found"})
    )
    assert ashby.fetch([], "") == []


# ---- SmartRecruiters ----------------------------------------------------

_SR_LIST = {
    "offset": 0,
    "limit": 100,
    "totalFound": 2,
    "content": [
        {
            "id": "744000146555579",
            "name": "Software Engineer - AI",
            "company": {"name": "Bosch Group", "identifier": "BoschGroup"},
            "location": {"city": "Braga", "region": "Braga", "country": "pt", "remote": False},
            "releasedDate": "2026-08-27T21:10:17.051Z",
            "typeOfEmployment": {"label": "Permanent"},
        },
        {
            "id": "744000146555580",
            "name": "Facilities Coordinator",
            "company": {"name": "Bosch Group", "identifier": "BoschGroup"},
            "location": {"city": "Vernon Hills", "region": "IL", "country": "us", "remote": False},
            "releasedDate": "2026-08-26T00:00:00.000Z",
            "typeOfEmployment": {"label": "Permanent"},
        },
    ],
}

_SR_DETAIL = {
    "id": "744000146555579",
    "jobAd": {
        "sections": {
            "jobDescription": {"text": "Build ML pipelines."},
            "qualifications": {"text": "Python, PyTorch, Kubernetes."},
            "additionalInformation": {"text": "Hybrid working."},
        }
    },
}


def test_smartrecruiters_is_inactive_without_configured_companies(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.smartrecruiters_companies", "")
    assert smartrecruiters.is_configured() is False
    monkeypatch.setattr("app.config.settings.smartrecruiters_companies", "BoschGroup")
    assert smartrecruiters.is_configured() is True


@respx.mock
def test_smartrecruiters_parses_and_filters(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.smartrecruiters_companies", "BoschGroup")
    respx.get(url__regex=r".*/companies/BoschGroup/postings\?.*").mock(
        return_value=httpx.Response(200, json=_SR_LIST)
    )
    respx.get(url__regex=r".*/postings/744000146555579$").mock(
        return_value=httpx.Response(200, json=_SR_DETAIL)
    )

    jobs = smartrecruiters.fetch(["software engineer"], "")

    assert len(jobs) == 1
    job = jobs[0]
    assert job.title == "Software Engineer - AI"
    assert job.company == "Bosch Group"
    assert job.posted == "2026-08-27"
    assert job.job_type == "Full-time"


@respx.mock
def test_smartrecruiters_flattens_the_structured_location(monkeypatch) -> None:
    """The rest of the pipeline reads a freeform string, and "City, REGION"
    is the shape the country and region inference are tuned for."""
    monkeypatch.setattr("app.config.settings.smartrecruiters_companies", "BoschGroup")
    respx.get(url__regex=r".*/companies/BoschGroup/postings\?.*").mock(
        return_value=httpx.Response(200, json=_SR_LIST)
    )
    respx.get(url__regex=r".*/postings/\d+$").mock(return_value=httpx.Response(200, json=_SR_DETAIL))

    assert smartrecruiters.fetch(["software engineer"], "")[0].location == "Braga, Braga"


@respx.mock
def test_smartrecruiters_builds_a_link_the_list_response_lacks(monkeypatch) -> None:
    """applyUrl exists only on the detail record, which most postings never
    fetch -- so nothing may reach the pool without a working Apply button."""
    monkeypatch.setattr("app.config.settings.smartrecruiters_companies", "BoschGroup")
    respx.get(url__regex=r".*/companies/BoschGroup/postings\?.*").mock(
        return_value=httpx.Response(200, json=_SR_LIST)
    )
    respx.get(url__regex=r".*/postings/\d+$").mock(return_value=httpx.Response(200, json=_SR_DETAIL))

    job = smartrecruiters.fetch(["software engineer"], "")[0]
    assert job.url == "https://jobs.smartrecruiters.com/BoschGroup/744000146555579"


@respx.mock
def test_smartrecruiters_joins_every_jobad_section(monkeypatch) -> None:
    """Skills are as often in qualifications as in the description proper."""
    monkeypatch.setattr("app.config.settings.smartrecruiters_companies", "BoschGroup")
    respx.get(url__regex=r".*/companies/BoschGroup/postings\?.*").mock(
        return_value=httpx.Response(200, json=_SR_LIST)
    )
    respx.get(url__regex=r".*/postings/\d+$").mock(return_value=httpx.Response(200, json=_SR_DETAIL))

    description = smartrecruiters.fetch(["software engineer"], "")[0].description
    assert "PyTorch" in description and "Build ML pipelines" in description


@respx.mock
def test_smartrecruiters_still_emits_a_posting_when_the_detail_call_fails(monkeypatch) -> None:
    """A listing shown without a description beats one the user never learns
    exists, so a failed detail fetch degrades rather than drops."""
    monkeypatch.setattr("app.config.settings.smartrecruiters_companies", "BoschGroup")
    respx.get(url__regex=r".*/companies/BoschGroup/postings\?.*").mock(
        return_value=httpx.Response(200, json=_SR_LIST)
    )
    respx.get(url__regex=r".*/postings/\d+$").mock(return_value=httpx.Response(500))

    jobs = smartrecruiters.fetch(["software engineer"], "")
    assert len(jobs) == 1
    assert jobs[0].description == ""


@respx.mock
def test_smartrecruiters_caps_detail_requests(monkeypatch) -> None:
    """Boards here run to thousands of reqs; one detail call per result would
    make a single refresh unbounded."""
    monkeypatch.setattr("app.config.settings.smartrecruiters_companies", "BoschGroup")
    monkeypatch.setattr(smartrecruiters, "MAX_DETAIL_FETCHES", 1)
    many = {
        "content": [
            {
                "id": str(700000000000000 + i),
                "name": "Software Engineer",
                "company": {"name": "Bosch Group"},
                "location": {"city": "Braga", "region": "Braga"},
                "releasedDate": "2026-08-27T00:00:00.000Z",
            }
            for i in range(5)
        ]
    }
    respx.get(url__regex=r".*/companies/BoschGroup/postings\?.*").mock(
        return_value=httpx.Response(200, json=many)
    )
    detail = respx.get(url__regex=r".*/postings/\d+$").mock(return_value=httpx.Response(200, json=_SR_DETAIL))

    jobs = smartrecruiters.fetch(["software engineer"], "")
    assert len(jobs) == 5
    assert detail.call_count == 1
    assert sum(1 for j in jobs if j.description) == 1


@respx.mock
def test_smartrecruiters_returns_nothing_on_an_http_error(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.smartrecruiters_companies", "BoschGroup")
    respx.get(url__regex=r".*/companies/BoschGroup/postings\?.*").mock(return_value=httpx.Response(503))
    assert smartrecruiters.fetch(["engineer"], "") == []


# ---- Credentials must not reach the logs --------------------------------


def test_describe_http_error_reports_the_status_without_the_url() -> None:
    """httpx puts the request URL in an HTTPStatusError's message, and two
    connectors carry their key in that URL."""
    request = httpx.Request("GET", "https://api.adzuna.com/v1/api?app_key=SUPERSECRET")
    exc = httpx.HTTPStatusError(
        "Client error '429 Too Many Requests' for url 'https://api.adzuna.com/v1/api?app_key=SUPERSECRET'",
        request=request,
        response=httpx.Response(429, request=request),
    )

    assert describe_http_error(exc) == "HTTP 429"


def test_describe_http_error_names_a_transport_failure() -> None:
    """No status to report, so the type is all there is -- and it is enough
    to tell a timeout from a DNS failure in the logs."""
    assert describe_http_error(httpx.ConnectTimeout("timed out")) == "ConnectTimeout"


@respx.mock
def test_adzuna_never_logs_its_api_key(monkeypatch, caplog) -> None:
    """A 429 is routine on a free tier, and a log line outlives the incident
    that produced it. This used to log the raw exception, URL and all."""
    monkeypatch.setattr("app.config.settings.adzuna_app_id", "adzuna-id-9f3c")
    monkeypatch.setattr("app.config.settings.adzuna_app_key", "adzuna-key-4b71")
    respx.get(url__startswith="https://api.adzuna.com").mock(return_value=httpx.Response(429))

    with caplog.at_level(logging.WARNING):
        assert adzuna.fetch(["Software Engineer"], "Seattle, WA") == []

    assert "adzuna-key-4b71" not in caplog.text
    assert "adzuna-id-9f3c" not in caplog.text
    assert "HTTP 429" in caplog.text  # the failure is still diagnosable


@respx.mock
def test_jooble_never_logs_its_api_key(monkeypatch, caplog) -> None:
    """Jooble's key sits in the path rather than the query string, so it
    leaks the same way."""
    monkeypatch.setattr("app.config.settings.jooble_api_key", "jooble-key-8d20")
    respx.post(url__startswith="https://jooble.org/api/").mock(return_value=httpx.Response(500))

    with caplog.at_level(logging.WARNING):
        assert jooble.fetch(["Backend Engineer"], "Seattle, WA") == []

    assert "jooble-key-8d20" not in caplog.text
    assert "HTTP 500" in caplog.text
