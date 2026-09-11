#!/usr/bin/env python3
"""Build the MMA results surface from verified issued-position/grade joins.

The public record is an inner join of official issued positions to active
commercial Winner grades. Grade rows are never trusted for display metadata;
matchup, selection, line, and tier always come from the immutable issuance.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

from _mma_public import ROOT
from _mma_forecast_contract import positions_sha256
from apply_cloudflare_web_analytics import BEACON_BLOCK
from apply_vercel_web_analytics import ANALYTICS_BLOCK


CACHE = "mma-total-apex-004"
COMMERCIAL_SOURCE = "PRODUCTION_COMMERCIAL_GRADES"
CANONICAL_MARKET = "WINNER"
MARKET_ALIASES = {
    "WINNER": CANONICAL_MARKET,
    "H2H": CANONICAL_MARKET,
    "METHOD": "METHOD",
    "TIME": "TIME",
}
OUTCOMES = {
    "W": "W",
    "WIN": "W",
    "L": "L",
    "LOSS": "L",
    "P": "P",
    "PUSH": "P",
    "V": "VOID",
    "VOID": "VOID",
    "PENDING": "PENDING",
    "UNSETTLED": "PENDING",
}
TIERS = {"WEAK", "MODERATE", "STRONG", "ELITE"}
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MISSING = object()


class ResultsContractError(ValueError):
    """The public MMA record cannot be proven from its source artifacts."""


def _object(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ResultsContractError(f"{context} must be an object")
    return value


def _rows(value: Any, context: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ResultsContractError(f"{context} must be a list")
    return [_object(row, f"{context}[{index}]") for index, row in enumerate(value)]


def _text(row: dict[str, Any], field: str, context: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ResultsContractError(f"{context} lacks {field}")
    return value


def _count(row: dict[str, Any], field: str, context: str) -> int:
    value = row.get(field, MISSING)
    if type(value) is not int or value < 0:
        raise ResultsContractError(f"{context}.{field} is not a nonnegative integer")
    return value


def _market(value: Any, context: str) -> str:
    if not isinstance(value, str) or value not in MARKET_ALIASES:
        raise ResultsContractError(f"{context} has missing or foreign market {value!r}")
    return MARKET_ALIASES[value]


def _price(row: dict[str, Any], context: str) -> int:
    value = row.get("price", MISSING)
    if isinstance(value, bool) or not isinstance(value, int) or abs(value) < 100:
        raise ResultsContractError(f"{context}.price is not valid American odds")
    return value


def _line(row: dict[str, Any], context: str) -> int | float | None:
    if "line" not in row:
        raise ResultsContractError(f"{context} lacks line")
    value = row["line"]
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ResultsContractError(f"{context}.line must be finite or null")
    return value


def _identity(
    issuance_id: str,
    row: dict[str, Any],
    context: str,
) -> tuple[str, str, str, str, int | float | None]:
    return (
        issuance_id,
        _text(row, "bout_id", context),
        _market(row.get("market"), context),
        _text(row, "selection", context),
        _line(row, context),
    )


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _validate_position(
    row: dict[str, Any],
    issuance_id: str,
    model_sha256: str,
    context: str,
) -> tuple[tuple[str, str, str, str, int | float | None], dict[str, Any]]:
    key = _identity(issuance_id, row, context)
    matchup = _text(row, "matchup", context)
    tier = _text(row, "tier", context)
    if tier not in TIERS:
        raise ResultsContractError(f"{context} has foreign tier {tier!r}")
    if row.get("sportsbook") != "FanDuel":
        raise ResultsContractError(f"{context} is not an issued FanDuel position")
    trace = row.get("trace")
    if not isinstance(trace, dict):
        raise ResultsContractError(f"{context} lacks an issuance trace")
    if trace.get("issuance_id") != issuance_id:
        raise ResultsContractError(f"{context} issuance trace conflicts with its event")
    if trace.get("model_sha256") != model_sha256:
        raise ResultsContractError(f"{context} model trace conflicts with its event")
    return key, {
        "bout_id": key[1],
        "market": key[2],
        "selection": key[3],
        "line": key[4],
        "matchup": matchup,
        "tier": tier,
        "price": _price(row, context),
    }


def _validate_grade(
    row: dict[str, Any],
    context: str,
) -> tuple[tuple[str, str, str, str, int | float | None], str, str, int]:
    issuance_id = _text(row, "issuance_id", context)
    key = _identity(issuance_id, row, context)
    source = row.get("source", MISSING)
    if source != COMMERCIAL_SOURCE:
        raise ResultsContractError(f"{context} has missing or foreign source {source!r}")
    grade_id = _text(row, "commercial_grade_id", context)
    raw_result = row.get("result", MISSING)
    try:
        result = OUTCOMES[raw_result]
    except (KeyError, TypeError):
        raise ResultsContractError(f"{context} has unknown commercial result {raw_result!r}") from None
    return key, grade_id, result, _price(row, context)


def _verified_payload(value: dict[str, Any], *, schema: str, context: str) -> None:
    if value.get("schema_version") != schema:
        raise ResultsContractError(f"{context} schema mismatch")
    supplied = value.get("payload_sha256")
    if not isinstance(supplied, str) or not re.fullmatch(r"[0-9a-f]{64}", supplied):
        raise ResultsContractError(f"{context} payload checksum is missing")
    body = dict(value)
    body.pop("payload_sha256", None)
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()
    if hashlib.sha256(encoded).hexdigest() != supplied:
        raise ResultsContractError(f"{context} payload checksum mismatch")


def _summary_mma_counts(summary: dict[str, Any]) -> dict[str, int]:
    sports = _object(summary.get("sports"), "apex_results_summary.sports")
    mma = _object(sports.get("mma"), "apex_results_summary.sports.mma")
    counts = {
        "W": _count(mma, "wins", "apex_results_summary.sports.mma"),
        "L": _count(mma, "losses", "apex_results_summary.sports.mma"),
        "P": _count(mma, "pushes", "apex_results_summary.sports.mma"),
    }
    settled = counts["W"] + counts["L"] + counts["P"]
    for field in ("positions_settled", "settled_n"):
        if _count(mma, field, "apex_results_summary.sports.mma") != settled:
            raise ResultsContractError(f"apex_results_summary.sports.mma.{field} is internally inconsistent")
    return {**counts, "settled": settled}


def _validate_fused_overall(summary: dict[str, Any]) -> dict[str, Any]:
    overall = _object(summary.get("overall"), "apex_results_summary.overall")
    validated = {
        field: _count(overall, field, "apex_results_summary.overall")
        for field in ("wins", "losses", "pushes", "positions_tracked")
    }
    for nested, flat in (
        ("wins", "overall_wins"),
        ("losses", "overall_losses"),
        ("pushes", "overall_pushes"),
    ):
        if flat in summary and _count(summary, flat, "apex_results_summary") != validated[nested]:
            raise ResultsContractError(f"fused Overall mismatch between overall.{nested} and {flat}")
    display = overall.get("win_rate_display")
    if not isinstance(display, str) or not display:
        raise ResultsContractError("apex_results_summary.overall.win_rate_display is missing")
    return {**validated, "win_rate_display": display}


def project_results_ledger(archive: Any) -> dict[str, Any]:
    """Return a deterministic commercial Winner ledger from the MMA archive."""
    archive = _object(archive, "mma_results_archive")
    _verified_payload(
        archive,
        schema="APEX_MMA_RESULTS_ARCHIVE_V1",
        context="mma_results_archive",
    )
    events = _rows(archive.get("events"), "mma_results_archive.events")

    positions: dict[
        tuple[str, str, str, str, int | float | None], dict[str, Any]
    ] = {}
    position_fingerprints: dict[
        tuple[str, str, str, str, int | float | None], str
    ] = {}
    grades: dict[
        tuple[str, str, str, str, int | float | None], tuple[str, str, str]
    ] = {}
    grade_ids: dict[str, tuple[str, str, str, str, int | float | None]] = {}
    issuance_events: dict[str, tuple[str, str]] = {}

    for event_index, event in enumerate(events):
        context = f"mma_results_archive.events[{event_index}]"
        if (
            event.get("official_issuance") is not True
            or event.get("picks_published") is not True
            or event.get("release_state") != "SEALED_RELEASE_AVAILABLE"
            or event.get("issuance_status") not in {"SEALED", "ALREADY_ISSUED"}
        ):
            raise ResultsContractError(f"{context} is not an official published issuance")
        issuance_id = _text(event, "issuance_id", context)
        model_sha256 = _text(event, "active_model_sha256", context)
        if not re.fullmatch(r"[0-9a-f]{64}", model_sha256):
            raise ResultsContractError(f"{context} has an invalid model identity")
        event_object = event.get("event") if isinstance(event.get("event"), dict) else {}
        event_date = event.get("event_date") or event_object.get("event_date")
        if not isinstance(event_date, str) or not DATE.fullmatch(event_date):
            raise ResultsContractError(f"{context} lacks a canonical event date")
        event_name = event.get("event_name") or event_object.get("display_name") or event_object.get("name")
        if not isinstance(event_name, str) or not event_name.strip():
            raise ResultsContractError(f"{context} lacks event_name")

        event_identity = (event_date, event_name)
        if issuance_id in issuance_events and issuance_events[issuance_id] != event_identity:
            raise ResultsContractError(f"issuance {issuance_id!r} is bound to multiple events")
        issuance_events[issuance_id] = event_identity

        raw_positions = _rows(event.get("positions"), f"{context}.positions")
        if event.get("positions_sha256") != positions_sha256(raw_positions):
            raise ResultsContractError(f"{context} issued-position checksum mismatch")

        for position_index, raw_position in enumerate(raw_positions):
            position_context = f"{context}.positions[{position_index}]"
            key, display = _validate_position(raw_position, issuance_id, model_sha256, position_context)
            projected = {
                **display,
                "issuance_id": issuance_id,
                "event_date": event_date,
                "event_name": event_name,
                "order": position_index + 1,
            }
            fingerprint = _canonical_json(raw_position)
            if key in positions:
                previous = positions[key]
                if (
                    position_fingerprints[key] != fingerprint
                    or previous["event_date"] != event_date
                    or previous["event_name"] != event_name
                ):
                    raise ResultsContractError(f"conflicting duplicate issued MMA position {key!r}")
                continue
            scope = key[:3]
            if any(existing[:3] == scope for existing in positions):
                raise ResultsContractError(f"multiple issued Winner selections for one bout {scope!r}")
            positions[key] = projected
            position_fingerprints[key] = fingerprint

        grade_collections: list[tuple[str, list[dict[str, Any]]]] = []
        for field in ("latest_results", "results"):
            if field in event:
                grade_collections.append((field, _rows(event[field], f"{context}.{field}")))
        for field, grade_rows in grade_collections:
            for grade_index, raw_grade in enumerate(grade_rows):
                grade_context = f"{context}.{field}[{grade_index}]"
                key, grade_id, result, price = _validate_grade(raw_grade, grade_context)
                if key not in positions:
                    raise ResultsContractError(f"{grade_context} does not exactly match an issued position")
                if price != positions[key]["price"]:
                    raise ResultsContractError(f"{grade_context} price conflicts with its issued position")
                if grade_id in grade_ids and grade_ids[grade_id] != key:
                    raise ResultsContractError(f"commercial grade id {grade_id!r} is bound to multiple positions")
                grade_ids[grade_id] = key
                signature = (grade_id, result, _canonical_json(raw_grade))
                if key in grades:
                    if grades[key] != signature:
                        raise ResultsContractError(f"conflicting duplicate commercial MMA grade {key!r}")
                    continue
                grades[key] = signature

    joined: list[dict[str, Any]] = []
    for key, (_grade_id, result, _fingerprint) in grades.items():
        # Display identity is intentionally sourced only from the sealed issuance.
        if key[2] == CANONICAL_MARKET:
            joined.append({**positions[key], "result": result})
    joined.sort(key=lambda row: (row["event_date"], row["issuance_id"], -row["order"]), reverse=True)

    raw_counts = Counter(row["result"] for row in joined)
    record = {"W": raw_counts["W"], "L": raw_counts["L"], "P": raw_counts["P"]}
    record["settled"] = record["W"] + record["L"] + record["P"]
    return {
        "contract_version": "APEX_MMA_RESULTS_LEDGER_V2",
        "market": CANONICAL_MARKET,
        "source": COMMERCIAL_SOURCE,
        "record": record,
        "rows": joined,
    }


def _mma_fuse_sources(summary: dict[str, Any]) -> dict[str, str]:
    fuse = _object(summary.get("total_apex_fuse"), "apex_results_summary.total_apex_fuse")
    sources = _object(fuse.get("sources"), "apex_results_summary.total_apex_fuse.sources")
    rows = _rows(sources.get("mma"), "apex_results_summary.total_apex_fuse.sources.mma")
    verified: dict[str, str] = {}
    for index, row in enumerate(rows):
        context = f"apex_results_summary.total_apex_fuse.sources.mma[{index}]"
        path = _text(row, "path", context)
        digest = _text(row, "sha256", context)
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ResultsContractError(f"{context}.sha256 is invalid")
        if path in verified:
            raise ResultsContractError(f"duplicate MMA fuse source {path!r}")
        verified[path] = digest
    return verified


def assert_summary_parity(ledger: Any, summary: Any) -> None:
    """Fail unless the joined archive equals the current fused MMA segment."""
    ledger = _object(ledger, "mma_results_ledger")
    summary = _object(summary, "apex_results_summary")
    _validate_fused_overall(summary)
    record = _object(ledger.get("record"), "mma_results_ledger.record")
    expected = _summary_mma_counts(summary)
    if record != expected:
        raise ResultsContractError(
            f"MMA archive/fused-summary parity failure: archive={record!r} summary={expected!r}"
        )
    source_proof = ledger.get("source_proof")
    if source_proof is not None:
        source_proof = _object(source_proof, "mma_results_ledger.source_proof")
        if _mma_fuse_sources(summary) != source_proof:
            raise ResultsContractError("MMA archive/fused-summary source parity failure")


def build_results_ledger(
    archive: Any,
    summary: Any,
    *,
    source_proof: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Project the archive and prove parity with the supplied fused summary."""
    ledger = project_results_ledger(archive)
    if source_proof is not None:
        ledger["source_proof"] = dict(sorted(source_proof.items()))
    assert_summary_parity(ledger, summary)
    return ledger


