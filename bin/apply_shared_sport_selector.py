#!/usr/bin/env python3
"""Idempotently preserve the three-sport selector in generated public HTML.

MLB and NCAA retain ownership of their page bodies. This post-build boundary
only restores shared navigation after a sport-specific generator refreshes a
page from its sealed release template.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


ROUTES = {
    "index.html": ("mlb", "picks"),
    "picks.html": ("mlb", "picks"),
    "picks/index.html": ("mlb", "picks"),
    "results.html": ("mlb", "results"),
    "results/index.html": ("mlb", "results"),
    "about/index.html": ("mlb", "about"),
    "ncaaf/index.html": ("ncaaf", "picks"),
    "ncaaf/results/index.html": ("ncaaf", "results"),
    "ncaaf/about/index.html": ("ncaaf", "about"),
    "mma/index.html": ("mma", "picks"),
    "mma/results/index.html": ("mma", "results"),
    "mma/about/index.html": ("mma", "about"),
}

STACK_RE = re.compile(
    r'<div class="apex-nav-stack">\s*<nav class="sport-nav".*?</nav>\s*'
    r'<nav class="section-nav".*?</nav>\s*</div>',
    re.DOTALL,
)
LEGACY_RE = re.compile(r'<nav class="nav">.*?</nav>', re.DOTALL)


def anchor(href: str, label: str, active: bool) -> str:
    attrs = ' class="active" aria-current="true"' if active else ""
    return f'    <a href="{href}"{attrs}>{label}</a>'


def navigation(sport: str, section: str) -> str:
    sport_targets = {
        "picks": ("/", "/ncaaf", "/mma"),
        "results": ("/results", "/ncaaf/results", "/mma/results"),
        "about": ("/about", "/ncaaf/about", "/mma/about"),
    }[section]
    section_targets = {
        "mlb": ("/", "/results", "/about"),
        "ncaaf": ("/ncaaf", "/ncaaf/results", "/ncaaf/about"),
        "mma": ("/mma", "/mma/results", "/mma/about"),
    }[sport]
    sport_lines = [
        anchor(sport_targets[0], "MLB", sport == "mlb"),
        anchor(sport_targets[1], "NCAA FOOTBALL", sport == "ncaaf"),
        anchor(sport_targets[2], "MMA / UFC", sport == "mma"),
    ]
    section_lines = [
        anchor(section_targets[0], "PICKS", section == "picks"),
        anchor(section_targets[1], "RESULTS", section == "results"),
        anchor(section_targets[2], "ABOUT", section == "about"),
    ]
    return (
        '  <div class="apex-nav-stack">\n'
        '  <nav class="sport-nav" aria-label="Sport selector">\n'
        + "\n".join(sport_lines)
        + '\n  </nav>\n  <nav class="section-nav" aria-label="'
        + {"mlb": "MLB", "ncaaf": "NCAA Football", "mma": "MMA"}[sport]
        + ' sections">\n'
        + "\n".join(section_lines)
        + "\n  </nav>\n  </div>"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--allow-missing", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    changed = 0
    for relative, (sport, section) in ROUTES.items():
        path = root / relative
        if not path.is_file():
            if args.allow_missing:
                continue
            raise FileNotFoundError(path)
        text = path.read_text(encoding="utf-8")
        replacement = navigation(sport, section)
        current_stack = STACK_RE.search(text)
        if current_stack and all(
            label in current_stack.group(0)
            for label in ("MLB", "NCAA FOOTBALL", "MMA / UFC")
        ):
            updated, count = text, 1
        elif current_stack:
            updated, count = STACK_RE.subn(replacement, text, count=1)
        else:
            updated, count = LEGACY_RE.subn(replacement, text, count=1)
        if count != 1:
            raise RuntimeError(f"unable to resolve one navigation block: {path}")
        if updated.count('<nav class="sport-nav"') != 1:
            raise RuntimeError(f"sport selector cardinality invalid: {path}")
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            changed += 1
    print(f"SHARED_SPORT_SELECTOR=PASS changed={changed} routes={len(ROUTES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
