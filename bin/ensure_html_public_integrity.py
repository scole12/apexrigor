#!/usr/bin/env python3
"""Fail-closed + auto-heal public HTML head tags required by audit_public_site.

Required per-route markup (audit_public_site.py):
  rel="icon", rel="apple-touch-icon", rel="manifest", name="viewport"
Analytics/RUM are applied by build_vercel_output / apply_vercel_web_analytics.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REQUIRED = (
    'rel="icon"',
    'rel="apple-touch-icon"',
    'rel="manifest"',
    'name="viewport"',
)

GOLD_ICON_BLOCK = """
<link rel="icon" type="image/svg+xml" href="/favicon.svg?v=apex-integrity-lock">
<link rel="icon" type="image/x-icon" href="/favicon.ico?v=apex-integrity-lock" sizes="32x32">
<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png?v=apex-integrity-lock">
<link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png?v=apex-integrity-lock">
<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png?v=apex-integrity-lock">
<link rel="manifest" href="/site.webmanifest?v=apex-integrity-lock">
"""

VIEWPORT = '<meta name="viewport" content="width=device-width,initial-scale=1.0,viewport-fit=cover">'


def heal(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    missing = [m for m in REQUIRED if m not in text]
    if not missing:
        return []
    cleaned = re.sub(
        r'<link[^>]+rel="(?:icon|apple-touch-icon|manifest)"[^>]*>\s*',
        "",
        text,
        flags=re.I,
    )
    inject = GOLD_ICON_BLOCK
    if 'name="viewport"' not in cleaned:
        inject = VIEWPORT + "\n" + inject
    if "</head>" not in cleaned:
        raise SystemExit(f"NO_HEAD:{path}")
    healed = cleaned.replace("</head>", inject + "</head>", 1)
    still = [m for m in REQUIRED if m not in healed]
    if still:
        raise SystemExit(f"HEAL_FAILED:{path}:{still}")
    path.write_text(healed, encoding="utf-8")
    return missing


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--paths", nargs="*", default=[])
    args = ap.parse_args()
    root = args.root.resolve()
    if args.paths:
        targets = [root / p for p in args.paths if str(p).endswith(".html")]
    else:
        targets = list(root.rglob("*.html"))
    report = []
    for p in targets:
        if not p.is_file():
            continue
        miss = heal(p)
        if miss:
            report.append({"path": str(p.relative_to(root)), "healed_missing": miss})
    print({"status": "PASS", "healed": report, "checked": len(targets)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