def _script_json(value: Any) -> str:
    return (
        _canonical_json(value)
        .replace("<", "\\u003c")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


HTML = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,viewport-fit=cover">
<title>APEX — MMA Results</title>
<meta name="description" content="APEX MMA / UFC graded results. Overall is Total Apex forever record.">
<link rel="stylesheet" href="/assets/apex.css?v={CACHE}">
<meta name="theme-color" content="#000000">
<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png">
<link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png">
<link rel="manifest" href="/site.webmanifest">
<link rel="icon" type="image/svg+xml" href="/favicon.svg?v={CACHE}">
{BEACON_BLOCK}
{ANALYTICS_BLOCK}
</head>
<body>
<div class="shell" data-sport="MMA">
  <div class="hero"><div class="hero-mark"><svg viewBox="0 0 44 44" xmlns="http://www.w3.org/2000/svg"><polygon points="22,6 38,36 6,36"/></svg></div><div class="hero-wordmark">APEX</div><div class="hero-rule"></div><div class="hero-tag">MMA / UFC</div><div class="hero-math">The Math Speaks.</div></div>
  <div class="apex-nav-stack">
  <nav class="sport-nav" aria-label="Sport selector">
    <a href="/results">MLB</a>
    <a href="/ncaaf/results">NCAA FOOTBALL</a>
    <a href="/mma/results" class="active" aria-current="true">MMA / UFC</a>
    <a href="/nfl/results">NFL</a>
  </nav>
  <nav class="section-nav" aria-label="MMA sections">
    <a href="/mma">PICKS</a>
    <a href="/mma/results" class="active" aria-current="true">RESULTS</a>
    <a href="/mma/about">ABOUT</a>
  </nav>
  </div>
  <main id="results-root" aria-live="polite"><p class="muted mono">Loading results…</p></main>
  <div class="foot mono">AS-ISSUED PICKS · OFFICIAL BOUT RESULTS · ZERO UNITS</div>
</div>
<script src="/mma/results/render.js?v={CACHE}"></script>
</body>
</html>
'''


def render_javascript(ledger: dict[str, Any]) -> str:
    encoded_ledger = _script_json(ledger)
    return rf'''(() => {{
  "use strict";
  const ledger = {encoded_ledger};
  const root = document.getElementById("results-root");
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}}[c]));
  const integer = (value, field) => {{
    if (!Number.isSafeInteger(value) || value < 0) throw new Error(field + " is not a nonnegative integer");
    return value;
  }};
  const fmtRecord = (w,l,p=0) => `${{w.toLocaleString("en-US")}}-${{l.toLocaleString("en-US")}}${{p?`-${{p}}P`:""}}`;
  const table = (headers, rows) => `<table class="results"><thead><tr>${{headers.map(h=>`<th>${{esc(h)}}</th>`).join("")}}</tr></thead><tbody>${{rows.map(r=>`<tr>${{r.map((c)=>`<td class="mono">${{esc(c)}}</td>`).join("")}}</tr>`).join("")}}</tbody></table>`;

  function verifiedSummary(summary) {{
    if (!summary || !summary.sports || !summary.sports.mma || !summary.overall) throw new Error("fused results summary is incomplete");
    const mma = summary.sports.mma;
    const expected = {{
      W: integer(mma.wins, "sports.mma.wins"),
      L: integer(mma.losses, "sports.mma.losses"),
      P: integer(mma.pushes, "sports.mma.pushes"),
    }};
    expected.settled = expected.W + expected.L + expected.P;
    if (integer(mma.positions_settled, "sports.mma.positions_settled") !== expected.settled ||
        integer(mma.settled_n, "sports.mma.settled_n") !== expected.settled ||
        expected.W !== ledger.record.W || expected.L !== ledger.record.L ||
        expected.P !== ledger.record.P || expected.settled !== ledger.record.settled) throw new Error("MMA archive/fused-summary parity failure");
    if (ledger.source_proof) {{
      const sourceRows = summary.total_apex_fuse?.sources?.mma;
      if (!Array.isArray(sourceRows)) throw new Error("MMA fuse source proof is missing");
      const actual = {{}};
      for (const row of sourceRows) {{
        if (!row || typeof row.path !== "string" || typeof row.sha256 !== "string" ||
            Object.hasOwn(actual, row.path)) throw new Error("MMA fuse source proof is invalid");
        actual[row.path] = row.sha256;
      }}
      const expectedSources = ledger.source_proof;
      const paths = Object.keys(expectedSources).sort();
      if (paths.length !== Object.keys(actual).length ||
          paths.some(path => actual[path] !== expectedSources[path])) throw new Error("MMA archive/fused-summary source parity failure");
    }}
    const overall = summary.overall;
    const fused = {{
      wins: integer(overall.wins, "overall.wins"),
      losses: integer(overall.losses, "overall.losses"),
      pushes: integer(overall.pushes, "overall.pushes"),
      tracked: integer(overall.positions_tracked, "overall.positions_tracked"),
      rate: overall.win_rate_display,
    }};
    if (typeof fused.rate !== "string" || !fused.rate) throw new Error("overall.win_rate_display is missing");
    for (const [nested, flat] of [["wins","overall_wins"],["losses","overall_losses"],["pushes","overall_pushes"]]) {{
      if (Object.hasOwn(summary, flat) && integer(summary[flat], flat) !== fused[nested]) throw new Error("fused Overall mismatch");
    }}
    return fused;
  }}

  async function load() {{
    const response = await fetch("/data/apex_results_summary.json", {{cache:"no-store"}});
    if (!response.ok) throw new Error("summary HTTP "+response.status);
    const summary = await response.json();
    const overall = verifiedSummary(summary);
    const rows = ledger.rows;
    const w = ledger.record.W, l = ledger.record.L, p = ledger.record.P;
    const winnerBanner = fmtRecord(w,l,p);
    const winnerRate = (w+l)?`${{(100*w/(w+l)).toFixed(1)}}%`:"—";
    const byTier = () => ["WEAK","MODERATE","STRONG","ELITE"].map(tier => {{
      const selected = rows.filter(r => r.tier === tier);
      const tw = selected.filter(r => r.result === "W").length;
      const tl = selected.filter(r => r.result === "L").length;
      const tp = selected.filter(r => r.result === "P").length;
      const decided = tw+tl;
      return [tier[0]+tier.slice(1).toLowerCase(), fmtRecord(tw,tl,tp), decided?`${{(100*tw/decided).toFixed(1)}}%`:"—"];
    }});
    const today = new Intl.DateTimeFormat("en-US",{{timeZone:"America/New_York", weekday:"long", month:"long", day:"numeric", year:"numeric"}}).format(new Date()).toUpperCase();
    let html = "";
    html += `<div class="section-head"><div class="title">APEX TOTAL RECORD</div><div class="meta mono">${{esc(today)}} · FOREVER · ${{overall.tracked.toLocaleString("en-US")}} POSITIONS TRACKED</div></div>`;
    html += `<div class="banner" data-apex-season-record="${{esc(fmtRecord(overall.wins,overall.losses,overall.pushes))}}" data-apex-season-win-rate="${{esc(overall.rate)}}">
      <div class="cell"><div class="label">Overall</div><div class="val mono">${{esc(fmtRecord(overall.wins,overall.losses,overall.pushes))}}</div></div>
      <div class="cell"><div class="label">Win Rate</div><div class="val mono">${{esc(overall.rate)}}</div></div>
      <div class="cell"><div class="label">MMA Winner</div><div class="val mono">${{esc(winnerBanner)}}</div></div>
      <div class="cell"><div class="label">Win Rate (H2H)</div><div class="val mono">${{esc(winnerRate)}}</div></div>
    </div>`;
    html += `<div class="section-head"><div class="title">AS-ISSUED TIER PERFORMANCE</div><div class="meta mono">MMA WINNER · AS ISSUED · H2H ONLY</div></div>`;
    html += `<div class="tier-sub">WINNER BY CONFIDENCE TIER</div><div class="tier-single">${{table(["Tier","Record","Win Rate"], byTier())}}</div>`;
    const days = new Map();
    for (const row of rows) {{ if (!days.has(row.event_date)) days.set(row.event_date, []); days.get(row.event_date).push(row); }}
    const sortedDays = Array.from(days).sort(([a],[b]) => b.localeCompare(a));
    html += `<div class="section-head"><div class="title">DAILY ARCHIVE</div></div>`;
    html += table(["Date","Record","Win Rate","Summary"], sortedDays.map(([date, selected]) => {{
      const dw = selected.filter(r => r.result === "W").length;
      const dl = selected.filter(r => r.result === "L").length;
      const dp = selected.filter(r => r.result === "P").length;
      const decided = dw+dl;
      return [date, `${{dw}}W-${{dl}}L${{dp?`-${{dp}}P`:""}}`, decided?`${{(100*dw/decided).toFixed(1)}}%`:"—", `MMA ${{dw}}-${{dl}}`];
    }}));
    for (const [date, selected] of sortedDays) {{
      html += `<div class="section-head"><div class="title">SLATE DETAIL — ${{esc(date)}}</div><div class="meta mono">${{selected.length}} POSITIONS</div></div>`;
      html += table(["Bout","Matchup","Market","Pick","Tier","Result"], selected.map((row) => [`F${{String(row.order).padStart(2,"0")}}`, row.matchup, row.market, row.selection+(row.line===null?"":" "+row.line), row.tier, row.result]));
    }}
    if (!rows.length) html += `<div class="empty-state">MMA RESULTS BEGIN WITH THE FIRST GRADED APEX UFC CARD.</div>`;
    root.innerHTML = html;
  }}
  load().catch(err => {{ root.innerHTML = `<p class="muted">Results temporarily unavailable.</p>`; console.error(err); }});
}})();
'''


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content.rstrip() + "\n", encoding="utf-8")
    temporary.replace(path)


def main(root: Path = ROOT) -> int:
    archive_path = root / "data" / "mma_results_archive.json"
    mma_summary_path = root / "data" / "mma_results_summary.json"
    archive_bytes = archive_path.read_bytes()
    archive = json.loads(archive_bytes)
    summary = json.loads((root / "data" / "apex_results_summary.json").read_text(encoding="utf-8"))
    # Every supported build/publisher path refreshes the fuse immediately
    # before this builder.  Refuse to emit a Results bundle on any parity drift.
    source_paths = [archive_path]
    if mma_summary_path.exists():
        source_paths.append(mma_summary_path)
    source_proof = {
        f"data/{path.name}": hashlib.sha256(path.read_bytes()).hexdigest()
        for path in source_paths
    }
    ledger = build_results_ledger(archive, summary, source_proof=source_proof)
    out = root / "mma" / "results"
    _write_text(out / "render.js", render_javascript(ledger))
    _write_text(out / "index.html", HTML)
    print(
        f"MMA_RESULTS_PATH={out / 'index.html'} "
        f"MMA_RECORD={ledger['record']['W']}-{ledger['record']['L']}-{ledger['record']['P']}P"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
