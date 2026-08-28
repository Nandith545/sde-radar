"""Free-text salary parsing, used by connectors whose APIs return a string
like "$120k - $150k a year" rather than structured numbers."""

import pytest

from app.services.sources.salary_parse import parse_salary_text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("$100,000 - $130,000 a year", (100000.0, 130000.0, "year")),
        ("$50 - $70 an hour", (50.0, 70.0, "hour")),
        ("120k - 150k", (120000.0, 150000.0, "year")),
        ("$95000", (95000.0, 95000.0, "year")),
        ("$45/hr", (45.0, 45.0, "hour")),
    ],
)
def test_parses_common_salary_formats(text: str, expected: tuple) -> None:
    assert parse_salary_text(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Competitive salary",
        "DOE",
        "Negotiable",
        None,
    ],
)
def test_unparseable_input_yields_no_numbers_rather_than_guessing(text) -> None:
    comp_min, comp_max, unit = parse_salary_text(text or "")
    assert comp_min is None
    assert comp_max is None
    assert unit == "year"


def test_hourly_rates_are_not_misread_as_annual() -> None:
    """A $50/hr rate stored as $50/year would rank the job near the bottom of
    every list -- worth pinning explicitly."""
    _, _, unit = parse_salary_text("$50 - $70 an hour")
    assert unit == "hour"


def test_range_ordering_is_preserved() -> None:
    comp_min, comp_max, _ = parse_salary_text("$100,000 - $130,000 a year")
    assert comp_min is not None and comp_max is not None
    assert comp_min <= comp_max
