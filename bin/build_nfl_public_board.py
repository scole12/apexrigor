#!/usr/bin/env python3
"""Render the published NFL slate into both routes, including without JavaScript.

Called by the existing NFL payload/publication builder on every refresh. Schedule
visibility is independent of prices, issuance, and the results ledger.
"""
from __future__ import annotations

from datetime import datetime
from html import escape
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
NY = ZoneInfo("America/New_York")
CARD = '''<article class="game-module nfl-game" data-game="[[ID]]" data-game-state="[[STATE]]">
  <header class="game-header">
    <div class="game-num mono">[[NUMBER]]</div>
    <div class="game-meta"><p class="nfl-eyebrow mono">[[ABBREVIATION]] · [[SEASON]] · WEEK [[WEEK]]</p><h2 class="game-matchup">[[MATCHUP]]</h2></div>
    <div class="game-time mono"><span class="nfl-kick-label">KICKOFF · [[SCHEDULE_STATE]]</span><time datetime="[[KICKOFF]]">[[TIME]]</time></div>
  </header>
  <div class="nfl-preparation"><div class="nfl-status"><span class="nfl-badge mono">[[STATE]]</span><span class="mono">[[PREPARATION]]</span></div><p>[[DETAIL]]</p></div>
[[MILESTONES]]
[[POSITIONS]]
</article>'''


def time_et(value: str) -> str:
    if not value:
        return "Time to be confirmed"
    date = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(NY)
    return f"{date:%a}, {date:%b} {date.day} · {date.hour % 12 or 12}:{date:%M} {date:%p} ET"


def abbreviation(game: dict) -> str:
    def short(key: str) -> str:
        value = str(game.get(key, "")).removeprefix("NFL_TEAM_")
        return "LAR" if value == "LA" else value
    return f"{short('away_team_id')} @ {short('home_team_id')}"


def render_card(game: dict, index: int, today: dict) -> str:
    issued = len(game.get("positions") or [])
    blocked = str(today.get("scientific_release_state", "")).startswith("SCIENCE_BLOCKED")
    milestones = []
    for key, label in (("NEXT_T3", "DATA REPORT"), ("NEXT_T2", "PICKS REVIEW")):
        stage = today.get("next_up", {}).get(key) or {}
        at = stage.get("at_et") or stage.get("at_utc")
        if game["game_id"] in stage.get("game_ids", []) and at:
            milestones.append('<div><dt>' + label + ' · ' + escape(stage.get("state", ""))
                              + '</dt><dd><time datetime="' + escape(at, quote=True) + '">'
                              + escape(time_et(at)) + '</time></dd></div>')
    values = {
        "ID": game["game_id"], "STATE": "ISSUED" if issued else "UNISSUED",
        "NUMBER": "NEXT" if index == 0 else f"G{index + 1:02}",
        "ABBREVIATION": abbreviation(game), "SEASON": game.get("season", ""),
        "WEEK": game.get("week", ""), "MATCHUP": game.get("matchup", ""),
        "SCHEDULE_STATE": game.get("status", "SCHEDULED"),
        "KICKOFF": game.get("kickoff_et") or game.get("kickoff_utc", ""),
        "TIME": time_et(game.get("kickoff_utc") or game.get("kickoff_et", "")),
        "PREPARATION": f"{issued} ISSUED POSITIONS" if issued else "PREPARE",
        "DETAIL": ("Selections are available on the Picks board." if issued else
                   "No picks issued. Lines and prices will appear with issued selections."),
    }
    rendered = re.sub(r"\[\[([A-Z_]+)\]\]", lambda m: escape(str(values[m[1]]), quote=True)
                      if m[1] in values else m[0], CARD)
    status = '<p class="nfl-science mono">SCIENCE_BLOCKED · 0 ISSUED POSITIONS</p>' if blocked and not issued else ""
    return rendered.replace("[[MILESTONES]]", ('<dl class="nfl-milestones mono">' + ''.join(milestones) + '</dl>' if milestones else '') + status).replace("[[POSITIONS]]", "")


def render_board(today: dict) -> str:
    games = sorted(today.get("slate", {}).get("games", []), key=lambda g: (g.get("kickoff_utc", ""), g["game_id"]))
    count = len(games)
    heading = "UPCOMING NFL" if not today.get("position_count") else "NFL GAME BOARD"
    cards = ''.join(render_card(game, i, today) for i, game in enumerate(games))
    if not games:
        cards = '<p class="nfl-schedule-note">The next NFL schedule has not been published yet. This board updates with the next scheduled slate.</p>'
    stamp = today.get("generated_at_utc", "")
    return (f'<section class="nfl-board" aria-label="NFL upcoming game board" data-generated-at="{escape(stamp, quote=True)}">'
            f'<div class="section-head picks-board-head"><h1 class="title" id="slate-title">{heading}</h1>'
            f'<div class="meta mono" id="slate-meta">{count} {"GAME" if count == 1 else "GAMES"} · {int(today.get("position_count", 0))} ISSUED POSITIONS</div></div>'
            f'<div class="picks-board" id="games" aria-live="polite">{cards}</div>'
            f'<p class="nfl-updated mono" id="nfl-refresh-status">SCHEDULE UPDATED {escape(time_et(stamp))}</p>'
            f'<template id="nfl-game-template">{CARD}</template></section>')


def build(root: Path = ROOT) -> None:
    today = json.loads((root / "data/nfl_today.json").read_text())
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
