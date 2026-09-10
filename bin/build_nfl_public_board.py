#!/usr/bin/env python3
"""NFL TODAY'S CARD — NCAAF unissued status and shared issued-market chrome."""
from __future__ import annotations

from datetime import datetime
from html import escape
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
NY = ZoneInfo("America/New_York")


def time_et(value: str) -> str:
    if not value:
        return "Time TBD"
    date = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(NY)
    return f"{date.hour % 12 or 12}:{date:%M} {date:%p} ET"


def date_meta(value: str) -> str:
    if not value:
        return ""
    date = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(NY)
    return f"{date:%A}, {date:%B} {date.day}, {date:%Y}".upper()


def issued_panel(label: str, pos: dict) -> str:
    pick = escape(str(pos.get("display_selection") or pos.get("headline") or pos.get("pick") or pos.get("selection") or "ISSUED"))
    tier = str(pos.get("rating_tier") or pos.get("tier") or "MODERATE").upper()
    if tier not in {"WEAK", "MODERATE", "STRONG", "ELITE"}:
        tier = "MODERATE"
    prob = pos.get("win_probability") or pos.get("apex_win_probability") or pos.get("issued_probability")
    if isinstance(prob, float) and prob <= 1:
        prob_s = f"{prob * 100:.1f}%"
    elif prob is not None:
        prob_s = str(prob)
    else:
        prob_s = "—"
    price = pos.get("american_price")
    price_s = ""
    if price is not None:
        try:
            p = int(price)
            price_s = f" at the captured FanDuel price of {p:+d}" if p else ""
        except Exception:
            price_s = ""
    rationale = pos.get("rationale_paragraphs") or pos.get("rationale") or []
    if isinstance(rationale, str):
        rationale = [rationale]
    if not rationale:
        rationale = [
            f"The issued probability for {pick} is {prob_s}{price_s}; Sportsbook: FanDuel.",
            f"The {tier} label is a calibrated-probability bucket only.",
        ]
    body = "".join(f"<p>{escape(str(p))}</p>" for p in rationale)
    return (
        f'<div class="market-panel">'
        f'<div class="market-label">{escape(label)}</div>'
        f'<div class="market-panel-head">'
        f'<span class="pick-headline">{pick}</span>'
        f'<span class="rating-label">APEX WIN PROBABILITY RATING</span>'
        f'<span class="tier-badge tier-badge--{tier.lower()}">{escape(tier)}</span>'
        f'</div>'
        f'<div class="meta mono">APEX WIN PROBABILITY: {escape(prob_s)} · Sportsbook: FanDuel</div>'
        f'<div class="rationale-copy">{body}</div>'
        f'</div>'
    )


def unissued_panel(label: str, state: str) -> str:
    # MLB-shaped empty panel — no invent picks/probs/tiers; no meta boilerplate spam
    return (
        f'<div class="market-panel">'
        f'<div class="market-label">{escape(label)}</div>'
        f'<div class="market-panel-head">'
        f'<span class="pick-headline">UNISSUED</span>'
        f'<span class="rating-label">APEX WIN PROBABILITY RATING</span>'
        f'<span class="tier-badge">—</span>'
        f'</div>'
        f'<div class="meta mono">APEX WIN PROBABILITY: — · Sportsbook: FanDuel</div>'
        f'<div class="rationale-copy">'
        f'<p>The T-2 picks card has not been published for this game.</p>'
        f'<p>The published card will include selection, '
        f'WEAK/MODERATE/STRONG/ELITE rating, win probability, and detailed rationale.</p>'
        f'</div></div>'
    )


def panels_for_game(game: dict, today: dict) -> str:
    state = str(today.get("scientific_release_state") or "UNISSUED")
    positions = list(game.get("positions") or [])
    if not positions:
        # Match the unissued STATUS block in ncaaf/index.html exactly.
        return (
            '<div class="market-grid">'
            '<section class="market-panel" data-position-state="UNISSUED">'
            '<div class="market-label">STATUS</div>'
            '<div class="market-panel-head">'
            '<span class="pick-headline">UNISSUED — AWAITING T-2</span>'
            '<span class="tier-badge tier-badge--moderate">SCHEDULED</span>'
            '</div><div class="rationale-copy">'
            '<p>Listed from the official schedule. No sealed FanDuel-issued APEX positions yet.</p>'
            '</div></section></div>'
        )

    def take(engine: str, label: str) -> str:
        hits = []
        for p in positions:
            m = str(p.get("market") or p.get("engine") or p.get("display_market_label") or "").upper()
            if engine == "ATS" and "ATS" in m and "TOTAL" not in m:
                hits.append(p)
            elif engine == "TOTALS" and ("TOTAL" in m or m == "TOTALS" or "TOT" in m):
                hits.append(p)
            elif engine == "PROPS" and ("PROP" in m or "QB" in m or "RB" in m or "WR" in m):
                hits.append(p)
        if hits:
            return "".join(issued_panel(label, p) for p in hits)
        return unissued_panel(label, state)

    # MLB layout: market-grid with side-by-side panels; props included as third panel in same grid
    return (
        '<div class="market-grid">'
        + take("ATS", "FULL-GAME ATS")
        + take("TOTALS", "FULL-GAME TOTALS")
        + take("PROPS", "QB / RB / WR PROPS")
        + "</div>"
    )


