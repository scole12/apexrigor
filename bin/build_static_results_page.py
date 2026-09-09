#!/usr/bin/env python3
import html, json, os, sys
from pathlib import Path
from datetime import datetime
RELEASE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(RELEASE_ROOT / "bin"))
sys.path.insert(0, str(RELEASE_ROOT / "lib" / "pipeline"))
from _apex_head import get_head_block, verify_branding

from apex_visual_presentation_guard import guard_write
from apex_canonical_results_summary import build_canonical_results_summary
from apex_tier_grading_authority import (
    SITE_TIER_SUMMARY_PATH,
    SITE_TIER_DAILY_ARCHIVE_PATH,
    tier_rows_for_display,
)
SITE_ROOT = Path(os.environ.get("APEX_SITE_ROOT", "/opt/apex_site"))
JSON_PATH = SITE_ROOT / "data/results_archive.json"
SITE_DATA = SITE_ROOT / "data"
OUT = SITE_ROOT / "results/index.html"


def _parse_record(rec: str) -> dict[str, int]:
    parts = [p.strip() for p in str(rec or "0-0-0").split("-")]
    w = int(parts[0]) if parts else 0
    l = int(parts[1]) if len(parts) > 1 else 0
    p = int(str(parts[2]).replace("P", "").replace("p", "")) if len(parts) > 2 else 0
    return {"W": w, "L": l, "PUSH": p}


