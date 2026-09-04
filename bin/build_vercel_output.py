#!/usr/bin/env python3
"""Create the minimal deterministic static directory consumed by Vercel."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "public"
FILES = (
    "index.html",
    "picks.html",
    "results.html",
    "favicon.svg",
    "favicon.ico",
    "favicon-16x16.png",
    "favicon-32x32.png",
    "apple-touch-icon.png",
    "android-chrome-192x192.png",
    "android-chrome-512x512.png",
    "og-image.png",
    "site.webmanifest",
)
DIRECTORIES = ("assets", "data", "picks", "results", "about", "ncaaf", "mma", "nfl")
GENERATORS = (
    "build_mma_public_payload.py",
    "build_mma_picks_page.py",
    "build_mma_results_page.py",
    "build_mma_about_page.py",
)


def ignore_data_backups(_directory: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        if (
            name.startswith("_")
            or "STALE" in name
            or ".bak" in name
            or name.endswith("_stage")
        ):
            ignored.add(name)
    return ignored


def main() -> int:
    if OUTPUT.parent != ROOT or OUTPUT.name != "public":
        raise RuntimeError(f"refusing unsafe output path: {OUTPUT}")
    for generator in GENERATORS:
        subprocess.run([sys.executable, str(ROOT / "bin" / generator)], check=True)

    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(mode=0o755)

    for relative in FILES:
        source = ROOT / relative
        if not source.is_file():
            raise FileNotFoundError(source)
        shutil.copy2(source, OUTPUT / relative)

    for relative in DIRECTORIES:
        source = ROOT / relative
        if not source.is_dir():
            raise FileNotFoundError(source)
        ignore = ignore_data_backups if relative == "data" else None
        shutil.copytree(source, OUTPUT / relative, ignore=ignore)

    commands = (
        [
            sys.executable,
            str(ROOT / "bin" / "apply_shared_sport_selector.py"),
            "--root",
            str(OUTPUT),
        ],
        [
            sys.executable,
            str(ROOT / "bin" / "apply_cloudflare_web_analytics.py"),
            "--root",
            str(OUTPUT),
            "--allow-missing",
        ],
        [
            sys.executable,
            str(ROOT / "bin" / "apply_vercel_web_analytics.py"),
            "--root",
            str(OUTPUT),
            "--allow-missing",
        ],
        [
            sys.executable,
            str(ROOT / "bin" / "audit_public_site.py"),
            "--root",
            str(OUTPUT),
        ],
    )
    for command in commands:
        subprocess.run(command, check=True)
    print(f"VERCEL_OUTPUT={OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
