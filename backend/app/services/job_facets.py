"""Derives work mode and country from a job posting's free text.

Neither is a field any board gives us. `JobListing` stores a freeform
`location` string and a description, so both facets are inferred, and the
inference is wrong sometimes. Everything here is therefore built to fail
quiet: an unrecognised posting comes back as "unknown" rather than being
guessed at, and the caller is expected to skip the preference rather than
penalise a job it could not read.

That asymmetry is deliberate. Scoring a job lower because we could not
classify it would hide real matches for a reason the user can never see.
"""

# Ordered: "hybrid" wins over "remote" because a hybrid posting almost always
# says "remote" too ("2 days remote, 3 in office"), and the reverse is rare.
_HYBRID_HINTS = ("hybrid", "partially remote", "part remote", "flexible working model")
_REMOTE_HINTS = (
    "remote",
    "work from home",
    "wfh",
    "fully distributed",
    "telecommute",
    "anywhere",
)
_ONSITE_HINTS = ("on-site", "onsite", "in office", "in-office", "on site")


def infer_work_mode(location: str, title: str = "", description: str = "") -> str:
    """Return "remote", "hybrid", "onsite", or "unknown".

    Location and title are trusted before the description: a description can
    mention "remote" while describing a benefit, a perk, or a policy the role
    itself doesn't have.
    """
    strong = f"{location} {title}".lower()
    for hint in _HYBRID_HINTS:
        if hint in strong:
            return "hybrid"
    for hint in _REMOTE_HINTS:
        if hint in strong:
            return "remote"
    for hint in _ONSITE_HINTS:
        if hint in strong:
            return "onsite"

    body = (description or "").lower()
    for hint in _HYBRID_HINTS:
        if hint in body:
            return "hybrid"
    for hint in _REMOTE_HINTS:
        if hint in body:
            return "remote"
    for hint in _ONSITE_HINTS:
        if hint in body:
            return "onsite"

    # A posting that names a city and never mentions remote is *probably*
    # onsite, but "probably" is exactly what this module refuses to do.
    return "unknown"


# Aliases that positively identify a country in a location string. Cities are
# listed only for countries the connectors actually return, because that is
# where the signal is: Arbeitnow answers with bare German city names, and
# without these a German posting would read as country-unknown forever.
#
# This is not a geocoder and will not become one. Anything not listed reports
# "unknown", which the caller treats as "don't apply the preference".
_COUNTRY_ALIASES: dict[str, tuple[str, ...]] = {
    "united states": (
        "united states",
        "usa",
        "u.s.a",
        "u.s.",
        " us ",
        "america",
    ),
    "united kingdom": (
        "united kingdom",
        "uk",
        "england",
        "scotland",
        "wales",
        "london",
        "manchester",
        "edinburgh",
        "bristol",
        "cambridge",
    ),
    "germany": (
        "germany",
        "deutschland",
        "berlin",
        "munich",
        "münchen",
        "hamburg",
        "frankfurt",
        "cologne",
        "köln",
        "stuttgart",
        "düsseldorf",
        "leipzig",
        "dresden",
        "nuremberg",
    ),
    "canada": (
        "canada",
        "toronto",
        "vancouver",
        "montreal",
        "ottawa",
        "calgary",
    ),
    "india": (
        "india",
        "bengaluru",
        "bangalore",
        "hyderabad",
        "pune",
        "mumbai",
        "chennai",
        "noida",
        "gurgaon",
        "gurugram",
    ),
    "netherlands": ("netherlands", "amsterdam", "rotterdam", "utrecht", "eindhoven"),
    "australia": ("australia", "sydney", "melbourne", "brisbane", "perth"),
    "ireland": ("ireland", "dublin"),
}

# "Seattle, WA" is the dominant shape of US postings in this data, and no
# country token appears anywhere in it. Two-letter state codes are the only
# reliable signal. "WA" is also Western Australia, which is why this is
# consulted only after the alias table above finds nothing.
_US_STATE_CODES = frozenset(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS "
    "MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV "
    "WI WY DC".split()
)


def infer_country(location: str) -> str:
    """Return a lowercase country name, or "unknown".

    Only positive identification counts. A location this doesn't recognise is
    unknown, never a default.
    """
    if not location:
        return "unknown"
    text = f" {location.lower()} ".replace(",", " ")

    for country, aliases in _COUNTRY_ALIASES.items():
        for alias in aliases:
            needle = alias if alias.startswith(" ") else f" {alias}"
            if needle in text or f" {alias} " in text:
                return country

    # Trailing state code, as in "Austin, TX" or "Seattle, WA (Hybrid)".
    for token in location.replace(",", " ").split():
        if token.upper() in _US_STATE_CODES and token.isalpha() and len(token) == 2:
            return "united states"

    return "unknown"


def normalize_country(value: str) -> str:
    """Map whatever the user typed onto the same vocabulary as infer_country.

    Lets someone type "USA", "U.S." or "United States" and still be compared
    against a posting resolved to "united states".
    """
    if not value:
        return ""
    text = f" {value.strip().lower()} "
    for country, aliases in _COUNTRY_ALIASES.items():
        if text.strip() == country:
            return country
        for alias in aliases:
            if text.strip() == alias.strip():
                return country
    return value.strip().lower()