def _fmt_market(m: dict) -> str:
    w = m.get("W", 0)
    l = m.get("L", 0)
    p = m.get("PUSH", m.get("push", 0))
    s = f"{w}-{l}"
    if p:
        s += f"-{p}P"
    return s


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
    meta = f"{games} GAMES · {len(rows)} POSITIONS ISSUED · {terminal} W/L/P SETTLED"
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
        # NCAAF-shaped single as-issued era over ALL living-authority graded
        # positions (windows.all_time). Dual LEGACY/CALIBRATED brackets are
        # forbidden on the public MLB Results surface.
        disp = tier_rows_for_display(tier_summary, "all_time")
        if not (disp.get("ats_by_tier") and disp.get("totals_by_tier") and disp.get("combined_by_tier")):
            raise RuntimeError("FAIL_CLOSED:missing_all_time_tier_tables")
        by_era = tier_summary.get("tier_records_by_era") or {}
        all_time = (tier_summary.get("windows") or {}).get("all_time") or {}
        if by_era and all_time:
            for market_key in ("ats_by_tier", "totals_by_tier", "combined_by_tier"):
                for tier_name in ("WEAK", "MODERATE", "STRONG", "ELITE"):
                    a = ((all_time.get(market_key) or {}).get(tier_name) or {})
                    w = sum(int((((by_era.get(e) or {}).get(market_key) or {}).get(tier_name) or {}).get("W") or 0) for e in by_era)
                    l = sum(int((((by_era.get(e) or {}).get(market_key) or {}).get(tier_name) or {}).get("L") or 0) for e in by_era)
                    p = sum(int((((by_era.get(e) or {}).get(market_key) or {}).get(tier_name) or {}).get("P") or 0) for e in by_era)
                    if int(a.get("W") or 0) != w or int(a.get("L") or 0) != l or int(a.get("P") or 0) != p:
                        raise RuntimeError(
                            f"FAIL_CLOSED:all_time_era_sum_mismatch:{market_key}:{tier_name}"
                        )

        def _MONTH(iso: str) -> str:
            raw = str(iso or "")[:10]
            try:
                return datetime.strptime(raw, "%Y-%m-%d").strftime("%B %-d, %Y").upper()
            except Exception:
                return raw or ""

        daily_archive = (
            json.loads(SITE_TIER_DAILY_ARCHIVE_PATH.read_text(encoding="utf-8"))
            if SITE_TIER_DAILY_ARCHIVE_PATH.exists()
            else {}
        )
        era_start = (
            daily_archive.get("tier_era_start")
            or tier_summary.get("tier_ledger_era_start")
            or ""
        )
        era_end = (
            daily_archive.get("tier_era_end")
            or tier_summary.get("latest_graded_date")
            or ""
        )
        if not era_start or not era_end:
            raise RuntimeError("FAIL_CLOSED:missing_as_issued_date_range")
        era_meta = f"{_MONTH(era_start)} — {_MONTH(era_end)}"
        era = "AS_ISSUED"

        def _tier_rows_body(rows: list, market: str) -> str:
            return "".join(
                f"""      <tr data-apex-tier-era="{html.escape(era)}" data-apex-tier-market="{html.escape(market)}" data-apex-tier="{html.escape(r['tier'].upper())}" data-apex-record="{html.escape(r['record'])}" data-apex-win-rate="{html.escape(r['win_pct'])}">
        <td class="mono">{html.escape(r['tier'])}</td>
        <td class="mono">{html.escape(r['record'])}</td>
        <td class="mono muted">{html.escape(r['win_pct'])}</td>
      </tr>\n"""
                for r in rows
            )

        def _tier_table(rows: list, market: str) -> str:
            return f"""  <table class="results">
    <thead><tr><th>Tier</th><th>Record</th><th>Win Rate</th></tr></thead>
    <tbody>
{_tier_rows_body(rows, market)}    </tbody>
  </table>
"""

        tier_html = (
            '  <div class="section-head">\n'
            '    <div class="title">AS-ISSUED TIER PERFORMANCE</div>\n'
            f'    <div class="meta mono">{html.escape(era_meta)}</div>\n'
            "  </div>\n"
            '  <div class="tier-grid">\n'
            '    <div class="tier-col">\n'
            '      <div class="tier-sub">ATS BY CONFIDENCE TIER</div>\n'
            + _tier_table(disp["ats_by_tier"], "ATS")
            + "    </div>\n"
            '    <div class="tier-col">\n'
            '      <div class="tier-sub">TOTALS BY CONFIDENCE TIER</div>\n'
            + _tier_table(disp["totals_by_tier"], "TOTALS")
            + "    </div>\n"
            "  </div>\n"
            '  <div class="tier-sub">COMBINED MLB BY CONFIDENCE TIER</div>\n'
            '  <div class="tier-single">\n'
            + _tier_table(disp["combined_by_tier"], "COMBINED")
            + "  </div>\n"
        )
        banned = (
            "LEGACY AS-ISSUED",
            "LEGACY TIER ERA",
            "LEGACY_AS_ISSUED",
            "CURRENT MAX-WIN CALIBRATED",
            "CALIBRATED CONFIDENCE ERA",
            "data-apex-tier-era=\"CALIBRATED_CONFIDENCE\"",
            "data-apex-tier-era=\"LEGACY_AS_ISSUED\"",
            "F5 ATS BY CONFIDENCE TIER",
            "F5 TOTALS BY CONFIDENCE TIER",
        )
        for token in banned:
            if token in tier_html:
                raise RuntimeError(f"FAIL_CLOSED:banned_token_in_tier_html:{token}")

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
  <div class="apex-nav-stack">
  <nav class="sport-nav" aria-label="Sport selector">
    <a href="/" class="active" aria-current="true">MLB</a>
    <a href="/ncaaf">NCAA FOOTBALL</a>
    <a href="/nfl">NFL</a>
    <a href="/mma">MMA / UFC</a>
  </nav>
  <nav class="section-nav" aria-label="MLB sections">
    <a href="/">PICKS</a>
    <a href="/results" class="active">RESULTS</a>
    <a href="/about">ABOUT</a>
  </nav>
  </div>
  <div class="section-head">
    <div class="title">SEASON RECORD</div>
    <div class="meta mono">{html.escape(today_str)} · {s_rows} POSITIONS TRACKED</div>
  </div>
  <div class="banner" data-apex-season-record="{html.escape(s_record)}" data-apex-season-win-rate="{html.escape(s_wr)}" data-apex-ats-record="{html.escape(fmt_market(ats))}" data-apex-totals-record="{html.escape(fmt_market(tot))}">
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
    OUT.write_text(out)
    guard_write(OUT)
    print(f"STATIC_RESULTS_PAGE_BUILT: {OUT}")
if __name__ == "__main__":
    build()
