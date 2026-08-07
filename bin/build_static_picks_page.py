#!/usr/bin/env python3
"""APEX static Picks page — premium presentation from mlb_today.json."""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from datetime import datetime
from html import escape
from pathlib import Path

JSON_PATH = Path("/opt/apex_site/data/mlb_today.json")
INDEX_OUT = Path("/opt/apex_site/index.html")
PICKS_OUT = Path("/opt/apex_site/picks/index.html")
PICKS_HTML_ALT = Path("/opt/apex_site/picks.html")
QUARANTINE = Path("/opt/apex_mlb/quarantine")
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "/opt/apex_mlb/bin")
sys.path.insert(0, "/opt/apex_mlb/pipeline/ops")
sys.path.insert(0, "/opt/apex_mlb/current/bin")
from _apex_head import get_head_block, verify_branding  # noqa: E402
from apex_active_model_display import (  # noqa: E402
    labels_from_model_identity,
    live_model_identity,
    public_meta_model_line,
)
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

SPORT_SWITCHER_CSS = """<style>
.sport-switcher{display:flex;gap:0;border-bottom:1px solid var(--border,#1f1f1f);margin-bottom:0}
.sport-tab{flex:1;text-align:center;padding:14px 16px;min-height:44px;font-size:11px;letter-spacing:0.24em;text-transform:uppercase;color:var(--muted,#888);border-bottom:2px solid transparent;text-decoration:none;display:block}
.sport-tab:hover,.sport-tab:focus{color:var(--text,#f5f5f5);outline:2px solid var(--text);outline-offset:-2px}
.sport-tab.active{color:var(--text,#f5f5f5);border-bottom-color:var(--text,#f5f5f5)}
</style>"""

