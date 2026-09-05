#!/usr/bin/env python3
"""Build the truth-only NFL public state from production-owned authorities.

This is an operator-run release builder.  It is intentionally not part of the
Vercel build: the deployment environment must never substitute for the APEX
Droplet's read-only authority boundary.
"""

from __future__ import annotations

from datetime import UTC, datetime
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
PLAYER = Path("/var/opt/apex_nfl/authorities/PLAYER.db")
CURRENT = Path("/var/opt/apex_nfl/state/t3_living/current.json")
RUNTIME_MANIFEST = Path("/opt/apex_nfl/runtime/PRODUCTION_RUNTIME_MANIFEST.json")
RELEASE_CURRENT = Path("/var/opt/apex_nfl/releases/current.json")
IMMUTABLE_RELEASE_ROOT = Path("/var/opt/apex_nfl/releases/immutable")
COHORT_ROOT = Path("/var/opt/apex_nfl/state/cohorts")
ISSUANCE_ROOT = Path("/var/opt/apex_nfl/issuance")
GRADE_ROOT = Path("/var/opt/apex_nfl/grades")
PARSER_VERSION = "apex-nfl-2026-pit-cohort-capture-v2.0.0"
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
    # These living authorities use WAL; immutable=1 can ignore committed WAL
    # state.  URI read-only plus query_only observes the canonical snapshot
    # without permitting a write.
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def verify_runtime_manifest() -> dict[str, Any]:
    manifest = json.loads(RUNTIME_MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("schema") != "apex.nfl.production_runtime_manifest.v2":
        raise RuntimeError("NFL runtime manifest schema is invalid")
    mismatches: list[str] = []
    for section in ("entrypoints", "runtime_sources", "migration_sources", "systemd_sources"):
        for relative, expected in (manifest.get(section) or {}).items():
            source = Path("/opt/apex_nfl") / relative
            installed = (
                Path("/etc/systemd/system") / Path(relative).name
                if section == "systemd_sources" else source
            )
            for path in (source, installed) if section == "systemd_sources" else (source,):
                if not path.is_file() or sha256(path) != expected:
                    mismatches.append(str(path))
    return {
        "manifest_sha256": sha256(RUNTIME_MANIFEST),
        "sealed_file_hash_mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "code_commit": manifest.get("code_commit"),
    }


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
    runtime = verify_runtime_manifest()
    if runtime["sealed_file_hash_mismatch_count"]:
        raise RuntimeError("NFL sealed runtime files differ from the current manifest")
    return hydration, runtime, receipt


def schedule(as_of: datetime | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    current = (as_of or datetime.now(UTC)).astimezone(UTC)
    team_connection = ro(TEAM)
    names = {
        str(row["team_id"]): str(row["current_name"])
        for row in team_connection.execute(
            "SELECT team_id,current_name FROM teams WHERE active=1 ORDER BY team_id"
        )
    }
    team_connection.close()
    history_connection = ro(HIST)
    next_identity = history_connection.execute(
        """SELECT season,season_type,week FROM canonical_games
            WHERE season>=2026 AND retracted_at IS NULL
              AND game_status IN ('SCHEDULED','DELAYED','POSTPONED')
              AND kickoff_ts>=?
            ORDER BY kickoff_ts,game_id LIMIT 1""",
        (current.isoformat().replace("+00:00", "Z"),),
    ).fetchone()
    if next_identity is None:
        history_connection.close()
        return [], {"season": 2026, "season_type": None, "week": 0, "canonical_game_count": 0}
    rows = history_connection.execute(
        """SELECT game_id,season,week,kickoff_ts,away_team_id,home_team_id,
                  game_status,effective_at,available_at
             FROM canonical_games
            WHERE season=? AND season_type=? AND week=?
              AND retracted_at IS NULL
            ORDER BY kickoff_ts,game_id"""
        , tuple(next_identity)
    ).fetchall()
    canonical_game_count = int(history_connection.execute(
        "SELECT count(*) FROM canonical_games WHERE season=2026 AND retracted_at IS NULL"
    ).fetchone()[0])
    history_connection.close()
    if not rows:
        raise RuntimeError("NFL next canonical schedule cohort is empty")
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
    return games, {
        "season": int(next_identity[0]),
        "season_type": str(next_identity[1]),
        "week": int(next_identity[2]),
        "canonical_game_count": canonical_game_count,
    }


def physical_runtime_state(as_of: datetime | None = None) -> dict[str, Any]:
    current = (as_of or datetime.now(UTC)).astimezone(UTC)
    now_z = current.isoformat().replace("+00:00", "Z")
    connection = ro(HIST)
    try:
        tables = {
            str(row[0]) for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        completion_present = "point_in_time_capture_completions" in tables
        slots = int(connection.execute(
            "SELECT count(*) FROM point_in_time_capture_schedule WHERE parser_version=?",
            (PARSER_VERSION,),
        ).fetchone()[0])
        cohorts = int(connection.execute(
            "SELECT count(DISTINCT cohort_id) FROM point_in_time_capture_schedule "
            "WHERE parser_version=?", (PARSER_VERSION,),
        ).fetchone()[0])
        completed = int(connection.execute(
            "SELECT count(*) FROM point_in_time_capture_completions"
        ).fetchone()[0]) if completion_present else 0
        retry_pending = int(connection.execute(
            """SELECT count(*) FROM point_in_time_capture_schedule s
                WHERE s.parser_version=?
                  AND (CASE WHEN s.capture_label='T2'
                            THEN datetime(s.cohort_cutoff,'-10 minutes')
                            ELSE datetime(s.due_at) END) <= datetime(?)
                  AND datetime(s.cohort_cutoff)>datetime(?)
                  AND datetime(s.cohort_cutoff)>=datetime(s.created_at)
                  AND NOT EXISTS (SELECT 1 FROM point_in_time_capture_completions c
                                   WHERE c.capture_slot_id=s.capture_slot_id)""",
            (PARSER_VERSION, now_z, now_z),
        ).fetchone()[0]) if completion_present else 0
        critical_missed = int(connection.execute(
            """SELECT count(*) FROM point_in_time_capture_schedule s
                WHERE s.parser_version=? AND s.capture_label IN ('T3','T2')
                  AND datetime(s.cohort_cutoff)<datetime(?)
                  AND datetime(s.cohort_cutoff)>=datetime(s.created_at)
                  AND NOT EXISTS (SELECT 1 FROM point_in_time_capture_completions c
                                   WHERE c.capture_slot_id=s.capture_slot_id)""",
            (PARSER_VERSION, now_z),
        ).fetchone()[0]) if completion_present else 0
    finally:
        connection.close()
    return {
        "active_capture_slot_count": slots,
        "active_cohort_count": cohorts,
        "completed_capture_slot_count": completed,
        "retryable_incomplete_capture_count": retry_pending,
        "critical_missed_capture_count": critical_missed,
        "completion_ledger_present": completion_present,
        "sealed_t3_cohort_count": sum(1 for path in COHORT_ROOT.rglob("T3.json")) if COHORT_ROOT.is_dir() else 0,
        "sealed_t2_cohort_count": sum(1 for path in COHORT_ROOT.rglob("T2.json")) if COHORT_ROOT.is_dir() else 0,
    }


def release_state() -> tuple[str, dict[str, Any] | None]:
    if not RELEASE_CURRENT.is_file():
        return "SCIENCE_BLOCKED_NO_QUALIFIED_CHAMPION", None
    pointer = json.loads(RELEASE_CURRENT.read_text(encoding="utf-8"))
    if pointer.get("schema") != "apex.nfl.production_release_pointer.v2":
        return "FAIL_CLOSED_INVALID_RELEASE_POINTER", None
    release_id = str(pointer.get("release_id") or "")
    manifest = (IMMUTABLE_RELEASE_ROOT / release_id / "release.json").resolve()
    try:
        manifest.relative_to(IMMUTABLE_RELEASE_ROOT.resolve())
    except ValueError:
        return "FAIL_CLOSED_RELEASE_PATH_ESCAPE", None
    if not manifest.is_file() or sha256(manifest) != pointer.get("release_manifest_sha256"):
        return "FAIL_CLOSED_RELEASE_HASH_MISMATCH", None
    release = json.loads(manifest.read_text(encoding="utf-8"))
    if (
        release.get("schema") != "apex.nfl.production_release.v2"
        or release.get("release_id") != release_id
        or release.get("status") != "SCIENTIFICALLY_QUALIFIED_FOR_PRODUCTION"
    ):
        return "FAIL_CLOSED_RELEASE_NOT_QUALIFIED", None
    engines = release.get("engines")
    if not isinstance(engines, list) or {
        row.get("market") for row in engines if isinstance(row, dict)
    } != {"ATS", "TOTALS", "PROPS"}:
        return "FAIL_CLOSED_RELEASE_ENGINE_SET", None
    for engine in engines:
        for path_key, hash_key in (
            ("serving_program", "serving_program_sha256"),
            ("model_artifact", "model_artifact_sha256"),
            ("feature_schema", "feature_schema_sha256"),
        ):
            path = Path(str(engine.get(path_key) or "")).resolve()
            try:
                path.relative_to(manifest.parent.resolve())
            except ValueError:
                return "FAIL_CLOSED_RELEASE_ARTIFACT_PATH", None
            if not path.is_file() or sha256(path) != engine.get(hash_key):
                return "FAIL_CLOSED_RELEASE_ARTIFACT_HASH", None
    return "SCIENTIFICALLY_QUALIFIED_FOR_PRODUCTION", release


def sealed_history() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    issuances: list[dict[str, Any]] = []
    by_id: dict[str, tuple[Path, dict[str, Any]]] = {}
    for path in sorted(ISSUANCE_ROOT.glob("*.json")) if ISSUANCE_ROOT.is_dir() else []:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            payload.get("schema") != "apex.nfl.sealed_issuance.v2"
            or path.name != f"{payload.get('issuance_id')}.json"
            or not isinstance(payload.get("positions"), list)
        ):
            raise RuntimeError(f"invalid NFL sealed issuance: {path}")
        for path_key, hash_key in (
            ("t3_receipt_path", "t3_receipt_sha256"),
            ("t2_receipt_path", "t2_receipt_sha256"),
            ("release_manifest_path", "release_manifest_sha256"),
            ("settlement_ruleset_path", "settlement_ruleset_sha256"),
        ):
            bound = Path(str(payload.get(path_key) or ""))
            if not bound.is_file() or sha256(bound) != payload.get(hash_key):
                raise RuntimeError(f"NFL issuance bound-file mismatch: {path_key}")
        by_id[str(payload["issuance_id"])] = (path, payload)
        issuances.append(payload)
    grades: list[dict[str, Any]] = []
    graded_ids: set[str] = set()
    for path in sorted(GRADE_ROOT.glob("*.json")) if GRADE_ROOT.is_dir() else []:
        payload = json.loads(path.read_text(encoding="utf-8"))
        issuance_id = str(payload.get("issuance_id") or "")
        bound = by_id.get(issuance_id)
        if (
            payload.get("schema") != "apex.nfl.immutable_grade_receipt.v2"
            or path.name != f"{payload.get('grade_id')}.json"
            or bound is None
            or payload.get("issuance_sha256") != sha256(bound[0])
            or issuance_id in graded_ids
            or not isinstance(payload.get("settlements"), list)
        ):
            raise RuntimeError(f"invalid/duplicate NFL immutable grade: {path}")
        graded_ids.add(issuance_id)
        grades.append(payload)
    return issuances, grades


def main() -> int:
    hydration, runtime, receipt = load_verified_state()
    games, schedule_state = schedule()
    physical = physical_runtime_state()
    generated_at = str(hydration["completed_at"])
    scientific_state, release = release_state()
    issuances, grades = sealed_history()
    team_connection = ro(TEAM)
    try:
        all_team_names = {
            str(row["team_id"]): str(row["current_name"])
            for row in team_connection.execute("SELECT team_id,current_name FROM teams ORDER BY team_id")
        }
    finally:
        team_connection.close()
    all_player_ids = sorted({
        str(position.get("player_id"))
        for issuance in issuances
        for position in issuance.get("positions", [])
        if position.get("player_id")
    })
    all_player_names: dict[str, str] = {}
    if all_player_ids:
        player_connection = ro(PLAYER)
        try:
            placeholders = ",".join("?" for _ in all_player_ids)
            all_player_names = {
                str(row["player_id"]): str(row["display_name"])
                for row in player_connection.execute(
                    f"SELECT player_id,display_name FROM canonical_players WHERE player_id IN ({placeholders})",
                    all_player_ids,
                )
            }
        finally:
            player_connection.close()

    def public_position(source: dict[str, Any]) -> dict[str, Any]:
        position = dict(source)
        market = str(position.get("market") or "")
        selection = str(position.get("selection") or "")
        line = float(position.get("line") or 0.0)
        if market == "ATS":
            side = "FAVORITE" if line < 0 else "UNDERDOG" if line > 0 else "PICK'EM"
            team_name = all_team_names.get(selection, selection)
            position["display_market_label"] = "FULL-GAME ATS"
            position["display_selection"] = f"{side}: {team_name} {line:+g}"
        elif market == "TOTALS":
            position["display_market_label"] = "FULL-GAME TOTALS"
            position["display_selection"] = f"{selection.upper()} {line:g}"
        elif market == "PROPS":
            player_id = str(position.get("player_id") or "")
            player_name = all_player_names.get(player_id, player_id or "PLAYER")
            prop_family = str(position.get("prop_family") or "PLAYER PROP").replace("_", " ")
            position["player_display_name"] = player_name
            position["display_market_label"] = prop_family
            position["display_selection"] = f"{player_name} · {selection.upper()} {line:g}"
        position["sportsbook"] = "FanDuel"
        return position

    public_issuances = [
        {**issuance, "positions": [public_position(position) for position in issuance.get("positions", [])]}
        for issuance in issuances
    ]
    release_qualified = scientific_state == "SCIENTIFICALLY_QUALIFIED_FOR_PRODUCTION"
    science = {lane: "SEE_QUALIFIED_RELEASE" if release_qualified else "NO_QUALIFIED_CHAMPION"
               for lane in ("ATS", "PROPS", "TOTALS")}
    infrastructure_ready = bool(
        physical["completion_ledger_present"]
        and physical["active_capture_slot_count"] == 708
        and physical["active_cohort_count"] == 118
        and physical["critical_missed_capture_count"] == 0
        and runtime["sealed_file_hash_mismatch_count"] == 0
    )
    runtime_exercised = bool(
        physical["sealed_t3_cohort_count"] and physical["sealed_t2_cohort_count"]
    )
    technical_ready = infrastructure_ready and runtime_exercised
    technical_status = (
        "TECHNICAL_RUNTIME_NOT_READY" if not infrastructure_ready
        else "ARMED_NOT_YET_EXERCISED" if not runtime_exercised
        else "TECHNICAL_RUNTIME_READY_INPUT_CAPTURE_RETRY_PENDING"
        if physical["retryable_incomplete_capture_count"]
        else "TECHNICAL_RUNTIME_READY"
    )
    display_game_ids = {str(game["game_id"]) for game in games}
    today_positions: list[dict[str, Any]] = []
    for issuance in public_issuances:
        for position in issuance["positions"]:
            if str(position.get("game_id")) in display_game_ids:
                value = dict(position)
                value["issuance_id"] = issuance["issuance_id"]
                value["issued_at_utc"] = issuance["issued_at"]
                value["release_id"] = issuance["release_id"]
                today_positions.append(value)
    by_game: dict[str, list[dict[str, Any]]] = {}
    for position in today_positions:
        by_game.setdefault(str(position["game_id"]), []).append(position)
    for game in games:
        game["positions"] = sorted(
            by_game.get(str(game["game_id"]), []), key=lambda row: str(row["position_id"])
        )
    settlements = [row for grade in grades for row in grade["settlements"]]
    counts = {
        state: sum(1 for row in settlements if row.get("result") == state)
        for state in ("WIN", "LOSS", "PUSH", "VOID")
    }
    scored = [row for row in settlements if row.get("log_loss") is not None]
    proper = None if not scored else {
        "mean_log_loss": sum(float(row["log_loss"]) for row in scored) / len(scored),
        "mean_brier": sum(float(row["brier"]) for row in scored) / len(scored),
        "scored_position_count": len(scored),
    }
    issued_position_count = sum(len(row["positions"]) for row in issuances)
    shared = {
        "generated_at_utc": generated_at,
        "technical_status": technical_status,
        "scientific_release_state": scientific_state,
        "science": science,
        "public_issuance": bool(today_positions),
        "position_count": len(today_positions),
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
            "code_commit": str(runtime["code_commit"]),
            "manifest_sha256": str(runtime["manifest_sha256"]),
            "sealed_file_hash_mismatch_count": int(
                runtime["sealed_file_hash_mismatch_count"]
            ),
        },
        "capture_health": physical,
    }
    today = {
        "schema_version": "APEX_NFL_TODAY_V1",
        "sport": "NFL",
        **shared,
        "slate": {
            "season": schedule_state["season"],
            "season_type": schedule_state["season_type"],
            "week": schedule_state["week"],
            "game_count": len(games),
            "games": games,
        },
        "positions": sorted(today_positions, key=lambda row: str(row["position_id"])),
    }
    system_state = {
        "schema_version": "APEX_NFL_PUBLIC_STATE_V1",
        "sport": "NFL",
        **shared,
        "schedule": {
            "canonical_game_count": schedule_state["canonical_game_count"],
            "display_week_game_count": len(games),
            "active_capture_slot_count": physical["active_capture_slot_count"],
            "active_cohort_count": physical["active_cohort_count"],
            "completed_capture_slot_count": physical["completed_capture_slot_count"],
            "retryable_incomplete_capture_count": physical["retryable_incomplete_capture_count"],
            "critical_missed_capture_count": physical["critical_missed_capture_count"],
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
        "issued_position_count": issued_position_count,
        "graded_position_count": len(settlements),
        "ungraded_position_count": max(0, issued_position_count - len(settlements)),
        "record": {
            "wins": counts["WIN"], "losses": counts["LOSS"],
            "pushes": counts["PUSH"], "voids": counts["VOID"],
        },
        "proper_scores": proper,
        "message": (
            "No NFL positions have been issued; no performance is claimed."
            if issued_position_count == 0 else "Exact sealed NFL issuance and grade state."
        ),
    }
    archive = {
        "schema_version": "APEX_NFL_RESULTS_ARCHIVE_V1",
        "sport": "NFL",
        "generated_at_utc": generated_at,
        "issuances": public_issuances,
        "grades": grades,
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
