"""Region vocabulary, inference and the picker endpoints."""

import datetime

import pytest
from fastapi.testclient import TestClient

from app.services.regions import (
    AMBIGUOUS_CITIES,
    COUNTRIES,
    infer_subdivision,
    locate,
    metro_of,
    state_label,
    subdivision_from_postal,
)

# ---- The dataset itself ------------------------------------------------


def test_every_country_matches_the_country_inference_vocabulary() -> None:
    """A slug here that infer_country never returns would be a country you
    could select and never match a single posting in."""
    from app.services.job_facets import _COUNTRY_ALIASES

    assert set(COUNTRIES) == set(_COUNTRY_ALIASES)


def test_subdivision_codes_are_unique_within_a_country() -> None:
    for slug, country in COUNTRIES.items():
        codes = [s.code for s in country.subdivisions]
        assert len(codes) == len(set(codes)), slug


def test_every_subdivision_has_at_least_one_city() -> None:
    """An empty state is a dead end in the picker: selectable, then offering
    nothing to select underneath it."""
    for slug, country in COUNTRIES.items():
        for sub in country.subdivisions:
            assert sub.cities, f"{slug}/{sub.code}"


def test_the_united_states_has_all_fifty_states_and_dc() -> None:
    assert len(COUNTRIES["united states"].subdivisions) == 51


def test_countries_name_their_own_tier() -> None:
    """ "State" over a list of Canadian provinces reads as a bug."""
    assert COUNTRIES["canada"].subdivision_label == "Province"
    assert COUNTRIES["united kingdom"].subdivision_label == "Nation"
    assert COUNTRIES["united states"].subdivision_label == "State"


def test_the_seed_pool_cities_are_all_in_the_table() -> None:
    """The bundled demo data is the only pool a fresh install has, so every
    one of its locations has to be placeable or the picker looks broken on
    day one."""
    from app.services.seed_jobs import SEED_JOBS

    for job in SEED_JOBS:
        assert infer_subdivision(job["location"], "united states"), job["location"]


# ---- Inference ---------------------------------------------------------


@pytest.mark.parametrize(
    ("location", "country", "expected"),
    [
        ("Seattle, WA", "united states", "WA"),
        ("Austin, TX", "united states", "TX"),
        ("Bellevue, WA (Hybrid)", "united states", "WA"),
        ("Toronto", "canada", "ON"),
        ("Bengaluru", "india", "KA"),
        ("Sydney", "australia", "NSW"),
        ("Amsterdam", "netherlands", "NH"),
        ("Edinburgh", "united kingdom", "SCT"),
    ],
)
def test_locations_resolve_to_their_subdivision(location: str, country: str, expected: str) -> None:
    assert infer_subdivision(location, country) == expected


@pytest.mark.parametrize(
    "location",
    ["Remote (USA)", "Unspecified", "", "Anywhere", "Remote"],
)
def test_an_unplaceable_location_reports_unknown_rather_than_guessing(location: str) -> None:
    """Empty means "could not tell". The caller must skip the preference, not
    treat the posting as failing it."""
    assert infer_subdivision(location, "united states") == ""


def test_a_city_in_two_states_reports_unknown_without_a_code() -> None:
    """Portland is in Oregon and Maine. Picking a favourite would file half
    of those postings under a state they are not in."""
    assert infer_subdivision("Portland", "united states") == ""
    assert infer_subdivision("Portland, OR", "united states") == "OR"
    assert infer_subdivision("Portland, ME", "united states") == "ME"


def test_ambiguous_names_are_reported_not_silently_dropped() -> None:
    assert "portland" in AMBIGUOUS_CITIES["united states"]
    assert "springfield" in AMBIGUOUS_CITIES["united states"]
    assert "seattle" not in AMBIGUOUS_CITIES["united states"]