SPORT_SWITCHER_MLB = """
  <div class="sport-switcher" role="tablist" aria-label="Sport selection">
    <a href="{mlb_href}" class="sport-tab active" role="tab" aria-selected="true">MLB</a>
    <a href="/picks/worldcup" class="sport-tab" role="tab" aria-selected="false">SOCCER</a>
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


from apex_public_starter_sanitizer import (  # noqa: E402
    public_pitcher_display,
    sanitize_public_rationale,
)
from apex_factual_rationale_renderer import (  # noqa: E402
    factual_rationales_for_payload,
)


def sanitize_public_text(text: str, *, home_pitcher: str = "", away_pitcher: str = "") -> str:
    return sanitize_public_rationale(text, home_pitcher=home_pitcher, away_pitcher=away_pitcher)


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


def build_panel(
    p: dict,
    *,
    home_pitcher: str = "",
    away_pitcher: str = "",
    factual_text: str | None = None,
) -> str:
    pick = escape(p.get("pick", ""))
    no_tier = os.environ.get("APEX_NO_TIER_PUBLIC") == "1"
    tier = escape(p.get("tier", "WEAK"))
    tc = tier_class(p.get("tier", "WEAK"))
    label = escape(market_label(p))
    raw = sanitize_public_text(
        factual_text if factual_text is not None else (p.get("rationale") or ""),
        home_pitcher=home_pitcher,
        away_pitcher=away_pitcher,
    )
    rat = "\n".join(
        f"          <p>{escape(s)}</p>"
        for s in split_sentences(raw)
    )
    tier_html = "" if no_tier else f'\n          <span class="tier-badge tier-badge--{tc}">{tier}</span>'
    source_key = str(p.get("odds_source") or "").lower()
    sportsbook = (
        "FanDuel"
        if "fanduel" in source_key
        else "DraftKings"
        if any(key in source_key for key in (
            "draftkings", "draft_kings", "draft kings"
        ))
        else "BetMGM"
        if any(key in source_key for key in (
            "betmgm", "bet_mgm", "bet mgm"
        ))
        else "William Hill"
        if any(
            key in source_key
            for key in ("williamhill", "william_hill", "william hill")
        )
        else str(p.get("odds_source") or "Source unavailable")
    )
    return f"""      <div class="market-panel">
        <div class="market-label">{label}</div>
        <div class="market-panel-head">
          <span class="pick-headline">{pick}</span>{tier_html}
        </div>
        <div class="meta mono">Sportsbook: {escape(sportsbook)}</div>
        <div class="rationale-copy">
{rat}
        </div>
      </div>"""


def build_games_html(games: list[dict], factual: dict | None = None) -> str:
    factual = factual or {}
    blocks = []
    for i, g in enumerate(games, 1):
        gid = f"G{i:02d}"
        matchup = escape(g.get("matchup", ""))
        et = escape(g.get("first_pitch_et", ""))
        hp = escape(public_pitcher_display(g.get("home_pitcher", "")))
        ap = escape(public_pitcher_display(g.get("away_pitcher", "")))
        pitchers = f"{ap} vs {hp}" if hp and ap else ""
        picks = sorted(g.get("picks", []), key=market_sort_key)
        hp_raw = g.get("home_pitcher", "")
        ap_raw = g.get("away_pitcher", "")
        panels = "\n".join(
            build_panel(
                p,
                home_pitcher=hp_raw,
                away_pitcher=ap_raw,
                factual_text=factual[(int(g.get("game_pk")), market_label(p))],
            )
            for p in picks
        )
        if not picks and (
            g.get("publication_status")
            == "NO_AUTHENTIC_FANDUEL_MARKET_MODEL_OUTPUT_ONLY"
        ):
            reason = escape(
                g.get("missing_data_reason")
                or "No authentic pregame FanDuel F5 quote was found."
            )
            total_model = (g.get("model_outputs") or {}).get("totals") or {}
            expected_runs = total_model.get("expected_f5_runs")
            variance = total_model.get("variance")
            total_detail = (
                f"Approved repaired totals PMF available. Expected F5 runs "
                f"{float(expected_runs):.3f}; variance {float(variance):.3f}. "
                "Over, Under, Push, position, and strength are unavailable "
                "because no authentic FanDuel F5 total exists."
                if expected_runs is not None and variance is not None
                else "Approved repaired totals PMF is available in the card "
                     "payload; wager probabilities are unavailable."
            )
            panels = f"""      <div class="market-panel">
        <div class="market-label">F5 ATS</div>
        <div class="market-panel-head">
          <span class="pick-headline">UNAVAILABLE — NO FANDUEL LINE</span>
        </div>
        <div class="rationale-copy">
          <p>{reason}</p>
        </div>
      </div>
      <div class="market-panel">
        <div class="market-label">F5 TOTALS</div>
        <div class="market-panel-head">
          <span class="pick-headline">MODEL OUTPUT ONLY — NO WAGER</span>
        </div>
        <div class="rationale-copy">
          <p>{escape(total_detail)}</p>
        </div>
      </div>"""
        late_badge = ""
        if g.get("late_refreshed") or g.get("late_refresh_label"):
            label = escape(g.get("late_refresh_label") or "LATE REFRESHED 6:29 PM ET")
            late_badge = f'\n      <div class="meta mono late-refresh-badge">{label}</div>'
        blocks.append(
            f"""    <article class="game-module" data-game="{gid}">
      <header class="game-header">
        <div class="game-num mono">{gid}</div>
        <div class="game-meta">
          <h2 class="game-matchup">{matchup}</h2>
          <p class="game-pitchers mono">{pitchers}</p>
        </div>
        <div class="game-time mono">{et}</div>
      </header>{late_badge}
      <div class="market-grid">
{panels}
      </div>
    </article>"""
        )
    return "\n".join(blocks)


def main() -> int:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    QUARANTINE.mkdir(parents=True, exist_ok=True)
    for src in (INDEX_OUT, PICKS_OUT, PICKS_HTML_ALT):
        if src.is_file():
            bak = QUARANTINE / f"{src.stem}_BEFORE_PICKS_POLISH_{ts}.html.bak"
            shutil.copy2(src, bak)
            print(f"BACKUP: {src} -> {bak}")

    d = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    if not d.get("grading_banner"):
        auth_path = Path(
            f"/opt/apex_mlb/control_plane/grading_authority/grading_authority_{d.get('date', '')}.json"
        )
        if auth_path.is_file():
            try:
                auth = json.loads(auth_path.read_text(encoding="utf-8"))
                banner = auth.get("public_banner")
                if banner:
                    d = dict(d)
                    d["grading_banner"] = banner
            except Exception:
                pass
    date_iso = d["date"]
    prefire = d.get("public_state") == "PREFIRE_PENDING" or d.get("prefire_pending")
    games = sorted(d.get("games", []), key=lambda g: et_to_min(g.get("first_pitch_et", "")))
    n_games = d.get("game_count", len(games))
    n_pos = d.get("position_count", sum(len(g.get("picks", [])) for g in games))
    dt = datetime.strptime(date_iso, "%Y-%m-%d")
    today_str = dt.strftime("%A, %B %d, %Y").upper().replace(" 0", " ")
    t2_fire = escape(d.get("t2_fire_et_label") or "11:35 AM ET")
    if d.get("model_version_ats") and d.get("model_version_totals"):
        ident = {
            "public_ats_label": d["model_version_ats"],
            "public_totals_label": d["model_version_totals"],
        }
    else:
        ident = d.get("model_identity") or live_model_identity()
    model_lbl = escape(public_meta_model_line(ident))

    head_root = get_head_block("APEX — Quantitative Forecasting", "/")
    head_picks = get_head_block("APEX — Picks", "/picks")
    if prefire or not games:
        board_title = "NEXT SLATE ARMED"
        meta_line = (
            f"{escape(today_str)} · {n_games} GAMES · {n_pos} POSITIONS · "
            f"T-2 FIRE {t2_fire} · {model_lbl}"
        )
        pending_msg = escape(
            d.get("prefire_message")
            or f"The {today_str.title()} card publishes at T-2 ({t2_fire}). No picks are shown before that window."
        )
        games_html = f"""    <article class="game-module" data-game="PENDING">
      <header class="game-header">
        <div class="game-num mono">—</div>
        <div class="game-meta">
          <h2 class="game-matchup">May25 slate armed — awaiting T-2 publish</h2>
          <p class="game-pitchers mono">Autonomous fire {t2_fire} · {n_games} games · {n_pos} positions expected</p>
        </div>
        <div class="game-time mono">{t2_fire}</div>
      </header>
      <div class="market-grid">
      <div class="market-panel">
        <div class="market-label">STATUS</div>
        <div class="market-panel-head">
          <span class="pick-headline">PREFIRE PENDING</span>
          <span class="tier-badge tier-badge--moderate">SCHEDULED</span>
        </div>
        <div class="rationale-copy">
          <p>{pending_msg}</p>
          <p>Prior completed slates remain on Results. This page does not display yesterday&apos;s card as today&apos;s active slate.</p>
        </div>
      </div>
      </div>
    </article>"""
    else:
        board_title = "TODAY'S CARD"
        meta_line = f"{escape(today_str)} · {n_games} GAMES · {n_pos} POSITIONS · {model_lbl}"
        factual = factual_rationales_for_payload(d)
        games_html = build_games_html(games, factual)
    grading_banner = escape(d.get("grading_banner") or "")
    banner_html = ""
    if grading_banner:
        banner_html = f"""  <div class="section-head picks-board-head grading-truth-banner">
    <div class="meta mono">{grading_banner}</div>
  </div>
