from . import adzuna, jooble, remotive, arbeitnow

# Order matters only for logging/readability; ingestion treats all sources
# equally and dedups across whichever ones are configured.
REGISTRY = [adzuna, jooble, remotive, arbeitnow]


def active_sources() -> list[str]:
    return [mod.NAME for mod in REGISTRY if mod.is_configured()]
