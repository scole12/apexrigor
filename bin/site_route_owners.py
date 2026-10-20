"""One registry of which sport owns which site path (issue #23).

Every public page and every published data file belongs to exactly one owner.
A sport's publication may change only paths that sport owns; ``SHARED`` paths
(site-wide chrome, assets, the fused all-sports record) are never written by a
sport publication.  Adding a sport means adding its entry here; the CI test
``tests/test_job1_route_owners.py`` fails when a built page has no owner.
"""

from __future__ import annotations

from pathlib import PurePosixPath

# The three navigation routes (picks, results, about) of each sport.
SPORT_ROUTES: dict[str, tuple[str, ...]] = {
    "MLB": (
        "index.html",
        "picks.html",
        "picks/index.html",
        "results.html",
        "results/index.html",
        "about/index.html",
    ),
    "NCAAF": ("ncaaf/index.html", "ncaaf/results/index.html", "ncaaf/about/index.html"),
    "MMA": ("mma/index.html", "mma/results/index.html", "mma/about/index.html"),
    "NFL": ("nfl/index.html", "nfl/results/index.html", "nfl/about/index.html"),
    "NHL": ("nhl/index.html", "nhl/results/index.html", "nhl/about/index.html"),
    "NBA": ("nba/index.html", "nba/results/index.html", "nba/about/index.html"),
}

# Everything else a sport owns: its page directory and its data files.
SPORT_PREFIXES: dict[str, tuple[str, ...]] = {
    "MLB": ("data/mlb_", "data/results_"),
    "NCAAF": ("ncaaf/", "data/ncaaf/", "data/ncaaf_"),
    "MMA": ("mma/", "data/mma_"),
    "NFL": ("nfl/", "data/nfl_"),
    "NHL": ("nhl/", "data/nhl_"),
    "NBA": ("nba/", "data/nba_"),
}

SHARED = "SHARED"
SHARED_PREFIXES = ("assets/", "data/apex_")
SHARED_FILES = frozenset({
    "favicon.svg",
    "favicon.ico",
    "favicon-16x16.png",
    "favicon-32x32.png",
    "apple-touch-icon.png",
    "android-chrome-192x192.png",
    "android-chrome-512x512.png",
    "og-image.png",
    "site.webmanifest",
    "data/README.txt",
})

SPORTS = tuple(SPORT_ROUTES)


def route_paths() -> frozenset[str]:
    """Every sport navigation route (the publisher's ROUTE_PATHS)."""
    return frozenset(path for paths in SPORT_ROUTES.values() for path in paths)


def owner_of(relative: str) -> str | None:
    """The owner of a site-relative path, or None when no owner is declared."""
    path = PurePosixPath(relative).as_posix()
    for sport, paths in SPORT_ROUTES.items():
        if path in paths:
            return sport
    if path in SHARED_FILES or path.startswith(SHARED_PREFIXES):
        return SHARED
    owners = [sport for sport, prefixes in SPORT_PREFIXES.items() if path.startswith(prefixes)]
    if len(owners) == 1:
        return owners[0]
    return None


def owned_by(sport: str, relative: str) -> bool:
    return owner_of(relative) == sport.upper()


def foreign_paths(sport: str, paths) -> list[str]:
    """Paths in ``paths`` that ``sport`` does not own (sorted)."""
    return sorted(path for path in paths if not owned_by(sport, path))