"""
    body = f"""<div class="shell">
{SHELL_HERO}
  <nav class="nav">
    <a href="/" class="active">PICKS</a>
    <a href="/results">RESULTS</a>
    <a href="/about">ABOUT</a>
  </nav>
{SPORT_SWITCHER_MLB.format(mlb_href="/picks")}
  <div class="section-head picks-board-head">
    <div class="title">{board_title}</div>
    <div class="meta mono">{meta_line}</div>
  </div>
{banner_html}  <main class="picks-page">
    <div class="picks-board">
{games_html}
    </div>
  </main>
  <div class="tag">THE MATH SPEAKS.</div>
  <div class="foot mono">APEX RESEARCH · WALK-FORWARD VALIDATED · F5 MARKETS ONLY</div>
</div>"""

    def wrap_page(head: str, mlb_href: str) -> str:
        page_body = body.replace(
            SPORT_SWITCHER_MLB.format(mlb_href="/picks"),
            SPORT_SWITCHER_MLB.format(mlb_href=mlb_href),
            1,
        )
        return f"""<!doctype html>
<html lang="en">
<head>
{head}
{SPORT_SWITCHER_CSS}
</head>
<body>
{page_body}
</body>
</html>"""

    html_root = wrap_page(head_root, "/")
    html_picks = wrap_page(head_picks, "/picks")

    for label, html in (("root", html_root), ("picks", html_picks)):
        ok, missing = verify_branding(html)
        if not ok:
            print(f"WARN branding markers missing ({label}): {missing}", file=sys.stderr)
        if "FLAT 1U" in html or "pick-odds" in html or "<motion" in html:
            print(f"BLOCKED: forbidden public markup in picks page ({label})", file=sys.stderr)
            return 2
        for cls in ("picks-page", "picks-board", "game-module", "market-panel", "rationale-copy"):
            if cls not in html:
                print(f"BLOCKED: missing {cls} ({label})", file=sys.stderr)
                return 2

    INDEX_OUT.write_text(html_root, encoding="utf-8")
    PICKS_OUT.parent.mkdir(parents=True, exist_ok=True)
    PICKS_OUT.write_text(html_picks, encoding="utf-8")
    PICKS_HTML_ALT.write_text(html_picks, encoding="utf-8")
    print(f"WROTE: {INDEX_OUT} ({len(html_root)} bytes)")
    print(f"WROTE: {PICKS_OUT} ({len(html_picks)} bytes)")
    print(f"WROTE: {PICKS_HTML_ALT} ({len(html_picks)} bytes)")
    print(f"STATIC_PICKS_PAGE_BUILT: date={date_iso} games={n_games} positions={n_pos}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
