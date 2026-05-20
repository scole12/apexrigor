#!/usr/bin/env python3
"""APEX static Picks page — premium presentation from mlb_today.json."""
from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime
from html import escape
from pathlib import Path

JSON_PATH = Path("/opt/apex_site/data/mlb_today.json")
INDEX_OUT = Path("/opt/apex_site/index.html")
PICKS_OUT = Path("/opt/apex_site/picks/index.html")
QUARANTINE = Path("/opt/apex_mlb/quarantine")
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "/opt/apex_mlb/bin")
from _apex_head import get_head_block, verify_branding  # noqa: E402
from apex_visual_presentation_guard import assert_picks_html_presentation, guard_write  # noqa: E402

SHELL_HERO = """  <div class="hero">
    <div class="hero-mark">
      <svg viewBox="0 0 44 44" xmlns="http://www.w3.org/2000/svg"><polygon points="22,6 38,36 6,36"/></svg>
    </div>
    <div class="hero-wordmark">APEX</div>
    <div class="hero-rule"></div>
    <div class="hero-tag">QUANTITATIVE FORECASTING</div>
    <div class="hero-math">The Math Speaks.</div>
  </div>"""


def et_to_min(et: str) -> int:
    try:
        m = re.match(r"(\d+):(\d+)\s*(AM|PM)", (et or "").strip(), re.I)
        if not m:
            return 9999
        h, mn, ap = int(m.group(1)), int(m.group(2)), m.group(3).upper()
        if ap == "PM" and h != 12:
            h += 12
        if ap == "AM" and h == 12:
            h = 0
        return h * 60 + mn
    except Exception:
        return 9999


def split_sentences(text: str) -> list[str]:
    t = (text or "").strip()
    if not t:
        return []
    t = re.sub(
        r"\b(?:St|Sr|Jr|Dr|Mr|Mrs|Ms|Prof|Rev|Gen|Col|Maj|Capt|Lt|Sgt|Cpl|Pvt|vs)\.",
        lambda m: m.group(0).replace(".", "\u2024"),
        t,
        flags=re.I,
    )
    parts = [p.replace("\u2024", ".") for p in re.split(r"(?<=[.!?])\s+", t) if p.strip()]
    return parts[:6]


def tier_class(tier: str) -> str:
    return (tier or "WEAK").lower()


def market_sort_key(p: dict) -> int:
    m = (p.get("market") or "").upper()
    return 0 if "ATS" in m else 1


def market_label(p: dict) -> str:
    m = (p.get("market") or "").upper()
    if "ATS" in m:
        return "F5 ATS"
    if "TOT" in m:
        return "F5 TOT"
    return p.get("market", "")


def build_panel(p: dict) -> str:
    pick = escape(p.get("pick", ""))
    tier = escape(p.get("tier", "WEAK"))
    tc = tier_class(p.get("tier", "WEAK"))
    label = escape(market_label(p))
    rat = "\n".join(
        f"          <p>{escape(s)}</p>"
        for s in split_sentences(p.get("rationale_full") or p.get("rationale", ""))
    )
    return f"""      <div class="market-panel">
        <div class="market-label">{label}</div>
        <div class="market-panel-head">
          <span class="pick-headline">{pick}</span>
          <span class="tier-badge tier-badge--{tc}">{tier}</span>
        </div>
        <div class="rationale-copy">
{rat}
        </div>
      </div>"""


def build_games_html(games: list[dict]) -> str:
    blocks = []
    for i, g in enumerate(games, 1):
        gid = f"G{i:02d}"
        matchup = escape(g.get("matchup", ""))
        et = escape(g.get("first_pitch_et", ""))
        hp = escape(g.get("home_pitcher", ""))
        ap = escape(g.get("away_pitcher", ""))
        pitchers = f"{ap} vs {hp}" if hp and ap else ""
        picks = sorted(g.get("picks", []), key=market_sort_key)
        panels = "\n".join(build_panel(p) for p in picks)
        blocks.append(
            f"""    <article class="game-module" data-game="{gid}">
      <header class="game-header">
        <div class="game-num mono">{gid}</div>
        <div class="game-meta">
          <h2 class="game-matchup">{matchup}</h2>
          <p class="game-pitchers mono">{pitchers}</p>
        </div>
        <div class="game-time mono">{et}</div>
      </header>
      <div class="market-grid">
{panels}
      </div>
    </article>"""
        )
    return "\n".join(blocks)


def main() -> int:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    for src in (INDEX_OUT, PICKS_OUT):
        if src.is_file():
            bak = QUARANTINE / f"{src.stem}_BEFORE_PICKS_POLISH_{ts}.html.bak"
            shutil.copy2(src, bak)
            print(f"BACKUP: {src} -> {bak}")

    d = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    date_iso = d["date"]
    games = sorted(d.get("games", []), key=lambda g: et_to_min(g.get("first_pitch_et", "")))
    n_games = d.get("game_count", len(games))
    n_pos = d.get("position_count", sum(len(g.get("picks", [])) for g in games))
    dt = datetime.strptime(date_iso, "%Y-%m-%d")
    today_str = dt.strftime("%A, %B %d, %Y").upper().replace(" 0", " ")

    head = get_head_block("APEX — MLB Picks", "/", "APEX Quantitative Forecasting — daily F5 picks.")
    games_html = build_games_html(games)
    html = f"""<!doctype html>
<html lang="en">
<head>
{head}
</head>
<body>
<div class="shell">
{SHELL_HERO}
  <nav class="nav">
    <a href="/" class="active">PICKS</a>
    <a href="/results">RESULTS</a>
    <a href="/about">ABOUT</a>
  </nav>
  <div class="section-head picks-board-head">
    <div class="title">TODAY'S CARD</div>
    <div class="meta mono">{escape(today_str)} · {n_games} GAMES · {n_pos} POSITIONS · MODEL V2.7</div>
  </div>
  <main class="picks-page">
    <div class="picks-board">
{games_html}
    </div>
  </main>
  <div class="tag">THE MATH SPEAKS.</div>
  <div class="foot mono">APEX RESEARCH · WALK-FORWARD VALIDATED · F5 MARKETS ONLY</div>
</div>
</body>
</html>""".replace("<div ", "<div ").replace("<div ", "<div ")

    ok, missing = verify_branding(html)
    if not ok:
        print(f"WARN branding markers missing: {missing}", file=sys.stderr)
    if "FLAT 1U" in html or "pick-odds" in html or "<motion" in html:
        print("BLOCKED: forbidden public markup in picks page", file=sys.stderr)
        return 2
    for cls in ("picks-page", "picks-board", "game-module", "market-panel", "rationale-copy"):
        if cls not in html:
            print(f"BLOCKED: missing {cls}", file=sys.stderr)
            return 2

    INDEX_OUT.write_text(html, encoding="utf-8")
    PICKS_OUT.parent.mkdir(parents=True, exist_ok=True)
    PICKS_OUT.write_text(html, encoding="utf-8")
    print(f"WROTE: {INDEX_OUT} ({len(html)} bytes)")
    print(f"WROTE: {PICKS_OUT} ({len(html)} bytes)")
    print(f"STATIC_PICKS_PAGE_BUILT: date={date_iso} games={n_games} positions={n_pos}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
