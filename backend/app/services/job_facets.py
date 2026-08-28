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


# Kept here beside the other inference so the vocabulary lives in one place.
_ENTRY_WORDS = (
    "junior",
    "jr.",
    "jr ",
    "entry level",
    "entry-level",
    "intern",
    "internship",
    "new grad",
    "graduate",
)
_SENIOR_WORDS = (
    "senior",
    "sr.",
    "sr ",
    "staff",
    "principal",
    "lead",
    "l5",
    "l6",
    "sde ii",
    "sde2",
    "sde 2",
    "sde iii",
    " iii",
    " iv",
    "architect",
)


def infer_seniority(title: str) -> str:
    """Return "entry", "senior" or "mid" from a job title.

    Unlike work mode, an absent marker here is real signal rather than a gap.
    Employers label junior and senior explicitly and leave mid-level roles
    bare -- "Software Engineer" with no qualifier is the industry's way of
    saying mid. So this returns "mid" for an unmarked title instead of
    "unknown", and the caller is safe to act on it.

    Senior is checked first: "Senior Software Engineer, New Grad Program" is
    a senior req that mentions a programme, not an entry-level role.
    """
    text = f" {(title or '').lower()} "
    for word in _SENIOR_WORDS:
        if word in text:
            return "senior"
    for word in _ENTRY_WORDS:
        if word in text:
            return "entry"
    return "mid"


def seniority_from_years(years: float | None) -> str:
    """Map resume experience onto the same three levels.

    Used only when the user hasn't stated a preference, so that someone who
    never opens settings still gets sensible ordering rather than the blanket
    "junior roles are bad" assumption this replaces.
    """
    if years is None:
        return ""
    if years < 2:
        return "entry"
    if years < 7:
        return "mid"
    return "senior"


_LEVEL_ORDER = {"entry": 0, "mid": 1, "senior": 2}


def seniority_distance(a: str, b: str) -> int:
    """How many rungs apart two levels are, or -1 if either is unreadable."""
    if a not in _LEVEL_ORDER or b not in _LEVEL_ORDER:
        return -1
    return abs(_LEVEL_ORDER[a] - _LEVEL_ORDER[b])


# 40 hours x 52 weeks. Matches the frontend's own conversion when it sorts by
# compensation, so a job cannot rank differently in the list than in scoring.
HOURS_PER_YEAR = 2080


def annual_comp(comp_min: float | None, comp_max: float | None, comp_unit: str) -> float | None:
    """Best-case annual pay for a posting, or None when it publishes no range.

    None is the common case -- most boards omit salary entirely -- and it
    means "unknown", never "zero". A caller must skip the salary preference
    rather than treat an unpublished range as failing it.
    """
    best = comp_max if comp_max else comp_min
    if not best:
        return None
    return best * HOURS_PER_YEAR if comp_unit == "hour" else best