def render_card(game: dict, index: int, today: dict) -> str:
    away = game.get("away_team") or ""
    home = game.get("home_team") or ""
    matchup = game.get("matchup") or f"{away} @ {home}"
    # MLB uses @ not "at"
    matchup = matchup.replace(" at ", " @ ")
    kick = time_et(game.get("kickoff_utc") or game.get("kickoff_et") or "")
    sub = ""
    if game.get("week") is not None:
        sub = f'<p class="game-pitchers mono">WEEK {escape(str(game.get("week")))} · {escape(str(game.get("season_type") or "REG"))}</p>'
    return (
        f'<article class="game-module" data-game="G{index+1:02}">'
        f'<header class="game-header">'
        f'<div class="game-num mono">G{index+1:02}</div>'
        f'<div class="game-meta">'
        f'<h2 class="game-matchup">{escape(matchup)}</h2>'
        f"{sub}"
        f"</div>"
        f'<div class="game-time mono">{escape(kick)}</div>'
        f"</header>"
        f"{panels_for_game(game, today)}"
        f"</article>"
    )


def render_board(today: dict) -> str:
    games = sorted(today.get("slate", {}).get("games", []), key=lambda g: (g.get("kickoff_utc", ""), g["game_id"]))
    count = len(games)
    issued = int(today.get("position_count") or 0)
    stamp = today.get("generated_at_utc") or datetime.now(tz=NY).isoformat()
    meta = (
        f"{date_meta(stamp)} · {count} {'GAME' if count == 1 else 'GAMES'} · {issued} POSITIONS"
        f" · ATS · TOTALS · PROPS"
    )
    cards = "".join(render_card(g, i, today) for i, g in enumerate(games))
    if not games:
        cards = "<p class=\"nfl-schedule-note\">The next NFL schedule has not been published yet.</p>"
    return (
        f'<section class="nfl-board" aria-label="NFL today card" data-generated-at="{escape(stamp, quote=True)}">'
        f'<div class="section-head picks-board-head">'
        f'<div class="title" id="slate-title">TODAY&#39;S CARD</div>'
        f'<div class="meta mono" id="slate-meta">{escape(meta)}</div>'
        f"</div>"
        f'<div class="picks-board" id="games" aria-live="polite">{cards}</div>'
        f'<p class="nfl-updated mono" id="nfl-refresh-status">SCHEDULE UPDATED {escape(time_et(stamp))}</p>'
        f"</section>"
    )


def build(root: Path = ROOT) -> None:
    today_path = root / "data/nfl_today.json"
    today = json.loads(today_path.read_text())
    today["generated_at_utc"] = datetime.now(tz=NY).astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-3] + "Z"
    today_path.write_text(json.dumps(today, indent=2) + "\n")
    board = render_board(today)
    for relative in ("nfl/index.html",):
        path = root / relative
        text = path.read_text()
        start, end = "<!-- NFL_BOARD_START -->", "<!-- NFL_BOARD_END -->"
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError(f"markers missing: {relative}")
        text = text.split(start)[0] + start + "\n" + board + "\n" + end + text.split(end)[1]
        issued = any(game.get("positions") for game in today.get("slate", {}).get("games", []))
        text = re.sub(r'data-picks-state="[^"]*"', f'data-picks-state="{"issued" if issued else "quiet"}"', text)
        text = re.sub(r'data-public-issuance="[^"]*"', f'data-public-issuance="{str(issued).lower()}"', text)
        # keep board.js disabled
        path.write_text(text)
        print(f"NFL_PUBLIC_BOARD={relative}")


if __name__ == "__main__":
    build()
