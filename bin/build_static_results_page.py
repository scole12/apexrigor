#!/usr/bin/env python3
import html, json, sys
from pathlib import Path
from datetime import datetime
import sys as _sys; _sys.path.insert(0, '/opt/apex_site/bin'); _sys.path.insert(0, '/opt/apex_mlb/bin')
from _apex_head import get_head_block, verify_branding
import sys

sys.path.insert(0, "/opt/apex_mlb/current/bin")
from apex_visual_presentation_guard import guard_write
from apex_canonical_results_summary import build_canonical_results_summary
from apex_tier_grading_authority import (
    SITE_TIER_SUMMARY_PATH,
    SITE_TIER_DAILY_ARCHIVE_PATH,
    tier_rows_for_display,
)
JSON_PATH = Path("/opt/apex_site/data/results_archive.json")
SUMMARY_PATH = Path("/opt/apex_site/data/apex_results_summary.json")
WC_ARCHIVE_PATH = Path("/opt/apex_site/data/worldcup_results_archive.json")
WC_GRADED_GLOB = "worldcup_results_graded_*.json"
SITE_DATA = Path("/opt/apex_site/data")
OUT = Path("/opt/apex_site/results/index.html")


def _parse_record(rec: str) -> dict[str, int]:
    parts = [p.strip() for p in str(rec or "0-0-0").split("-")]
    w = int(parts[0]) if parts else 0
    l = int(parts[1]) if len(parts) > 1 else 0
    p = int(str(parts[2]).replace("P", "").replace("p", "")) if len(parts) > 2 else 0
    return {"W": w, "L": l, "PUSH": p}


def _fmt_wc_market(m: dict) -> str:
    w = m.get("W", 0)
    l = m.get("L", 0)
    p = m.get("PUSH", m.get("push", 0))
    return f"{w}-{l}-{p}P"


def _fmt_market(m: dict) -> str:
    w = m.get("W", 0)
    l = m.get("L", 0)
    p = m.get("PUSH", m.get("push", 0))
    s = f"{w}-{l}"
    if p:
        s += f"-{p}P"
    return s


def _grade_to_wlp(grade: str) -> dict[str, int]:
    g = (grade or "").upper()
    if g == "W":
        return {"W": 1, "L": 0, "PUSH": 0}
    if g == "P":
        return {"W": 0, "L": 0, "PUSH": 1}
    return {"W": 0, "L": 1, "PUSH": 0}


def _add_wlp(base: dict, add: dict) -> None:
    for k in ("W", "L", "PUSH"):
        base[k] = base.get(k, 0) + add.get(k, 0)


def compute_worldcup_display_stats() -> dict | None:
    """Roll up complete graded World Cup days from canonical archive + per-day JSON."""
    if not WC_ARCHIVE_PATH.exists():
        return None
    archive = json.loads(WC_ARCHIVE_PATH.read_text(encoding="utf-8"))
    overall = {"W": 0, "L": 0, "PUSH": 0}
    goal_line = {"W": 0, "L": 0, "PUSH": 0}
    total_goals = {"W": 0, "L": 0, "PUSH": 0}
    positions = 0
    days_included: list[str] = []
    for day in archive.get("days") or []:
        if day.get("positions_pending", 0):
            continue
        graded_date = day.get("graded_date", "")
        if not graded_date:
            continue
        graded_path = SITE_DATA / f"worldcup_results_graded_{graded_date}.json"
        if not graded_path.exists():
            continue
        payload = json.loads(graded_path.read_text(encoding="utf-8"))
        rows = payload.get("position_rows") or []
        day_positions = 0
        for row in rows:
            if row.get("grade_status") != "graded":
                continue
            wlp = _grade_to_wlp(row.get("grade", ""))
            _add_wlp(overall, wlp)
            mt = (row.get("market_type") or "").upper()
            if "TOTAL" in mt:
                _add_wlp(total_goals, wlp)
            else:
                _add_wlp(goal_line, wlp)
            day_positions += 1
        if day_positions:
            days_included.append(graded_date)
            positions += day_positions
    if not positions:
        return None
    decided = overall["W"] + overall["L"]
    win_rate = round((overall["W"] / decided) * 100, 1) if decided else 0.0
    return {
        "days_included": days_included,
        "positions_graded": positions,
        "overall": overall,
        "goal_line": goal_line,
        "total_goals": total_goals,
        "overall_record": _fmt_wc_market(overall),
        "goal_line_record": _fmt_wc_market(goal_line),
        "total_goals_record": _fmt_wc_market(total_goals),
        "win_rate_display": f"{win_rate:.1f}%",
    }


