#!/usr/bin/env python3
"""Build public NCAA payloads from certified authorities and immutable production state."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Mapping
from zoneinfo import ZoneInfo


SITE = Path(__file__).resolve().parents[1]
DATA = SITE / "data"
VAR = Path("/var/opt/apex_ncaaf")
TEAM = VAR / "authorities/TEAM_LINEUP.db"
OUTCOMES = VAR / "authorities/HISTORICAL_OUTCOMES_WITH_ODDS.db"
STATE = VAR / "production"
NY = ZoneInfo("America/New_York")


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = canonical(value)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def ro(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def active_payloads(table: str, key: str, database: Path, where: str = "") -> dict[str, dict[str, Any]]:
    connection = ro(database)
    rows = connection.execute(
        f"SELECT {key},payload_json FROM {table} WHERE record_status='ACTIVE' {where} ORDER BY rowid"
    ).fetchall()
    connection.close()
    return {str(row[0]): json.loads(row[1]) for row in rows}


def latest_capture(slate_date: str) -> dict[str, Any] | None:
    paths = sorted((STATE / "market_captures" / slate_date / "receipts").glob("*.json"))
    return None if not paths else json.loads(paths[-1].read_text(encoding="utf-8"))


def team_metadata() -> tuple[dict[str, str], dict[str, str]]:
    identities = active_payloads("team_identity_status_versions", "team_id", TEAM)
    subdivisions = active_payloads("subdivision_history_versions", "team_id", TEAM, "AND season=2026")
    names = {team_id: str(payload.get("school") or payload.get("team") or team_id) for team_id, payload in identities.items()}
    divisions = {team_id: str(payload.get("classification") or "UNRESOLVED").upper() for team_id, payload in subdivisions.items()}
    return names, divisions


def venue_names() -> dict[str, str]:
    payloads = active_payloads("venue_identity_status_versions", "venue_id", TEAM)
    return {venue_id: str(payload.get("name") or "Venue not published") for venue_id, payload in payloads.items()}


def public_position(position: Mapping[str, Any], card: Mapping[str, Any]) -> dict[str, Any]:
    engine = str(position["market_type"])
    selection = str(position["selected_team_name"] if engine == "ATS" else position["selected_direction"])
    selected_probability = (
        position.get("p_favorite_cover") if engine == "ATS" and position["selected_direction"] in {"FAVORITE", "SIDE_A"}
        else position.get("p_underdog_cover") if engine == "ATS"
        else position.get("p_over") if position["selected_direction"] == "OVER"
        else position.get("p_under")
    )
    return {
        "market_type": engine,
        "selection": selection,
        "direction": str(position["selected_direction"]),
        "line": str(position["line"]),
        "price": int(position["selected_price_american"]),
        "rating": str(position["rating"]),
        "rationale": list(position.get("rationale") or []),
        "p_selected": float(selected_probability),
        "p_favorite_cover": position.get("p_favorite_cover"),
        "p_push": position.get("p_push"),
        "p_underdog_cover": position.get("p_underdog_cover"),
        "p_over": position.get("p_over"),
        "p_under": position.get("p_under"),
        "model_id": str(card["ats_model_id"] if engine == "ATS" else card["totals_model_id"]),
        "model_sha256": str(card["ats_model_sha256"] if engine == "ATS" else card["totals_model_sha256"]),
        "market_captured_at_utc_ms": int(position["market_captured_at_utc_ms"]),
        "issued_at_utc_ms": int(card["issued_at_utc_ms"]),
    }


def market_display(
    override: Mapping[str, Any] | None,
    market_type: str,
    side_a_name: str,
    side_b_name: str,
) -> dict[str, Any]:
    market = None if override is None else override.get(market_type)
    if not market:
        return {"available": False, "line": None, "price_a": None, "price_b": None, "captured_at_utc_ms": None}
    return {
        "available": True,
        "line": market["line"],
        "price_a": int(market["price_a"]),
        "price_b": int(market["price_b"]),
        "captured_at_utc_ms": int(market["apex_captured_at_utc_ms"]),
        "bookmaker_updated_at_utc_ms": int(market["bookmaker_updated_at_utc_ms"]),
        "sportsbook": "FANDUEL",
        "side_a_name": side_a_name if market_type == "ATS" else "Over",
        "side_b_name": side_b_name if market_type == "ATS" else "Under",
    }


def build_slate(slate_date: str) -> tuple[dict[str, Any], dict[str, Any]]:
    local_start = datetime.fromisoformat(f"{slate_date}T00:00:00").replace(tzinfo=NY)
    local_end = local_start.replace(hour=23, minute=59, second=59, microsecond=999999)
    start_ms = int(local_start.astimezone(timezone.utc).timestamp() * 1000)
    end_ms = int(local_end.astimezone(timezone.utc).timestamp() * 1000)
    connection = ro(OUTCOMES)
    schedules = [dict(row) for row in connection.execute(
        """SELECT game_id,kickoff_utc_ms,home_team_id,away_team_id,venue_id,competition_classification,
                  game_status,record_content_sha256
             FROM game_schedule_versions
            WHERE record_status='ACTIVE' AND kickoff_utc_ms BETWEEN ? AND ?
            ORDER BY kickoff_utc_ms,game_id""", (start_ms, end_ms)
    )]
    connection.close()
    names, divisions = team_metadata()
    venues = venue_names()
    capture = latest_capture(slate_date)
    overrides = {} if capture is None else capture.get("overrides", {})
    games = []
    counts = {"FBS": 0, "FCS": 0, "D1_VS_LOWER_DIVISION": 0, "spread": 0, "total": 0}
    for schedule in schedules:
        game_id = str(schedule["game_id"])
        away_id, home_id = str(schedule["away_team_id"]), str(schedule["home_team_id"])
        away_div, home_div = divisions.get(away_id, "OTHER_OR_UNRESOLVED"), divisions.get(home_id, "OTHER_OR_UNRESOLVED")
        d1 = {"FBS", "FCS"}
        if away_div not in d1 and home_div not in d1:
            continue
        if away_div == "FBS" and home_div == "FBS":
            classification = "FBS_V_FBS"
            counts["FBS"] += 1
        elif away_div == "FCS" and home_div == "FCS":
            classification = "FCS_V_FCS"
            counts["FCS"] += 1
        elif away_div in d1 and home_div in d1:
            classification = "FBS_V_FCS"
            counts["FBS"] += 1
        else:
            classification = "D1_VS_LOWER_DIVISION"
            counts["D1_VS_LOWER_DIVISION"] += 1
        market_override = overrides.get(game_id)
        ats_market = market_display(market_override, "ATS", names.get(home_id, home_id), names.get(away_id, away_id))
        totals_market = market_display(market_override, "TOTALS", "Over", "Under")
        counts["spread"] += int(ats_market["available"])
        counts["total"] += int(totals_market["available"])
        issuance_path = STATE / "issuance" / slate_date / f"{game_id}.json"
        card = json.loads(issuance_path.read_text(encoding="utf-8")) if issuance_path.is_file() else None
        positions = [] if card is None else [public_position(position, card) for position in card["positions"]]
        if positions:
            status = "APEX_T2_ISSUANCE_LOCKED"
        elif ats_market["available"] or totals_market["available"]:
            status = "FANDUEL_MARKET_AVAILABLE_APEX_FORECAST_LOCKS_AT_T2"
        elif capture is not None:
            status = "FANDUEL_MARKET_NOT_YET_AVAILABLE"
        else:
            status = "GAME_LISTED_AWAITING_T2_FORECAST"
        kickoff = datetime.fromtimestamp(int(schedule["kickoff_utc_ms"]) / 1000, timezone.utc).astimezone(NY)
        games.append({
            "game_id": game_id, "date": slate_date, "kickoff_utc_ms": int(schedule["kickoff_utc_ms"]),
            "kickoff_et": kickoff.isoformat(), "kickoff_display_et": kickoff.strftime("%-I:%M %p ET"),
            "away_program_id": away_id, "home_program_id": home_id,
            "matchup": f"{names.get(away_id, away_id)} at {names.get(home_id, home_id)}",
            "fbs_fcs_classification": classification, "away_subdivision": away_div, "home_subdivision": home_div,
            "venue": venues.get(str(schedule.get("venue_id") or ""), "Venue not published"),
            "final_status": str(schedule["game_status"]), "market_status": status,
            "fanduel_ats_market_status": "AVAILABLE" if ats_market["available"] else "NOT_AVAILABLE",
            "fanduel_total_market_status": "AVAILABLE" if totals_market["available"] else "NOT_AVAILABLE",
            "ats_market": ats_market, "totals_market": totals_market, "positions": positions,
            "t3_utc_ms": int(schedule["kickoff_utc_ms"]) - 10_800_000,
            "t2_utc_ms": int(schedule["kickoff_utc_ms"]) - 7_200_000,
        })
    source_hashes = {
        "team_lineup_path": str(TEAM),
        "historical_path": str(OUTCOMES),
        "schedule_population_sha256": hashlib.sha256(canonical(sorted(str(row["record_content_sha256"]) for row in schedules))).hexdigest(),
        "market_capture_receipt": None if capture is None else capture.get("receipt_path"),
        "market_capture_sha256": None if capture is None else capture.get("receipt_sha256"),
    }
    slate = {
        "schema_version": "apex.ncaaf.public_slate.2026-08-25.v3", "slate_date_et": slate_date,
        "game_count": len(games), "fbs_game_count": counts["FBS"], "fcs_game_count": counts["FCS"],
        "d1_vs_lower_division_game_count": counts["D1_VS_LOWER_DIVISION"],
        "fanduel_spread_available_count": counts["spread"], "fanduel_total_available_count": counts["total"],
        "games": games,
    }
    return slate, source_hashes


def result_rows() -> list[dict[str, Any]]:
    rows = []
    for path in sorted((STATE / "grades").glob("*/*.json")):
        grade = json.loads(path.read_text(encoding="utf-8"))
        issuance_path = STATE / "issuance" / path.parent.name / f"{grade.get('game_id')}.json"
        if not issuance_path.is_file():
            continue
        card = json.loads(issuance_path.read_text(encoding="utf-8"))
        by_market = {row["market_type"]: row for row in grade.get("settlements", [])}
        for position in card.get("positions", []):
            market = str(position["market_type"])
            settlement = by_market.get(market, {})
            rows.append({
                "date": path.parent.name, "game_id": str(card["game_id"]), "matchup": str(card["matchup"]),
                "market": market, "pick": f"{position.get('selected_team_name') or position['selected_direction']} {position['line']}",
                "tier": str(position["rating"]), "result": str(settlement.get("result") or "PENDING").replace("WIN", "W").replace("LOSS", "L"),
                "grade_id": grade.get("grade_id"), "issuance_id": card.get("issuance_id"),
            })
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    outcomes = ("W", "L", "PUSH", "VOID", "PENDING")
    def record(selected: list[dict[str, Any]]) -> dict[str, int]:
        return {outcome: sum(row["result"] == outcome for row in selected) for outcome in outcomes}
    tiers = ("WEAK", "MODERATE", "STRONG", "ELITE")
    return {
        "schema_version": "apex.public.ncaaf_results_summary.2026-08-25.v2",
        "status": "AWAITING_FIRST_NATURAL_GRADE" if not rows else "ACTIVE",
        "season_record": record(rows),
        "ats_by_tier": {tier: record([row for row in rows if row["market"] == "ATS" and row["tier"] == tier]) for tier in tiers},
        "totals_by_tier": {tier: record([row for row in rows if row["market"] == "TOTALS" and row["tier"] == tier]) for tier in tiers},
        "combined_by_tier": {tier: record([row for row in rows if row["tier"] == tier]) for tier in tiers},
        "graded_position_count": sum(row["result"] != "PENDING" for row in rows),
        "pending_position_count": sum(row["result"] == "PENDING" for row in rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="2026-08-29")
    args = parser.parse_args()
    slate, sources = build_slate(args.date)
    envelope = {
        "schema_version": "apex.public.ncaaf_today.2026-08-25.v2", "sport": "NCAA_DIVISION_I_FOOTBALL",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "sources": sources,
        "public_contract_fields": ["matchup", "market_type", "selection", "line", "price", "rating", "rationale"],
        "slate": slate,
    }
    archive = result_rows()
    summary = summarize(archive)
    atomic_write(DATA / "ncaaf_today.json", envelope)
    atomic_write(DATA / "ncaaf_results_summary.json", summary)
    atomic_write(DATA / "ncaaf_results_archive.json", archive)
    print(json.dumps({
        "status": "PASS", "slate_date_et": args.date, "game_count": slate["game_count"],
        "spread_available_count": slate["fanduel_spread_available_count"],
        "total_available_count": slate["fanduel_total_available_count"], "grade_row_count": len(archive),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
