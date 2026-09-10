"""Fuse saved public graded books; never issue, grade, or open sport authorities."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import date
import hashlib
import json
from pathlib import Path

RESULTS = {"W": "W", "WIN": "W", "L": "L", "LOSS": "L", "P": "PUSH",
           "PUSH": "PUSH", "V": "VOID", "VOID": "VOID", "PENDING": "PENDING"}
FIELDS = {"wins": "W", "losses": "L", "pushes": "PUSH", "voids": "VOID", "pending": "PENDING"}


def _read(path):
    raw = path.read_bytes()
    return json.loads(raw), {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()}


def _count(value):
    if type(value) is not int or value < 0:
        raise ValueError(f"Invalid record count: {value!r}")
    return value


def _result(value):
    try:
        return RESULTS[value]
    except (KeyError, TypeError):
        raise ValueError(f"Unknown recorded outcome: {value!r}") from None


def _segment(rows):
    counts = Counter(_result(row["result"]) for row in rows)
    decided = counts["W"] + counts["L"]
    settled = decided + counts["PUSH"]
    dates = sorted({row["date"] for row in rows if row.get("date") and _result(row["result"]) != "PENDING"})
    latest = dates[-1] if dates else ""
    rate = round(100 * counts["W"] / decided, 1) if decided else None
    return {
        **{field: counts[result] for field, result in FIELDS.items()}, "other": 0,
        "win_rate": rate, "win_rate_display": f"{rate:.1f}%" if rate is not None else "—",
        "positions_tracked": len(rows), "positions_graded": len(rows),
        "positions_settled": settled, "decided_n": decided, "settled_n": settled,
        "tracked_n": len(rows), "slates_graded": len(dates), "graded_slate_count": len(dates),
        "latest_graded_date": latest or None,
        "latest_graded_date_display": date.fromisoformat(latest).strftime("%B %d, %Y") if latest else "",
    }


def _record_text(segment):
    return f"{segment['wins']}W-{segment['losses']}L-{segment['pushes']}P"


def mma_segment(data_dir):
    """Union the cumulative event archive with the latest commercial Winner book."""
    rows, sources = {}, []
    duplicates = 0

    def add(items, event_date=None):
        nonlocal duplicates
        for item in items:
            if item.get("market") not in {"WINNER", "H2H"}:
                continue
            if item.get("source") != "PRODUCTION_COMMERCIAL_GRADES":
                continue
            identity = (item.get("issuance_id"), item.get("bout_id"), "WINNER")
            if not all(identity) or not item.get("commercial_grade_id"):
                raise ValueError("MMA commercial grade missing issued bout identity")
            outcome = _result(item["result"])
            row = {"identity": identity, "result": outcome,
                   "grade_id": item["commercial_grade_id"],
                   "date": event_date or str(item.get("graded_at_utc") or "")[:10]}
            if identity in rows:
                previous = rows[identity]
                if (previous["result"], previous["grade_id"]) != (outcome, row["grade_id"]):
                    raise ValueError(f"Conflicting active MMA grade: {identity}")
                duplicates += 1
            else:
                rows[identity] = row

    for name, field in (("mma_results_archive.json", "events[].latest_results"),
                        ("mma_results_summary.json", "latest_event_results")):
        path = data_dir / name
        if not path.exists():
            continue
        payload, source = _read(path)
        if name == "mma_results_archive.json":
            for event in payload["events"]:
                add(event.get("latest_results", []), event.get("event_date"))
        else:
            add(payload["latest_event_results"])
        sources.append({**source, "field": field})
    if not sources:
        return None
    segment = _segment(list(rows.values()))
    segment.update(winner_record=_record_text(segment), source_scope="PRODUCTION_COMMERCIAL_WINNER_H2H",
                   source_files=sources, source_row_count=len(rows), duplicate_rows_ignored=duplicates,
                   deduplication_key="issuance_id + bout_id + WINNER")
    return segment


def cumulative_segment(path):
    payload, source = _read(path)
    rows, identities = [], set()
    for item in payload["positions"]:
        identity = item.get(payload.get("deduplication_key", "position_id")) or item.get("position_id")
        if not identity or identity in identities:
            raise ValueError(f"Missing or duplicate cumulative position: {path}: {identity}")
        identities.add(identity)
        rows.append({**item, "date": item.get("slate_date") or item.get("date")})
    segment = _segment(rows)
    # A season-only aggregate must not silently stand in for a lifetime book.
    expected = payload["lifetime_record"]
    for field, result in FIELDS.items():
        if segment[field] != _count(expected.get(result, 0)):
            raise ValueError(f"Lifetime ledger/count mismatch: {path}: {result}")
    segment.update(source_files=[{**source, "field": "positions", "aggregate_check": "lifetime_record"}],
                   source_row_count=len(rows), source_scope=payload.get("source_scope"))
    return segment


def archive_segment(path, sport):
    """Read active settlement revisions, bound to saved issued positions."""
    payload, source = _read(path)
    if payload.get("sport") != sport.upper():
        raise ValueError(f"Wrong sport archive: {path}")
    issued = {}
    for issuance in payload["issuances"]:
        for position in issuance.get("positions", []):
            key = (issuance["issuance_id"], position["position_id"])
            if key in issued:
                raise ValueError(f"Duplicate issued position: {key}")
            issued[key] = {**position, "date": issuance.get("game_date") or issuance.get("slate_date"),
                           "result": "PENDING"}
    grades = payload["grades"]
    ids = {grade["grade_id"] for grade in grades}
    if len(ids) != len(grades):
        raise ValueError(f"Duplicate grade identity: {path}")
    superseded = set()
    parents = {}
    for grade in grades:
        parent = grade.get("supersedes_grade_id")
        if parent:
            if parent not in ids or parent == grade["grade_id"] or parent in superseded:
                raise ValueError(f"Invalid grade revision: {path}")
            superseded.add(parent)
            parents[grade["grade_id"]] = parent
    for grade_id in parents:
        seen = set()
        while grade_id in parents:
            if grade_id in seen:
                raise ValueError(f"Cyclic grade revisions: {path}")
            seen.add(grade_id)
            grade_id = parents[grade_id]
    settled = set()
    for grade in grades:
        if grade["grade_id"] in superseded:
            continue
        for item in grade["settlements"]:
            key = (grade["issuance_id"], item["position_id"])
            if key not in issued or key in settled:
                raise ValueError(f"Unbound or duplicate active settlement: {key}")
            issued[key]["result"] = _result(item["result"])
            settled.add(key)
    if payload.get("status") == "UNISSUED" and (issued or grades):
        raise ValueError(f"UNISSUED archive contains records: {path}")
    rows = list(issued.values())
    segment = _segment(rows)
    segment.update(status="ACTIVE" if rows else "UNISSUED", source_row_count=len(rows),
                   source_files=[{**source, "field": "issuances[].positions + active grades[].settlements"}])
    for market, field in (("ATS", "ats_record"), ("TOTALS", "totals_record"),
                          ("PROPS", "props_record"), ("DOG_PLUS_1_5", "underdog_plus_1_5_record")):
        segment[field] = _record_text(_segment([row for row in rows if row.get("market") == market]))
    return segment


def fuse_summary(summary, *, data_dir, previous=None):
    """Rebuild from sport segments on every invocation; never add to Overall."""
    data_dir = Path(data_dir)
    fused = deepcopy(summary)
    sports = deepcopy((previous or {}).get("sports", {}))
    sports.update(deepcopy(summary["sports"]))
    if "mlb" not in sports:
        raise ValueError("Existing canonical MLB segment is required")
    for sport in ("nfl", "mma", "ncaaf", "nhl"):
        cumulative = data_dir / f"{sport}_results_cumulative.json"
        archive = data_dir / f"{sport}_results_archive.json"
        if sport == "mma":
            segment = mma_segment(data_dir)
        elif cumulative.exists():
            segment = cumulative_segment(cumulative)
        elif sport in {"nfl", "nhl"} and archive.exists():
            segment = archive_segment(archive, sport)
        elif sport == "ncaaf" and (data_dir / "ncaaf_results_summary.json").exists():
            segment = cumulative_segment(data_dir / "ncaaf_results_summary.json")
        else:
            segment = None
        if segment is not None:
            sports[sport] = {**sports.get(sport, {}), **segment}
    included = []
    for sport, segment in sports.items():
        for field in FIELDS:
            _count(segment.get(field, 0))
        graded = sum(segment.get(field, 0) for field in ("wins", "losses", "pushes", "voids"))
        if graded or sport in {"mlb", "nfl"}:
            included.append(sport)
    order = {sport: index for index, sport in enumerate(("mlb", "nfl", "mma", "ncaaf", "nhl"))}
    included.sort(key=lambda sport: (order.get(sport, len(order)), sport))
    overall = deepcopy(sports["mlb"])
    for field in (*FIELDS, "other"):
        overall[field] = sum(_count(sports[sport].get(field, 0)) for sport in included)
    overall["decided_n"] = overall["wins"] + overall["losses"]
    overall["positions_settled"] = overall["settled_n"] = overall["decided_n"] + overall["pushes"]
    overall["positions_tracked"] = overall["tracked_n"] = overall["positions_graded"] = sum(
        overall[field] for field in (*FIELDS, "other"))
    overall["slates_graded"] = sum(_count(sports[s].get("slates_graded", sports[s].get("graded_slate_count", 0))) for s in included)
    rate = round(100 * overall["wins"] / overall["decided_n"], 1) if overall["decided_n"] else None
    overall["win_rate"] = rate
    overall["win_rate_display"] = f"{rate:.1f}%" if rate is not None else "—"
    latest = max(sports[s].get("latest_graded_date") or "" for s in included)
    overall["latest_graded_date"] = latest
    overall["latest_graded_date_display"] = date.fromisoformat(latest).strftime("%B %d, %Y") if latest else ""
    fused.update(sports=sports, sports_included=included, overall=overall,
                 positions_graded=overall["positions_graded"], daily_archive_count=overall["slates_graded"],
                 calculation_authority="CANONICAL_SPORT_GRADED_BOOKS",
                 note="Overall = sum of included sport graded books. Settled=W+L+P; tracked=settled+VOID+PENDING+OTHER.")
    for field in ("wins", "losses", "pushes", "win_rate", "win_rate_display"):
        fused[f"overall_{field}"] = overall[field]
    for field in ("latest_graded_date", "latest_graded_date_display"):
        fused[field] = overall[field]
    fused["total_apex_fuse"] = {
        "version": "total_apex_fuse_v2", "builder": str(Path(__file__).resolve()),
        "sources": {sport: sports[sport].get("source_files", []) for sport in included},
        "excluded_ungraded_sports": [sport for sport in sports if sport not in included],
    }
    fused["total_apex_fuse"]["sources"]["mlb"] = [{
        "path": summary.get("source_summary_path", str(data_dir / "results_archive.json")),
        "sha256": summary.get("source_summary_sha256", ""),
        "canonical_receipt_sha256": summary.get("canonical_receipt_sha256", ""),
        "field": "_canonical_grader_receipt_projection.sports.mlb",
    }]
    return fused