def build_latest_slate_detail() -> str:
    """Per-position detail for the most recent graded MLB slate.

    Every issued position is listed, including ones that are pending or void.
    A slate is not represented honestly if an unresolved game is left off, and a
    doubleheader needs both halves shown as separate games.
    """
    paths = sorted(SITE_DATA.glob("results_graded_2026-*.json"))
    if not paths:
        return ""
    latest = paths[-1]
    try:
        payload = json.loads(latest.read_text())
    except Exception:
        return ""
    rows = payload.get("position_rows") or []
    if not rows:
        return ""
    iso = payload.get("graded_date") or ""
    try:
        label = datetime.strptime(iso, "%Y-%m-%d").strftime("%B %d, %Y")
    except Exception:
        label = iso

    def _status(raw: str) -> str:
        o = (raw or "").upper()
        return {"P": "PUSH", "PEND": "PENDING"}.get(o, o) or "PENDING"

    terminal = sum(1 for r in rows if _status(r.get("outcome", "")) in ("W", "L", "PUSH"))
    pend = sum(1 for r in rows if _status(r.get("outcome", "")) == "PENDING")
    void = sum(1 for r in rows if _status(r.get("outcome", "")) == "VOID")
    games = len({str(r.get("game_pk") or r.get("game_num") or "") for r in rows})
    meta = f"{games} GAMES · {len(rows)} POSITIONS ISSUED · {terminal} GRADED"
    if pend:
        meta += f" · {pend} PENDING"
    if void:
        meta += f" · {void} VOID"

    body = ""
    for r in sorted(rows, key=lambda x: (str(x.get("game_num") or ""), str(x.get("market") or ""))):
        st = _status(r.get("outcome", ""))
        cls = {"W": "win", "L": "loss"}.get(st, "muted")
        body += (
            "      <tr>"
            f'<td class="mono muted">{html.escape(str(r.get("game_num") or ""))}</td>'
            f'<td>{html.escape(str(r.get("matchup") or ""))}</td>'
            f'<td class="mono muted">{html.escape(str(r.get("market") or ""))}</td>'
            f'<td class="mono">{html.escape(str(r.get("pick") or ""))}</td>'
            f'<td class="mono muted">{html.escape(str(r.get("tier") or ""))}</td>'
            f'<td class="mono {cls}">{html.escape(st)}</td>'
            "</tr>\n"
        )
    return (
        '  <div class="section-head">\n'
        f'    <div class="title">SLATE DETAIL — {html.escape(label)}</div>\n'
        f'    <div class="meta mono">{html.escape(meta)}</div>\n'
        "  </div>\n"
        '  <table class="results">\n'
        "    <thead><tr><th>Game</th><th>Matchup</th><th>Market</th>"
        "<th>Pick</th><th>Tier</th><th>Result</th></tr></thead>\n"
        f"    <tbody>\n{body}    </tbody>\n  </table>\n"
    )


