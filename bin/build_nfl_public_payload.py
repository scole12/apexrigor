#!/usr/bin/env python3
"""Build the truth-only NFL public state from production-owned authorities.

This is an operator-run release builder.  It is intentionally not part of the
Vercel build: the deployment environment must never substitute for the APEX
Droplet's read-only authority boundary.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
HIST = Path("/var/opt/apex_nfl/authorities/HISTORICAL_OUTCOMES_WITH_ODDS.db")
TEAM = Path("/var/opt/apex_nfl/authorities/TEAM_LINEUP.db")
CURRENT = Path("/var/opt/apex_nfl/state/t3_living/current.json")
ACCEPTANCE = Path(
    "/opt/apex_principal_engineer/reports/evidence/"
    "nfl_final_reconciliation_20260904/NFL_FINAL_RECONCILIATION_ACCEPTANCE.json"
)
RUNTIME_MANIFEST = Path("/opt/apex_nfl/runtime/PRODUCTION_RUNTIME_MANIFEST.json")
NY = ZoneInfo("America/New_York")


def canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(canonical(value))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def ro(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def load_verified_state() -> tuple[dict[str, Any], dict[str, Any], Path]:
    current = json.loads(CURRENT.read_text(encoding="utf-8"))
    if current.get("status") != "PASS":
        raise RuntimeError("current NFL hydration pointer is not PASS")
    receipt = Path(str(current["receipt_path"]))
    if receipt.parent != CURRENT.parent or not receipt.is_file():
        raise RuntimeError("current NFL hydration receipt is outside canonical state")
    if sha256(receipt) != current.get("receipt_file_sha256"):
        raise RuntimeError("current NFL hydration receipt hash mismatch")
    hydration = json.loads(receipt.read_text(encoding="utf-8"))
    if hydration.get("status") != "PASS" or hydration.get("source_to_target_parity") != "PASS":
        raise RuntimeError("NFL source-to-target hydration is not PASS")
    if hydration.get("retrieval_mode") != "LIVE_NETWORK_RETRIEVAL":
        raise RuntimeError("NFL current state is not backed by live retrieval")
    if hydration.get("public_issuance") is not False:
        raise RuntimeError("unexpected NFL public issuance state")
    acceptance = json.loads(ACCEPTANCE.read_text(encoding="utf-8"))
    required = {
        "NFL_T3_CURRENT_RETRIEVAL": "PASS",
        "NFL_T3_FRESHNESS": "PASS",
        "NFL_T2_IS_REAL_SERVING_IMPLEMENTATION": "YES",
        "NFL_GRADER_IS_REAL_SETTLEMENT_IMPLEMENTATION": "YES",
        "NFL_TECHNICAL_RUNTIME_READY": "YES",
    }
    actual = acceptance.get("acceptance", {})
    for key, expected in required.items():
        if actual.get(key) != expected:
            raise RuntimeError(f"NFL acceptance mismatch: {key}")
    science = acceptance.get("truthful_non_issuance", {})
    if any(science.get(lane) != "NO_QUALIFIED_CHAMPION" for lane in ("ATS", "PROPS", "TOTALS")):
        raise RuntimeError("NFL science gate is not the expected no-champion state")
    expected_manifest_sha = acceptance.get("runtime", {}).get("manifest_sha256")
    if not RUNTIME_MANIFEST.is_file() or sha256(RUNTIME_MANIFEST) != expected_manifest_sha:
        raise RuntimeError("NFL sealed runtime manifest identity mismatch")
    return hydration, acceptance, receipt


def schedule() -> list[dict[str, Any]]:
    team_connection = ro(TEAM)
    names = {
        str(row["team_id"]): str(row["current_name"])
        for row in team_connection.execute(
            "SELECT team_id,current_name FROM teams WHERE active=1 ORDER BY team_id"
        )
    }
    team_connection.close()
    history_connection = ro(HIST)
    rows = history_connection.execute(
        """SELECT game_id,season,week,kickoff_ts,away_team_id,home_team_id,
                  game_status,effective_at,available_at
             FROM canonical_games
            WHERE season=2026 AND season_type='REG' AND week=1
              AND retracted_at IS NULL
            ORDER BY kickoff_ts,game_id"""
    ).fetchall()
    history_connection.close()
    if len(rows) != 16:
        raise RuntimeError(f"NFL Week 1 canonical schedule cardinality is {len(rows)}, expected 16")
    games: list[dict[str, Any]] = []
    for row in rows:
        kickoff = datetime.fromisoformat(str(row["kickoff_ts"]).replace("Z", "+00:00"))
        away_id, home_id = str(row["away_team_id"]), str(row["home_team_id"])
        if away_id not in names or home_id not in names:
            raise RuntimeError(f"unresolved NFL team identity for {row['game_id']}")
        games.append(
            {
                "game_id": str(row["game_id"]),
                "season": int(row["season"]),
                "week": int(row["week"]),
                "kickoff_utc": str(row["kickoff_ts"]),
                "kickoff_et": kickoff.astimezone(NY).isoformat(),
                "away_team_id": away_id,
                "away_team": names[away_id],
                "home_team_id": home_id,
                "home_team": names[home_id],
                "matchup": f"{names[away_id]} at {names[home_id]}",
                "status": str(row["game_status"]),
                "schedule_effective_at_utc": str(row["effective_at"]),
                "schedule_available_at_utc": str(row["available_at"]),
                "positions": [],
            }
        )
    return games


def main() -> int:
    hydration, acceptance, receipt = load_verified_state()
    games = schedule()
    generated_at = str(hydration["completed_at"])
    runtime = acceptance["runtime"]
    science = {
        lane: "NO_QUALIFIED_CHAMPION" for lane in ("ATS", "PROPS", "TOTALS")
    }
    shared = {
        "generated_at_utc": generated_at,
        "technical_status": "TECHNICAL_RUNTIME_READY",
        "scientific_release_state": "SCIENCE_BLOCKED_NO_QUALIFIED_CHAMPION",
        "science": science,
        "public_issuance": False,
        "position_count": 0,
        "hydration": {
            "status": "PASS",
            "retrieval_mode": str(hydration["retrieval_mode"]),
            "retrieved_at_utc": str(hydration["retrieved_at"]),
            "completed_at_utc": generated_at,
            "source_to_target_parity": "PASS",
            "cross_authority_completion": str(
                hydration["cross_authority_completion"]["status"]
            ),
            "receipt_sha256": sha256(receipt),
            "raw_set_sha256": str(hydration["raw_set_sha256"]),
        },
        "runtime": {
            "seal_commit": str(runtime["seal_commit"]),
            "manifest_sha256": str(runtime["manifest_sha256"]),
            "sealed_file_hash_mismatch_count": int(
                runtime["sealed_file_hash_mismatch_count"]
            ),
        },
    }
    today = {
        "schema_version": "APEX_NFL_TODAY_V1",
        "sport": "NFL",
        **shared,
        "slate": {
            "season": 2026,
            "season_type": "REG",
            "week": 1,
            "game_count": len(games),
            "games": games,
        },
        "positions": [],
    }
    system_state = {
        "schema_version": "APEX_NFL_PUBLIC_STATE_V1",
        "sport": "NFL",
        **shared,
        "schedule": {
            "canonical_game_count": 272,
            "week_1_game_count": len(games),
            "active_capture_slot_count": 708,
            "active_cohort_count": 118,
            "week_min": 1,
            "week_max": 18,
            "persistent_timer_count": 4,
        },
    }
    results = {
        "schema_version": "APEX_NFL_RESULTS_SUMMARY_V1",
        "sport": "NFL",
        "generated_at_utc": generated_at,
        "scientific_release_state": shared["scientific_release_state"],
        "issued_position_count": 0,
        "graded_position_count": 0,
        "ungraded_position_count": 0,
        "record": {"wins": 0, "losses": 0, "pushes": 0, "voids": 0},
        "proper_scores": None,
        "message": "No NFL positions have been issued; no performance is claimed.",
    }
    archive = {
        "schema_version": "APEX_NFL_RESULTS_ARCHIVE_V1",
        "sport": "NFL",
        "generated_at_utc": generated_at,
        "issuances": [],
        "grades": [],
    }
    outputs = {
        "nfl_today.json": today,
        "nfl_system_state.json": system_state,
        "nfl_results_summary.json": results,
        "nfl_results_archive.json": archive,
    }
    for name, payload in outputs.items():
        atomic_write(DATA / name, payload)
        print(f"NFL_PUBLIC_PAYLOAD={name} SHA256={sha256(DATA / name)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
