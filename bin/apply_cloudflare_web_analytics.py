#!/usr/bin/env python3
"""Install the owner-provided Cloudflare Web Analytics beacon in each head."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
BLOCK_RE = re.compile(
    r"\s*<!-- Cloudflare Web Analytics -->.*?"
    r"<!-- End Cloudflare Web Analytics -->\s*",
    re.DOTALL,
)
BEACON_URL = "https://static.cloudflareinsights.com/beacon.min.js"
BEACON_BLOCK = "<!-- Cloudflare Web Analytics --><script type='module' src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{\"token\": \"2ee12644257c4dd3b0357c59a12a109c\"}'></script><!-- End Cloudflare Web Analytics -->"


def install(path: Path) -> None:
    original = path.read_text(encoding="utf-8")
    cleaned = BLOCK_RE.sub("\n", original)
    if BEACON_URL in cleaned:
        raise RuntimeError(f"unmanaged Cloudflare beacon remains in {path}")
    if "</head>" not in cleaned:
        raise RuntimeError(f"missing </head> in {path}")
    rendered = cleaned.replace(
        "</head>", f"{BEACON_BLOCK}\n</head>", 1
    )
    if rendered.count(BEACON_URL) != 1 or rendered.count(BEACON_BLOCK) != 1:
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
        root / "about" / "index.html",
        root / "ncaaf" / "index.html",
        root / "ncaaf" / "results" / "index.html",
        root / "ncaaf" / "about" / "index.html",
        root / "mma" / "index.html",
        root / "mma" / "results" / "index.html",
        root / "mma" / "about" / "index.html",
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
    print("CLOUDFLARE_WEB_ANALYTICS=ACTIVE")
    print("RUM_BEACON_PER_PUBLIC_ROUTE=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
