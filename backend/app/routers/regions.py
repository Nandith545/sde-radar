"""Country / state / city vocabulary for the settings pickers.

The lists themselves are static (`services/regions.py`); what this router
adds is how many postings are currently in each place, so the picker can say
where the jobs actually are instead of offering 51 identical-looking states.

Counts come from the same age-limited pool the dashboard reads, and they
deliberately ignore the caller's own preferences: the question a picker
answers is "is there anything here", which must not depend on the filter the
user is in the middle of changing.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user
from ..services.job_facets import MAX_AGE_DAYS, job_age_days, normalize_country
from ..services.regions import (
    COUNTRIES,
    POSTAL_COUNTRIES,
    locate,
    state_label,
    subdivision_from_postal,
)

router = APIRouter(prefix="/api/regions", tags=["regions"])


def _country_or_404(slug: str) -> str:
    """Resolve whatever the caller passed onto a known country slug.

    Accepts the aliases `normalize_country` understands ("USA", "U.S."), so a
    preference saved before this endpoint existed still resolves.
    """
    resolved = normalize_country(slug)
    if resolved not in COUNTRIES:
        raise HTTPException(
            status_code=404,
            detail=f"No region data for '{slug}'. Known: {', '.join(sorted(COUNTRIES))}.",
        )
    return resolved


def _counts(db: Session, country_slug: str) -> tuple[dict[str, int], dict[str, int]]:
    """(jobs per subdivision, jobs per city) across the visible pool.

    One pass over the postings, resolving each location once. A posting whose
    location cannot be placed contributes to neither tally rather than to a
    catch-all bucket -- an "unknown" row in a picker is not something anyone
    can select.
    """
    by_state: dict[str, int] = {}
    by_city: dict[str, int] = {}
    for job in db.query(models.JobListing).all():
        age = job_age_days(job.posted or "", job.created_at)
        if age is not None and age > MAX_AGE_DAYS:
            continue
        code, city = locate(job.location or "", country_slug)
        if code:
            by_state[code] = by_state.get(code, 0) + 1
        if city:
            by_city[city] = by_city.get(city, 0) + 1
    return by_state, by_city


@router.get("", response_model=list[schemas.CountryOut])
def list_countries(_: models.User = Depends(get_current_user)):
    """Every country the connectors serve, which is the same list the country
    inference recognises. A country outside it could be typed into the old
    free-text box but never matched a posting."""
    return [
        schemas.CountryOut(
            slug=c.slug,
            label=c.label,
            subdivision_label=c.subdivision_label,
            supports_postal_lookup=c.slug in POSTAL_COUNTRIES,
        )
        for c in sorted(COUNTRIES.values(), key=lambda c: c.label)
    ]


@router.get("/{country}", response_model=schemas.CountryDetailOut)
def country_detail(
    country: str,
    _: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    slug = _country_or_404(country)
    data = COUNTRIES[slug]
    by_state, by_city = _counts(db, slug)

    return schemas.CountryDetailOut(
        slug=data.slug,
        label=data.label,
        subdivision_label=data.subdivision_label,
        supports_postal_lookup=slug in POSTAL_COUNTRIES,
        subdivisions=[
            schemas.SubdivisionOut(
                code=sub.code,
                label=sub.label,
                job_count=by_state.get(sub.code, 0),
                cities=[schemas.CityOut(name=city, job_count=by_city.get(city, 0)) for city in sub.cities],
            )
            # Kept in table order rather than sorted by count: a picker whose
            # rows reshuffle every time the pool changes is one you cannot
            # learn the shape of.
            for sub in data.subdivisions
        ],
    )


@router.get("/{country}/postal/{postal_code}", response_model=schemas.PostalLookupOut)
def postal_lookup(
    country: str,
    postal_code: str,
    _: models.User = Depends(get_current_user),
):
    """Resolve a postal code to a subdivision, for the profile address.

    404 when it cannot be resolved -- an unsupported country, a malformed
    code, or one falling in a range two subdivisions share. The caller leaves
    the picker untouched in all three cases, so a bad guess is never written
    into someone's own address.
    """
    slug = _country_or_404(country)
    code = subdivision_from_postal(slug, postal_code)
    if not code:
        raise HTTPException(status_code=404, detail=f"Couldn't place '{postal_code}'.")

    cities = next((s.cities for s in COUNTRIES[slug].subdivisions if s.code == code), ())
    return schemas.PostalLookupOut(code=code, label=state_label(slug, code), cities=list(cities))
