from . import adzuna, arbeitnow, ashby, greenhouse, jooble, lever, remotive, smartrecruiters

# Order matters only for logging/readability; ingestion treats all sources
# equally and dedups across whichever ones are configured.
REGISTRY = [adzuna, jooble, remotive, arbeitnow, greenhouse, lever, ashby, smartrecruiters]

# The bundled demo pool is not a connector -- it has no module in REGISTRY --
# but its postings carry this as their source name, so anything that offers
# the user a choice of board has to count it as one. Leaving it out would
# make the board filter reject the only value a fresh install with no
# credentials actually has.
SEED_SOURCE = "seed"


def active_sources() -> list[str]:
    return [mod.NAME for mod in REGISTRY if mod.is_configured()]


def known_source_names() -> list[str]:
    """Every board name a stored job can legitimately carry.

    Configured or not: a connector that has since had its credentials removed
    leaves its jobs in the pool, and those stay filterable.
    """
    return [mod.NAME for mod in REGISTRY] + [SEED_SOURCE]