@pytest.mark.parametrize(
    ("written", "country", "expected"),
    [
        ("München", "germany", "Munich"),
        ("Munich", "germany", "Munich"),
        ("Köln", "germany", "Cologne"),
        ("Bangalore", "india", "Bengaluru"),
        ("Bengaluru", "india", "Bengaluru"),
        ("Den Haag", "netherlands", "The Hague"),
    ],
)
def test_a_city_resolves_to_one_option_whichever_name_a_board_used(
    written: str, country: str, expected: str
) -> None:
    """Arbeitnow says München and Adzuna says Munich. Two rows for one city
    would be a picker bug, and splitting the count across them a worse one."""
    assert locate(written, country)[1] == expected


def test_a_two_letter_token_is_only_read_as_a_code_where_addresses_use_them() -> None:
    """German addresses don't write "BE" for Berlin, so a stray "BE" in a
    location string must not become one."""
    assert infer_subdivision("BE Consulting GmbH, Hamburg", "germany") == "HH"


def test_state_label_falls_back_to_the_code() -> None:
    assert state_label("united states", "WA") == "Washington"
    assert state_label("united states", "ZZ") == "ZZ"


# ---- Postal codes ------------------------------------------------------


@pytest.mark.parametrize(
    ("country", "code", "expected"),
    [
        ("united states", "98052", "WA"),
        ("united states", "98052-8300", "WA"),  # ZIP+4 still resolves
        ("united states", "94043", "CA"),
        ("united states", "10001", "NY"),
        ("canada", "M5V 3A8", "ON"),
        ("canada", "V6B1A1", "BC"),
        ("australia", "2000", "NSW"),
        ("australia", "6000", "WA"),
    ],
)
def test_postal_codes_resolve(country: str, code: str, expected: str) -> None:
    assert subdivision_from_postal(country, code) == expected


@pytest.mark.parametrize(
    ("country", "code"),
    [
        ("germany", "80331"),  # unsupported country
        ("united states", "00000"),  # in no range
        ("united states", "abc"),  # not a code at all
        ("united states", "981"),  # too short to place
        ("canada", "X0A 0H0"),  # X spans two territories
        ("united states", ""),
    ],
)
def test_an_unresolvable_postal_code_returns_nothing(country: str, code: str) -> None:
    """A bad guess here gets written into someone's own address, so silence
    beats a plausible-looking wrong answer."""
    assert subdivision_from_postal(country, code) == ""


# ---- The picker endpoints ---------------------------------------------


def test_listing_countries_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/regions").status_code == 401


def test_countries_are_listed_with_their_tier_label(client: TestClient, registered_user: dict) -> None:
    countries = client.get("/api/regions", headers=registered_user["headers"]).json()
    canada = next(c for c in countries if c["slug"] == "canada")

    assert canada["label"] == "Canada"
    assert canada["subdivision_label"] == "Province"
    assert canada["supports_postal_lookup"] is True
    assert next(c for c in countries if c["slug"] == "germany")["supports_postal_lookup"] is False


def test_country_detail_carries_states_and_their_cities(client: TestClient, registered_user: dict) -> None:
    body = client.get("/api/regions/united states", headers=registered_user["headers"]).json()
    wa = next(s for s in body["subdivisions"] if s["code"] == "WA")

    assert wa["label"] == "Washington"
    assert "Seattle" in [c["name"] for c in wa["cities"]]


def test_an_alias_country_name_resolves(client: TestClient, registered_user: dict) -> None:
    """A preference saved as "USA" through the old free-text box still has to
    open its own picker."""
    body = client.get("/api/regions/USA", headers=registered_user["headers"]).json()
    assert body["slug"] == "united states"


def test_an_unknown_country_is_a_404_naming_the_known_ones(client: TestClient, registered_user: dict) -> None:
    response = client.get("/api/regions/atlantis", headers=registered_user["headers"])
    assert response.status_code == 404
    assert "united states" in response.json()["detail"]


