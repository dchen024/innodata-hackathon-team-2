"""Registry of diagram families. Add each new family here."""
FAMILIES = {}   # name -> Family instance, e.g. {"transit_map": TransitMapFamily()}


def get_family(name):
    if name not in FAMILIES:
        raise SystemExit(f"unknown family {name!r}; available: {', '.join(FAMILIES) or 'none yet'}")
    return FAMILIES[name]
