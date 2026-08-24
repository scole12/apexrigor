#!/usr/bin/env python3
"""Build the NCAA-namespaced public payload from the single NCAA machine."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


SITE = Path(__file__).resolve().parents[1]
DATA = SITE / "data"
NCAA_STATE = Path("/var/opt/apex_ncaaf/production")
CLOSURE_CENSUS = Path(
    "/opt/apex_ncaaf/testing_authority/"
    "final_system_closure_20260824_20260824T152750Z/"
    "08_replays/2026_WEEK0_SLATE_CENSUS.json"
)


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))


def source_payload() -> tuple[dict, str, str]:
    production = sorted((NCAA_STATE / "public").glob("*/website.json"))
    if production:
        path = production[-1]
        return json.loads(path.read_text(encoding="utf-8")), str(path), hashlib.sha256(path.read_bytes()).hexdigest()
    census = json.loads(CLOSURE_CENSUS.read_text(encoding="utf-8"))
    payload = {
        "schema_version": "apex.ncaaf.public_slate.2026-08-24.v2",
        "slate_date_et": census["slate_date_et"],
        "issuance_id": None,
        "games": [
            {
                "game_id": row["game_id"],
                "matchup": row["matchup"],
                "kickoff_et": row["kickoff_et"],
                "market_status": row["market_status_as_of_census"],
                "positions": [],
                "grade": None,
            }
            for row in census["games"]
        ],
    }
    return payload, str(CLOSURE_CENSUS), hashlib.sha256(CLOSURE_CENSUS.read_bytes()).hexdigest()


def main() -> None:
    payload, source_path, source_sha = source_payload()
    envelope = {
        "schema_version": "apex.public.ncaaf_today.2026-08-24.v1",
        "sport": "NCAA_DIVISION_I_FOOTBALL",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source_path": source_path,
        "source_sha256": source_sha,
        "public_contract_fields": ["matchup", "market_type", "selection", "line", "price", "rating", "rationale"],
        "slate": payload,
    }
    grades = sorted((NCAA_STATE / "grades").glob("*/*.json"))
    archive = [json.loads(path.read_text(encoding="utf-8")) for path in grades]
    summary = {
        "schema_version": "apex.public.ncaaf_results_summary.2026-08-24.v1",
        "graded_object_count": len(archive),
        "natural_2026_grade_count": sum(1 for row in archive if str(row.get("schema_version", "")).startswith("apex.ncaaf")),
        "status": "AWAITING_FIRST_NATURAL_GRADE" if not archive else "ACTIVE",
    }
    write(DATA / "ncaaf_today.json", envelope)
    write(DATA / "ncaaf_results_summary.json", summary)
    write(DATA / "ncaaf_results_archive.json", archive)
    print(json.dumps({"game_count": len(payload["games"]), "grade_count": len(archive), "status": "PASS"}, sort_keys=True))


if __name__ == "__main__":
    main()
