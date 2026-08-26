#!/usr/bin/env python3
"""Fail closed on the MLB-only public boundary, assets, and RUM drift."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
BEACON_URL = "https://static.cloudflareinsights.com/beacon.min.js"
VERCEL_INSIGHTS_SCRIPT = "/_vercel/insights/script.js"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    if len(data) != 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"not a PNG: {path}")
    return struct.unpack(">II", data[16:24])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help="site-output root; defaults to the canonical working tree",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    routes = {
        "/": root / "index.html",
        "/picks": root / "picks" / "index.html",
        "/results": root / "results" / "index.html",
        "/about": root / "about" / "index.html",
    }
    icon_pairs = (
        (root / "favicon.svg", root / "assets" / "favicon.svg"),
        (root / "favicon.ico", root / "assets" / "favicon.ico"),
        (root / "favicon-16x16.png", root / "assets" / "favicon-16x16.png"),
        (root / "favicon-32x32.png", root / "assets" / "favicon-32x32.png"),
        (root / "apple-touch-icon.png", root / "assets" / "apple-touch-icon.png"),
        (
            root / "android-chrome-192x192.png",
            root / "assets" / "android-chrome-192x192.png",
        ),
        (
            root / "android-chrome-512x512.png",
            root / "assets" / "android-chrome-512x512.png",
        ),
    )
    errors: list[str] = []
    route_beacons: dict[str, int] = {}
    route_vercel_scripts: dict[str, int] = {}
    route_text: dict[str, str] = {}
    required_markup = (
        'rel="icon"',
        'rel="apple-touch-icon"',
        'rel="manifest"',
        'name="viewport"',
    )
    for route, path in routes.items():
        if not path.is_file():
            errors.append(f"missing route output {route}: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        route_text[route] = text
        for marker in required_markup:
            if marker not in text:
                errors.append(f"{route} missing {marker}")
        route_beacons[route] = text.count(BEACON_URL)
        route_vercel_scripts[route] = text.count(VERCEL_INSIGHTS_SCRIPT)
        if "window.va" not in text:
            errors.append(f"{route} missing official Vercel Analytics queue")

    counts = set(route_beacons.values())
    if counts not in ({0}, {1}):
        errors.append(f"mixed or duplicate public RUM beacon counts: {route_beacons}")
    vercel_counts = set(route_vercel_scripts.values())
    if vercel_counts != {1}:
        errors.append(
            f"Vercel Analytics script must appear once per public route: {route_vercel_scripts}"
        )

    switcher_re = re.compile(r'<div class="sport-switcher".*?</div>', re.DOTALL)
    public_sport_switcher_count = 0
    public_world_cup_label_count = 0
    public_soccer_label_count = 0
    public_other_sport_label_counts = {
        "nhl": 0,
        "nba": 0,
        "ncaa": 0,
        "mls": 0,
        "liga_mx": 0,
    }
    for route, text in route_text.items():
        switcher_count = len(switcher_re.findall(text))
        public_sport_switcher_count += switcher_count
        if switcher_count:
            errors.append(f"{route} exposes an unneeded sport switcher before launch")
        public_world_cup_label_count += len(
            re.findall(r"(?:href=\"[^\"]*worldcup|>\s*WORLD CUP\s*<)", text, re.IGNORECASE)
        )
        public_soccer_label_count += len(
            re.findall(r"(?:href=\"[^\"]*soccer|\bsoccer\b)", text, re.IGNORECASE)
        )
        public_other_sport_label_counts["nhl"] += len(
            re.findall(r"\bNHL\b", text, re.IGNORECASE)
        )
        public_other_sport_label_counts["nba"] += len(
            re.findall(r"\bNBA\b", text, re.IGNORECASE)
        )
        public_other_sport_label_counts["ncaa"] += len(
            re.findall(r"\bNCAA\b", text, re.IGNORECASE)
        )
        public_other_sport_label_counts["mls"] += len(
            re.findall(r"\bMLS\b", text, re.IGNORECASE)
        )
        public_other_sport_label_counts["liga_mx"] += len(
            re.findall(r"\bLiga\s+(?:MX|Mexico)\b", text, re.IGNORECASE)
        )
    if public_world_cup_label_count or public_soccer_label_count:
        errors.append(
            "inactive sport leaked into a current public route: "
            f"soccer={public_soccer_label_count}, "
            f"world_cup={public_world_cup_label_count}"
        )
    public_other_sport_label_count = sum(
        public_other_sport_label_counts.values()
    )
    if public_other_sport_label_count:
        errors.append(
            "non-MLB sport leaked into a current public route: "
            + ", ".join(
                f"{sport}={count}"
                for sport, count in public_other_sport_label_counts.items()
            )
        )

    hidden_route_paths = tuple(
        root / section / route_name
        for section in ("picks", "results")
        for route_name in ("soccer", "worldcup")
    )
    for path in hidden_route_paths:
        if path.exists():
            errors.append(f"unlaunched sport route present in output: {path}")

    about = route_text.get("/about", "")
    for model_id in (
        "ATS-ELITE-C1-CONDITIONAL-DISTRIBUTION-RESIDUAL",
        "TOTALS_FINAL_NESTED_JOINT_R4_V1_20260825",
    ):
        if model_id not in about:
            errors.append(f"/about missing current MLB model identity: {model_id}")

    config_root = root if (root / "vercel.json").is_file() else root.parent
    try:
        vercel = json.loads((config_root / "vercel.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"invalid vercel.json: {exc}")
        vercel = {}
    for item in vercel.get("redirects", []):
        source = str(item.get("source", ""))
        destination = str(item.get("destination", ""))
        if any(
            name in value.lower()
            for name in ("soccer", "worldcup")
            for value in (source, destination)
        ):
            errors.append(f"unlaunched sport redirect present: {source} -> {destination}")

    icon_hashes: dict[str, str] = {}
    for root_icon, asset_icon in icon_pairs:
        if not root_icon.is_file() or not asset_icon.is_file():
            errors.append(f"missing icon pair: {root_icon.name}")
            continue
        root_hash, asset_hash = sha256(root_icon), sha256(asset_icon)
        icon_hashes[root_icon.name] = root_hash
        if root_hash != asset_hash:
            errors.append(f"root/assets icon mismatch: {root_icon.name}")

    expected_png_dimensions = {
        "favicon-16x16.png": (16, 16),
        "favicon-32x32.png": (32, 32),
        "apple-touch-icon.png": (180, 180),
        "android-chrome-192x192.png": (192, 192),
        "android-chrome-512x512.png": (512, 512),
    }
    for name, expected in expected_png_dimensions.items():
        try:
            actual = png_dimensions(root / name)
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
        else:
            if actual != expected:
                errors.append(f"{name} dimensions {actual}, expected {expected}")

    try:
        manifest = json.loads((root / "site.webmanifest").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"invalid site.webmanifest: {exc}")
        manifest = {}
    manifest_sizes = {item.get("sizes") for item in manifest.get("icons", [])}
    if not {"192x192", "512x512"}.issubset(manifest_sizes):
        errors.append(f"manifest missing Android sizes: {sorted(manifest_sizes)}")

    result = {
        "schema": "APEX_PUBLIC_SITE_INTEGRITY_V1",
        "ok": not errors,
        "routes": {route: str(path.relative_to(root)) for route, path in routes.items()},
        "rum_beacons_per_route": route_beacons,
        "rum_state": "ACTIVE" if counts == {1} else "OWNER_ACTION_REQUIRED",
        "vercel_insights_scripts_per_route": route_vercel_scripts,
        "vercel_web_analytics": "ACTIVE" if vercel_counts == {1} else "MISSING",
        "icon_sha256": icon_hashes,
        "errors": errors,
        "public_sport_switcher_count": public_sport_switcher_count,
        "public_soccer_label_count": public_soccer_label_count,
        "public_sport_label_soccer": "HIDDEN",
        "public_world_cup_label_count": public_world_cup_label_count,
        "public_other_sport_label_count": public_other_sport_label_count,
        "public_other_sport_label_counts": public_other_sport_label_counts,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    print("PUBLIC_SPORT_LABEL_SOCCER=HIDDEN")
    print(f"PUBLIC_WORLD_CUP_LABEL_COUNT={public_world_cup_label_count}")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
