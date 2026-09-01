#!/usr/bin/env python3
"""Shared deterministic HTML fragments for the namespaced APEX MMA product."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def head(title: str, description: str, canonical_path: str) -> str:
    return f"""<!doctype html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1.0,viewport-fit=cover\">
<title>{title}</title>
<meta name=\"description\" content=\"{description}\">
<link rel=\"icon\" type=\"image/svg+xml\" href=\"/favicon.svg?v=apex-20260825-mma\">
<link rel=\"icon\" type=\"image/x-icon\" href=\"/favicon.ico?v=apex-20260825-mma\" sizes=\"32x32\">
<link rel=\"icon\" type=\"image/png\" sizes=\"32x32\" href=\"/favicon-32x32.png?v=apex-20260825-mma\">
<link rel=\"icon\" type=\"image/png\" sizes=\"16x16\" href=\"/favicon-16x16.png?v=apex-20260825-mma\">
<link rel=\"apple-touch-icon\" sizes=\"180x180\" href=\"/apple-touch-icon.png?v=apex-20260825-mma\">
<link rel=\"manifest\" href=\"/site.webmanifest?v=apex-20260825-mma\">
<meta name=\"theme-color\" content=\"#000000\">
<meta property=\"og:type\" content=\"website\">
<meta property=\"og:site_name\" content=\"APEX\">
<meta property=\"og:title\" content=\"{title}\">
<meta property=\"og:description\" content=\"{description}\">
<meta property=\"og:url\" content=\"https://apexrigor.com{canonical_path}\">
<meta property=\"og:image\" content=\"https://apexrigor.com/og-image.png?v=apex-20260825-mma\">
<link rel=\"stylesheet\" href=\"/assets/apex.css?v=apex-20260825-mma\">
</head>"""


def hero() -> str:
    return """<body>
<div class=\"shell\">
  <div class=\"hero\">
    <div class=\"hero-mark\"><svg viewBox=\"0 0 44 44\" xmlns=\"http://www.w3.org/2000/svg\"><polygon points=\"22,6 38,36 6,36\"/></svg></div>
    <div class=\"hero-wordmark\">APEX</div>
    <div class=\"hero-rule\"></div>
    <div class=\"hero-tag\">MMA / UFC</div>
    <div class=\"hero-math\">The Math Speaks.</div>
  </div>"""


def navigation(active: str) -> str:
    section_path = {"PICKS": "", "RESULTS": "/results", "ABOUT": "/about"}[active]
    sport = f"""  <div class=\"apex-nav-stack\">
  <nav class=\"sport-nav\" aria-label=\"Sport selector\">
    <a href=\"/{section_path.lstrip('/')}\">MLB</a>
    <a href=\"/ncaaf{section_path}\">APEX NCAA FOOTBALL</a>
    <a href=\"/mma{section_path}\" class=\"active\" aria-current=\"true\">MMA / UFC</a>
    <span class=\"sport-unavailable\" aria-disabled=\"true\" title=\"NFL public route not yet established\">NFL</span>
  </nav>"""
    links = (
        ("PICKS", "/mma"),
        ("RESULTS", "/mma/results"),
        ("ABOUT", "/mma/about"),
    )
    internal = "\n".join(
        f'    <a href="{path}"{" class=\"active\" aria-current=\"true\"" if label == active else ""}>{label}</a>'
        for label, path in links
    )
    return f"{sport}\n  <nav class=\"section-nav\" aria-label=\"MMA sections\">\n{internal}\n  </nav>\n  </div>"


def write(relative: str, content: str) -> Path:
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content.rstrip() + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def close() -> str:
    return "</div>\n</body>\n</html>"
