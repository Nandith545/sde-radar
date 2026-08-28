"""Work-mode and country inference.

The behaviour worth pinning is the refusal to guess: an unreadable posting
must come back "unknown" so the caller can skip the preference, rather than
being quietly classified and then quietly penalised.
"""

import pytest

from app.services.job_facets import infer_country, infer_work_mode, normalize_country


@pytest.mark.parametrize(
    ("location", "title", "expected"),
    [
        ("Remote (US)", "Software Engineer", "remote"),
        ("Anywhere", "Backend Engineer", "remote"),
        ("Seattle, WA", "Software Engineer (Hybrid)", "hybrid"),
        ("Berlin, Germany — Hybrid", "Engineer", "hybrid"),
        ("Austin, TX", "On-site Platform Engineer", "onsite"),
        ("Seattle, WA", "Software Engineer", "unknown"),
        ("", "", "unknown"),
    ],
)
def test_work_mode_inference(location: str, title: str, expected: str) -> None:
    assert infer_work_mode(location, title) == expected


def test_hybrid_wins_over_remote() -> None:
    """A hybrid posting nearly always says "remote" too; the reverse is rare."""
    assert infer_work_mode("Hybrid — 2 days remote", "Engineer") == "hybrid"


def test_description_is_consulted_only_after_location_and_title() -> None:
    # "remote" here describes a perk, not the role, so a location that already
    # settles the question must win.
    assert infer_work_mode("On-site, Austin TX", "Engineer", "We offer remote Fridays") == "onsite"
    # With nothing stronger available, the description is allowed to decide.
    assert infer_work_mode("", "Engineer", "This role is fully remote") == "remote"


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        ("Seattle, WA", "united states"),
        ("Austin, TX", "united states"),
        ("New York, United States", "united states"),
        ("Leipzig", "germany"),
        ("Berlin, Germany", "germany"),
        ("London", "united kingdom"),
        ("Bengaluru", "india"),
        ("Toronto", "canada"),
        ("Atlantis", "unknown"),
        ("", "unknown"),
    ],
)
def test_country_inference(location: str, expected: str) -> None:
    assert infer_country(location) == expected


def test_unrecognised_location_is_unknown_not_a_default() -> None:
    """The whole design rests on this: no guess means no penalty."""
    assert infer_country("Somewhere Nobody Listed") == "unknown"


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("USA", "united states"),
        ("usa", "united states"),
        ("United States", "united states"),
        ("Germany", "germany"),
        ("UK", "united kingdom"),
        ("", ""),
    ],
)
def test_user_input_normalizes_onto_the_same_vocabulary(typed: str, expected: str) -> None:
    assert normalize_country(typed) == expected