def build():
    if not JSON_PATH.exists():
        print(f"BLOCKED: missing {JSON_PATH}", file=sys.stderr); sys.exit(2)
    d = json.loads(JSON_PATH.read_text())
    summary = build_canonical_results_summary(d)
    if SUMMARY_PATH.exists():
        ms = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
        if "worldcup" in (ms.get("sports_included") or []):
            summary = ms
    season = d.get("season", {}) or {}
    archive = d.get("archive", []) or []
    baseline = d.get("baseline", {}) or {}
    def _date_sort_key(r):
        raw = r.get("_apex_raw") or {}
        iso = raw.get("date_iso") or r.get("date_iso")
        if iso: return iso
        import datetime as _dt
        try:
            return _dt.datetime.strptime(r.get("date",""), "%B %d, %Y").strftime("%Y-%m-%d")
        except Exception:
            return "0000-00-00"
    archive_sorted = sorted(archive, key=_date_sort_key, reverse=True)
    overall = summary.get("overall") or {}
    mlb = (summary.get("sports") or {}).get("mlb") or overall
    sw = overall.get("wins", 0)
    sl = overall.get("losses", 0)
    sp = overall.get("pushes", 0)
    s_rows = overall.get("positions_graded", 0)
    s_record = f"{sw:,}-{sl:,}"
    if sp: s_record += f"-{sp}P"
    s_wr = overall.get("win_rate_display") or ""
    ats = mlb.get("f5_spread_raw") or {}
    tot = mlb.get("f5_total_raw") or {}
    def fmt_market(m):
        return _fmt_market(m)
    def _strip_ver_tag(s):
        import re as _re
        return _re.sub(r"\s*\(\d+V\)\s*$", "", str(s or ""), flags=_re.I)
    rows_html = []
    for r in archive_sorted:
        rows_html.append(f"""      <tr>
        <td class="mono">{html.escape(str(r.get("date","")))}</td>
        <td class="mono">{html.escape(_strip_ver_tag(str(r.get("record",""))))}</td>
        <td class="mono muted">{html.escape(str(r.get("win_rate","")))}</td>
        <td class="muted">{html.escape(str(r.get("summary","")))}</td>
      </tr>""")
    archive_html = "\n".join(rows_html)

    tier_html = ""
    if SITE_TIER_SUMMARY_PATH.exists():
        tier_summary = json.loads(SITE_TIER_SUMMARY_PATH.read_text(encoding="utf-8"))
        disp = tier_rows_for_display(tier_summary, "all_time")
        daily_archive = (
            json.loads(SITE_TIER_DAILY_ARCHIVE_PATH.read_text(encoding="utf-8"))
            if SITE_TIER_DAILY_ARCHIVE_PATH.exists()
            else {}
        )

        def _MONTH(iso: str) -> str:
            try:
                return datetime.strptime(iso, "%Y-%m-%d").strftime("%B %-d, %Y").upper()
            except Exception:
                return iso or ""

        era_start = daily_archive.get("tier_era_start") or tier_summary.get("tier_ledger_era_start", "")
        era_end = daily_archive.get("tier_era_end") or tier_summary.get("latest_graded_date", "")
        era_label = f"VERIFIED TIER ERA · {_MONTH(era_start)} — {_MONTH(era_end)}"

        def _tier_rows_body(rows: list) -> str:
            return "".join(
                f"""      <tr>
        <td class="mono">{html.escape(r['tier'])}</td>
        <td class="mono">{html.escape(r['record'])}</td>
        <td class="mono muted">{html.escape(r['win_pct'])}</td>
      </tr>\n"""
                for r in rows
            )

        def _tier_table(rows: list) -> str:
            return f"""  <table class="results">
    <thead><tr><th>Tier</th><th>Record</th><th>Win Rate</th></tr></thead>
    <tbody>
{_tier_rows_body(rows)}    </tbody>
  </table>
"""

        # Two-column desktop (ATS | Totals), stacked on mobile via .tier-grid
        two_col = (
            '  <div class="tier-grid">\n'
            '    <div class="tier-col">\n'
            '      <div class="tier-sub">F5 ATS BY CONFIDENCE TIER</div>\n'
            + _tier_table(disp["ats_by_tier"])
            + "    </div>\n"
            '    <div class="tier-col">\n'
            '      <div class="tier-sub">F5 TOTALS BY CONFIDENCE TIER</div>\n'
            + _tier_table(disp["totals_by_tier"])
            + "    </div>\n"
            "  </div>\n"
        )

        # Combined (diagnostic only) beneath
        combined_html = (
            '  <div class="tier-sub">COMBINED MLB BY CONFIDENCE TIER</div>\n'
            '  <div class="tier-single">\n'
            + _tier_table(disp["combined_by_tier"])
            + "  </div>\n"
        )

        tier_html = (
            '  <div class="section-head">\n'
            '    <div class="title">MLB TIER PERFORMANCE</div>\n'
            f'    <div class="meta mono">{html.escape(era_label)}</div>\n'
            "  </div>\n"
            + two_col
            + combined_html
        )

    slate_html = build_latest_slate_detail()

    today_str = datetime.now().strftime("%A, %B %d, %Y").upper()
    HEAD_BLOCK = get_head_block("APEX — Results", "/results", "APEX Quantitative Forecasting — graded daily results archive.")
    out = f"""<!doctype html>
<html lang="en">
<head>
{HEAD_BLOCK}
</head>
<body>
<div class="shell">
  <div class="hero">
    <div class="hero-mark">
      <svg viewBox="0 0 44 44" xmlns="http://www.w3.org/2000/svg"><polygon points="22,6 38,36 6,36"/></svg>
    </div>
    <div class="hero-wordmark">APEX</div>
    <div class="hero-rule"></div>
    <div class="hero-tag">QUANTITATIVE FORECASTING</div>
    <div class="hero-math">The Math Speaks.</div>
  </div>
  <nav class="nav">
    <a href="/">PICKS</a>
    <a href="/results" class="active">RESULTS</a>
    <a href="/about">ABOUT</a>
  </nav>
  <div class="section-head">
    <div class="title">SEASON RECORD</div>
    <div class="meta mono">{html.escape(today_str)} · {s_rows} POSITIONS TRACKED</div>
  </div>
  <div class="banner">
    <div class="cell"><div class="label">Overall</div><div class="val mono">{html.escape(s_record)}</div></div>
    <div class="cell"><div class="label">Win Rate</div><div class="val mono">{html.escape(s_wr)}</div></div>
    <div class="cell"><div class="label">F5 Spread</div><div class="val mono">{html.escape(fmt_market(ats))}</div></div>
    <div class="cell"><div class="label">F5 Total</div><div class="val mono">{html.escape(fmt_market(tot))}</div></div>
  </div>
{tier_html}  <div class="section-head">
    <div class="title">DAILY ARCHIVE</div>
  </div>
  <table class="results">
    <thead><tr><th>Date</th><th>Record</th><th>Win Rate</th><th>Summary</th></tr></thead>
    <tbody>
{archive_html}
    </tbody>
  </table>
{slate_html}  <div class="tag">THE MATH SPEAKS.</div>
</div>
</body>
</html>
"""
    OUT.parent.mkdir(exist_ok=True, parents=True)
    _ok, _missing = verify_branding(out)
    if not _ok:
        raise RuntimeError(f"BRANDING_CONTRACT_VIOLATION: results page missing tags: {_missing}")
    guard_write(OUT)
    OUT.write_text(out)
    print(f"STATIC_RESULTS_PAGE_BUILT: {OUT}")
if __name__ == "__main__":
    build()
