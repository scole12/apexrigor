#!/usr/bin/env python3
"""Install the official Vercel Web Analytics HTML snippet in each public head.

Static HTML integration from Vercel docs:
  window.va / window.vaq queue, then defer /_vercel/insights/script.js
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_URL = "/_vercel/insights/script.js"
BLOCK_RE = re.compile(
    r"\s*<!-- Vercel Web Analytics -->.*?"
    r"<!-- End Vercel Web Analytics -->\s*",
    re.DOTALL,
)
ANALYTICS_BLOCK = (
    "<!-- Vercel Web Analytics -->"
    "<script>"
    "window.va = window.va || function () { "
    "(window.vaq = window.vaq || []).push(arguments); "
    "};"
    "</script>"
    f'<script defer src="{SCRIPT_URL}"></script>'
    "<!-- End Vercel Web Analytics -->"
)


def install(path: Path) -> None:
    original = path.read_text(encoding="utf-8")
    cleaned = BLOCK_RE.sub("\n", original)
    if SCRIPT_URL in cleaned:
        raise RuntimeError(f"unmanaged Vercel Analytics script remains in {path}")
    if "</head>" not in cleaned:
        raise RuntimeError(f"missing </head> in {path}")
    rendered = cleaned.replace("</head>", f"{ANALYTICS_BLOCK}\n</head>", 1)
    if rendered.count(SCRIPT_URL) != 1 or rendered.count(ANALYTICS_BLOCK) != 1:
        raise RuntimeError(f"Vercel Analytics cardinality is not one in {path}")
    if rendered != original:
        path.write_text(rendered, encoding="utf-8")


def active_outputs(root: Path) -> tuple[Path, ...]:
    return (
        root / "index.html",
        root / "picks.html",
        root / "picks" / "index.html",
        root / "results.html",
        root / "results" / "index.html",
        root / "about" / "index.html",
        root / "ncaaf" / "index.html",
        root / "ncaaf" / "results" / "index.html",
        root / "ncaaf" / "about" / "index.html",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="retained for compatibility with the existing Vercel build command",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help="site-output root; defaults to the canonical working tree",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        print(f"site-output root is not a directory: {root}", file=sys.stderr)
        return 2
    for output in active_outputs(root):
        if not output.is_file():
            print(f"missing active public output: {output}", file=sys.stderr)
            return 2
        install(output)
    print("VERCEL_WEB_ANALYTICS=ACTIVE")
    print("VERCEL_INSIGHTS_SCRIPT_PER_PUBLIC_ROUTE=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