def test_job_counts_reflect_the_pool(client: TestClient, registered_user: dict, db, make_job) -> None:
    for i in range(3):
        db.add(make_job(external_id=f"t:{i}", location="Seattle, WA", dedup_key=f"k{i}"))
    db.add(make_job(external_id="t:x", location="Austin, TX", dedup_key="kx"))
    db.commit()

    body = client.get("/api/regions/united states", headers=registered_user["headers"]).json()
    states = {s["code"]: s for s in body["subdivisions"]}

    assert states["WA"]["job_count"] == 3
    assert states["TX"]["job_count"] == 1
    assert states["ND"]["job_count"] == 0
    seattle = next(c for c in states["WA"]["cities"] if c["name"] == "Seattle")
    assert seattle["job_count"] == 3


def test_counts_ignore_postings_past_the_age_ceiling(
    client: TestClient, registered_user: dict, db, make_job
) -> None:
    db.add(
        make_job(
            external_id="t:old",
            location="Seattle, WA",
            posted=(datetime.date.today() - datetime.timedelta(days=45)).isoformat(),
        )
    )
    db.commit()

    body = client.get("/api/regions/united states", headers=registered_user["headers"]).json()
    wa = next(s for s in body["subdivisions"] if s["code"] == "WA")
    assert wa["job_count"] == 0


def test_states_stay_in_table_order_regardless_of_counts(
    client: TestClient, registered_user: dict, db, make_job
) -> None:
    """A picker whose rows reshuffle as the pool changes is one you cannot
    learn the shape of."""
    db.add(make_job(external_id="t:1", location="Austin, TX"))
    db.commit()

    body = client.get("/api/regions/united states", headers=registered_user["headers"]).json()
    assert [s["code"] for s in body["subdivisions"]][:3] == ["AL", "AK", "AZ"]


def test_postal_lookup_returns_the_state_and_its_cities(client: TestClient, registered_user: dict) -> None:
    body = client.get("/api/regions/united states/postal/98052", headers=registered_user["headers"]).json()

    assert body["code"] == "WA"
    assert body["label"] == "Washington"
    assert "Redmond" in body["cities"]


def test_an_unresolvable_postal_lookup_is_a_404(client: TestClient, registered_user: dict) -> None:
    response = client.get("/api/regions/germany/postal/80331", headers=registered_user["headers"])
    assert response.status_code == 404


# ---- Commute markets ----------------------------------------------------


def test_seattle_suburbs_share_a_metro() -> None:
    """The whole point: a Redmond posting is not "not Seattle" to anyone
    actually job-hunting here."""
    metro = metro_of("united states", "Seattle, WA")
    assert metro
    for city in ("Bellevue, WA", "Redmond, WA", "Kirkland, WA", "Renton, WA", "Bothell, WA"):
        assert metro_of("united states", city) == metro, city


def test_a_metro_can_span_subdivisions() -> None:
    """Delhi NCR covers Delhi, Haryana and Uttar Pradesh, so a state-level
    rule could not have expressed it."""
    ncr = metro_of("india", "New Delhi")
    assert ncr
    assert metro_of("india", "Noida") == ncr
    assert metro_of("india", "Gurugram, Haryana") == ncr


def test_somewhere_outside_any_metro_is_unknown() -> None:
    """Bremerton is across the Puget Sound -- a ferry, not a commute -- and
    an unknown location must fall back to the exact match rather than being
    quietly folded into the nearest city."""
    assert metro_of("united states", "Bremerton, WA") == ""
    assert metro_of("united states", "Spokane, WA") == ""


def test_ambiguous_city_names_are_left_out_of_the_metro_index() -> None:
    """Portland is in Oregon and Maine, and this index is keyed by country
    only -- so including it would file Portland, Maine postings in the Oregon
    commute market. Same reasoning the city index already applies."""
    assert metro_of("united states", "Portland, OR") == ""


def test_an_unknown_country_has_no_metros() -> None:
    assert metro_of("", "Seattle, WA") == ""
    assert metro_of("atlantis", "Seattle, WA") == ""
