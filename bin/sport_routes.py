"""Declared ownership for every public HTML route; shared tools consume this registry."""

SPORT_ROUTES = {
    "MLB": {
        "index.html": "picks",
        "picks.html": "picks",
        "picks/index.html": "picks",
        "results.html": "results",
        "results/index.html": "results",
        "about/index.html": "about",
    },
    **{
        sport: {
            f"{sport.lower()}/index.html": "picks",
            f"{sport.lower()}/results/index.html": "results",
            f"{sport.lower()}/about/index.html": "about",
        }
        for sport in ("NCAAF", "MMA", "NFL", "NHL", "NBA")
    },
}
ROUTE_OWNERS = {
    path: sport for sport, routes in SPORT_ROUTES.items() for path in routes
}
if len(ROUTE_OWNERS) != sum(map(len, SPORT_ROUTES.values())):
    raise RuntimeError("public route has multiple owners")


def navigation_routes(sport):
    return {
        path: (sport.lower(), section) for path, section in SPORT_ROUTES[sport].items()
    }

# Retained historical URLs remain deployable, but are not active publication outputs.
LEGACY_ROUTE_OWNERS = {
    'mma/four-markets/index.html': 'MMA',
    'mma/research/2026-09-05/index.html': 'MMA',
    'nfl/three-teamer/index.html': 'NFL',
}
PUBLIC_ROUTE_OWNERS = {**ROUTE_OWNERS, **LEGACY_ROUTE_OWNERS}
