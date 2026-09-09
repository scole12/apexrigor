#!/usr/bin/env python3
"""Render NFL picks board in MLB TODAY'S CARD chrome (3 engines). Scott 2026-09-09."""
from __future__ import annotations

from datetime import datetime
from html import escape
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
NY = ZoneInfo("America/New_York")

ENGINES = (
    ("ATS", "FULL-GAME ATS"),
    ("TOTALS", "FULL-GAME TOTALS"),
    ("PROPS", "QB / RB / WR PROPS"),
)


def time_et(value: str) -> str:
    if not value:
        return "Time to be confirmed"
    date = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(NY)
    return f"{date.hour % 12 or 12}:{date:%M} {date:%p} ET"


def date_meta(value: str) -> str:
    if not value:
        return ""
    date = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(NY)
    return f"{date:%A}, {date:%B} {date.day}, {date:%Y}".upper()


def market_panel(engine_key: str, label: str, game: dict, today: dict) -> str:
    positions = [p for p in (game.get("positions") or []) if str(p.get("engine") or p.get("market") or "").upper().startswith(engine_key[:3]) or str(p.get("engine") or "").upper() == engine_key]
    # also accept market field containing ATS/TOTALS/PROPS
    if not positions:
        positions = [p for p in (game.get("positions") or []) if engine_key in str(p.get("market") or p.get("engine") or "").upper()]
    blocked = str(today.get("scientific_release_state", "")).startswith("SCIENCE_BLOCKED")
    if positions:
        panels = []
        for pos in positions:
            pick = escape(str(pos.get("selection") or pos.get("pick") or pos.get("headline") or "ISSUED"))
            tier = str(pos.get("rating_tier") or pos.get("tier") or "MODERATE").upper()
            if tier not in {"WEAK", "MODERATE", "STRONG", "ELITE"}:
                tier = "MODERATE"
            tier_class = tier.lower()
            prob = pos.get("win_probability") or pos.get("apex_win_probability")
            prob_s = f"{float(prob)*100:.1f}%" if isinstance(prob, float) and prob <= 1 else (f"{prob}" if prob is not None else "—")
            rationale = pos.get("rationale_paragraphs") or pos.get("rationale") or []
            if isinstance(rationale, str):
                rationale = [rationale]
            rationale_html = "".join(f"<p>{escape(str(p))}</p>" for p in rationale) or "<p>Issued position. Detailed rationale bound at T-2.</p>"
            panels.append(
                f'<div class="market-panel">'
                f'<div class="market-label">{escape(label)}</div>'
                f'<div class="market-panel-head">'
                f'<span class="pick-headline">{pick}</span>'
                f'<span class="rating-label">APEX WIN PROBABILITY RATING</span>'
                f'<span class="tier-badge tier-badge--{tier_class}">{escape(tier)}</span>'
                f'</div>'
                f'<div class="meta mono">APEX WIN PROBABILITY: {escape(prob_s)} · Sportsbook: FanDuel</div>'
                f'<div class="rationale-copy">{rationale_html}</div>'
                f'</div>'
            )
        return "".join(panels)
    # UNISSUED — MLB chrome, no invented picks/probs/tiers
    why = "SCIENCE_BLOCKED_NO_QUALIFIED_CHAMPION" if blocked else "NO_ISSUED_POSITION"
    copy = (
        f"<p>No {escape(label)} position is issued for this game.</p>"
        f"<p>Release state: {escape(str(today.get('scientific_release_state') or why))}.</p>"
        f"<p>When a FanDuel-qualified champion clears A-law, this panel publishes the pick, "
        f"WEAK/MODERATE/STRONG/ELITE rating, FanDuel win probability, and detailed rationale "
        f"in the same format as MLB.</p>"
    )
    return (
        f'<div class="market-panel">'
        f'<div class="market-label">{escape(label)}</div>'
        f'<div class="market-panel-head">'
        f'<span class="pick-headline">UNISSUED</span>'
        f'<span class="rating-label">APEX WIN PROBABILITY RATING</span>'
        f'<span class="tier-badge">—</span>'
        f'</div>'
        f'<div class="meta mono">APEX WIN PROBABILITY: — · Sportsbook: FanDuel</div>'
        f'<div class="rationale-copy">{copy}</div>'
        f'</div>'
    )


def render_card(game: dict, index: int, today: dict) -> str:
    matchup = game.get("matchup") or f"{game.get('away_team','')} @ {game.get('home_team','')}"
    kick = time_et(game.get("kickoff_utc") or game.get("kickoff_et") or "")
    markets = "".join(market_panel(k, lab, game, today) for k, lab in ENGINES)
    return (
        f'<article class="game-module" data-game="G{index+1:02}">'
        f'<header class="game-header">'
        f'<div class="game-num mono">G{index+1:02}</div>'
        f'<div class="game-meta"><h2 class="game-matchup">{escape(matchup)}</h2></div>'
        f'<div class="game-time mono">{escape(kick)}</div>'
        f'</header>'
        f'<div class="market-grid">{markets}</div>'
        f'</article>'
    )


def render_board(today: dict) -> str:
    games = sorted(today.get("slate", {}).get("games", []), key=lambda g: (g.get("kickoff_utc", ""), g["game_id"]))
    count = len(games)
    issued = int(today.get("position_count") or 0)
    stamp = today.get("generated_at_utc") or datetime.now(tz=NY).isoformat()
    meta = f"{date_meta(stamp)} · {count} {'GAME' if count == 1 else 'GAMES'} · {issued} POSITIONS · ATS · TOTALS · PROPS"
    cards = "".join(render_card(g, i, today) for i, g in enumerate(games))
    if not games:
        cards = '<p class="nfl-schedule-note">The next NFL schedule has not been published yet.</p>'
    return (
        f'<section class="nfl-board" aria-label="NFL today card" data-generated-at="{escape(stamp, quote=True)}">'
        f'<div class="section-head picks-board-head">'
        f'<div class="title" id="slate-title">TODAY&#39;S CARD</div>'
        f'<div class="meta mono" id="slate-meta">{escape(meta)}</div>'
        f'</div>'
        f'<div class="picks-board" id="games" aria-live="polite">{cards}</div>'
        f'<p class="nfl-updated mono" id="nfl-refresh-status">SCHEDULE UPDATED {escape(time_et(stamp))}</p>'
        f'</section>'
    )


def build(root: Path = ROOT) -> None:
    today = json.loads((root / "data/nfl_today.json").read_text())
    # refresh stamp so page is not stale
    today["generated_at_utc"] = datetime.now(tz=NY).astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-3] + "Z"
    (root / "data/nfl_today.json").write_text(json.dumps(today, indent=2) + "\n")
    board = render_board(today)
    for relative in ("nfl/index.html", "nfl/results/index.html"):
        path = root / relative
        text = path.read_text()
        start, end = "<!-- NFL_BOARD_START -->", "<!-- NFL_BOARD_END -->"
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError(f"NFL board render markers missing: {relative}")
        text = text.split(start)[0] + start + "\n" + board + "\n" + end + text.split(end)[1]
        path.write_text(text)
        print(f"NFL_PUBLIC_BOARD={relative}")


if __name__ == "__main__":
    build()
