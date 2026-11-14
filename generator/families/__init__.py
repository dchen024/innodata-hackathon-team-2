"""Registry of diagram families. Add each new family here."""
from generator.families.subway.family import SubwayFamily

FAMILIES = {f.name: f for f in (SubwayFamily(),)}


def get_family(name):
    if name not in FAMILIES:
        raise SystemExit(f"unknown family {name!r}; available: {', '.join(FAMILIES) or 'none yet'}")
    return FAMILIES[name]
