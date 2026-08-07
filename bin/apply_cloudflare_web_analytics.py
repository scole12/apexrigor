#!/usr/bin/env python3
"""Install one Cloudflare Web Analytics beacon on each active public route.

The site token is intentionally supplied by the deployment environment. It is
not guessed, synthesized, or copied from another Cloudflare resource.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
TOKEN_RE = re.compile(r"^[0-9a-fA-F]{32}$")
BLOCK_RE = re.compile(
    r"\s*<!-- Cloudflare Web Analytics -->.*?"
    r"<!-- End Cloudflare Web Analytics -->\s*",
    re.DOTALL,
)
BEACON_URL = "https://static.cloudflareinsights.com/beacon.min.js"


def beacon_block(token: str) -> str:
    return (
        "<!-- Cloudflare Web Analytics -->\n"
        f'<script defer src="{BEACON_URL}" '
        f"data-cf-beacon='{{\"token\":\"{token.lower()}\"}}'></script>\n"
        "<!-- End Cloudflare Web Analytics -->"
    )


def install(path: Path, token: str) -> None:
    original = path.read_text(encoding="utf-8")
    cleaned = BLOCK_RE.sub("\n", original)
    if BEACON_URL in cleaned:
        raise RuntimeError(f"unmanaged Cloudflare beacon remains in {path}")
    if "</body>" not in cleaned:
        raise RuntimeError(f"missing </body> in {path}")
    rendered = cleaned.replace(
        "</body>", f"{beacon_block(token)}\n</body>", 1
    )
    if rendered.count(BEACON_URL) != 1:
        raise RuntimeError(f"beacon cardinality is not one in {path}")
    if rendered != original:
        path.write_text(rendered, encoding="utf-8")


def active_outputs(root: Path) -> tuple[Path, ...]:
    return (
        root / "index.html",
        root / "picks.html",
        root / "picks" / "index.html",
        root / "results.html",
        root / "results" / "index.html",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="report owner action instead of failing when the site token is absent",
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
    token = os.environ.get("CLOUDFLARE_WEB_ANALYTICS_SITE_TOKEN", "").strip()
    if not token:
        print("CLOUDFLARE_WEB_ANALYTICS=OWNER_ACTION_REQUIRED")
        print("RUM_BEACON_PUBLIC_ROUTE_COUNT=0")
        return 0 if args.allow_missing else 3
    if not TOKEN_RE.fullmatch(token):
        print("invalid CLOUDFLARE_WEB_ANALYTICS_SITE_TOKEN", file=sys.stderr)
        return 2
    for output in active_outputs(root):
        if not output.is_file():
            print(f"missing active public output: {output}", file=sys.stderr)
            return 2
        install(output, token)
    print("CLOUDFLARE_WEB_ANALYTICS=ACTIVE")
    print("RUM_BEACON_PER_PUBLIC_ROUTE=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
