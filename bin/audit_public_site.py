#!/usr/bin/env python3
"""Fail closed on public-route, icon, manifest, and RUM cardinality drift."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
BEACON_URL = "https://static.cloudflareinsights.com/beacon.min.js"


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
        for marker in required_markup:
            if marker not in text:
                errors.append(f"{route} missing {marker}")
        route_beacons[route] = text.count(BEACON_URL)

    counts = set(route_beacons.values())
    if counts not in ({0}, {1}):
        errors.append(f"mixed or duplicate public RUM beacon counts: {route_beacons}")

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
        "icon_sha256": icon_hashes,
        "errors": errors,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
