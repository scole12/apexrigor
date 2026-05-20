#!/usr/bin/env python3
import json, html, sys
from pathlib import Path
from datetime import datetime
import sys as _sys; _sys.path.insert(0, '/opt/apex_site/bin'); _sys.path.insert(0, '/opt/apex_mlb/bin')
from _apex_head import get_head_block, verify_branding
from apex_visual_presentation_guard import guard_write
JSON_PATH = Path("/opt/apex_site/data/results_archive.json")
OUT = Path("/opt/apex_site/results/index.html")
def build():
    if not JSON_PATH.exists():
        print(f"BLOCKED: missing {JSON_PATH}", file=sys.stderr); sys.exit(2)
    d = json.loads(JSON_PATH.read_text())
    season = d.get("season", {}) or {}
    archive = d.get("archive", []) or []
    baseline = d.get("baseline", {}) or {}
    def _date_sort_key(r):
        # Prefer ISO date from _apex_raw, then top-level date_iso, then parse display date
        raw = r.get("_apex_raw") or {}
        iso = raw.get("date_iso") or r.get("date_iso")
        if iso: return iso
        # Fall back: parse "May 14, 2026" -> "2026-05-14"
        import datetime as _dt
        try:
            return _dt.datetime.strptime(r.get("date",""), "%B %d, %Y").strftime("%Y-%m-%d")
        except Exception:
            return "0000-00-00"
    archive_sorted = sorted(archive, key=_date_sort_key, reverse=True)
    # === APEX SEASON ROLLUP: baseline + live archive ===
    # The banner is computed by summing the Replit baseline with every graded
    # archive entry. Every new day flows in automatically.
    def _zero(): return {"W":0,"L":0,"PUSH":0,"VOID":0}
    base_overall = baseline.get("overall") or _zero()
    base_ats     = baseline.get("f5_spread") or _zero()
    base_tot     = baseline.get("f5_total")  or _zero()
    base_rows    = baseline.get("rows", 0)
    sw  = base_overall.get("W",0)
    sl  = base_overall.get("L",0)
    sp  = base_overall.get("PUSH",0)
    sv  = base_overall.get("VOID",0)
    ats = {"W":base_ats.get("W",0), "L":base_ats.get("L",0), "PUSH":base_ats.get("PUSH",0), "VOID":base_ats.get("VOID",0)}
    tot = {"W":base_tot.get("W",0), "L":base_tot.get("L",0), "PUSH":base_tot.get("PUSH",0), "VOID":base_tot.get("VOID",0)}
    s_rows = base_rows
    for _r in archive:
        _raw = _r.get("_apex_raw") or {}
        sw += _raw.get("w",0); sl += _raw.get("l",0)
        sp += _raw.get("push",0); sv += _raw.get("void",0)
        s_rows += _raw.get("rows",0)
        _bm = _raw.get("by_market", {})
        for _m_key, _dst in (("F5_ATS",ats),("F5_TOT",tot)):
            _b = _bm.get(_m_key, {}) or {}
            for _k in _dst.keys():
                _dst[_k] += _b.get(_k,0)
    s_record = f"{sw:,}-{sl:,}"
    if sp: s_record += f"-{sp}P"
    s_wr = f"{(sw/(sw+sl))*100:.1f}%" if (sw+sl) > 0 else ""
    def fmt_market(m):
        w = m.get("W",0); l = m.get("L",0); p = m.get("PUSH", m.get("push",0))
        s = f"{w}-{l}"
        if p: s += f"-{p}P"
        return s
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
    <div class="meta mono">{html.escape(today_str)} · {s_rows} POSITIONS GRADED</div>
  </div>
  <div class="banner">
    <div class="cell"><div class="label">Overall</div><div class="val mono">{html.escape(s_record)}</div></div>
    <div class="cell"><div class="label">Win Rate</div><div class="val mono">{html.escape(s_wr)}</div></div>
    <div class="cell"><div class="label">F5 Spread</div><div class="val mono">{html.escape(fmt_market(ats))}</div></div>
    <div class="cell"><div class="label">F5 Total</div><div class="val mono">{html.escape(fmt_market(tot))}</div></div>
  </div>
  <div class="section-head">
    <div class="title">DAILY ARCHIVE</div>
    <div class="meta mono">{len(archive_sorted)} ENTRIES</div>
  </div>
  <table class="results">
    <thead><tr><th>Date</th><th>Record</th><th>Win Rate</th><th>Summary</th></tr></thead>
    <tbody>
{archive_html}
    </tbody>
  </table>
  <div class="tag">THE MATH SPEAKS.</div>
  <div class="foot mono">APEX RESEARCH · WALK-FORWARD VALIDATED · F5 MARKETS ONLY</div>
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
