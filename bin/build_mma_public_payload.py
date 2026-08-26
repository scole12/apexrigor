#!/usr/bin/env python3
"""Build fail-closed public MMA payloads from one sanitized state snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE = ROOT / "data/mma_system_state.json"


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(json.dumps(value, indent=2, sort_keys=True, default=str).encode() + b"\n")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--snapshot-state", action="store_true")
    args = parser.parse_args()
    state = json.loads(args.state.read_text(encoding="utf-8"))
    if state.get("schema_version") not in {"APEX_MMA_PUBLIC_STATE_V1", "APEX_MMA_PUBLIC_STATE_V2"}:
        raise RuntimeError("unsupported MMA public state")
    if state.get("release_state") == "NO_RELEASE_SCIENTIFIC_GATE":
        if state.get("picks_published") or state.get("active_model"):
            raise RuntimeError("release-gated state contains a pick/model")
    elif not state.get("active_model"):
        raise RuntimeError("a releasable state must identify its active model")
    if args.snapshot_state:
        write_json(DEFAULT_STATE, state)

    today = {
        "schema_version": "APEX_MMA_TODAY_V1",
        "generated_at_utc": state["generated_at_utc"],
        "release_state": state["release_state"],
        "picks_published": bool(state["picks_published"]),
        "active_model": state.get("active_model"),
        "active_model_sha256": state.get("active_model_sha256"),
        "event": state["event"],
        "fight_count": state["fight_count"],
        "card": state["card"],
        "positions": [],
        "t3": state["t3"],
        "t2": state["t2"],
        "authenticity": {
            "no_fabricated_positions": True,
            "no_authentic_fanduel_total_means_no_total_position": True,
            "card_reconciliation_status": state["card_reconciliation_status"],
        },
        "science_blocker": state["science_blocker"],
    }
    today["payload_sha256"] = hashlib.sha256(canonical(today)).hexdigest()

    summary = {
        "schema_version": "APEX_MMA_RESULTS_SUMMARY_V1",
        "generated_at_utc": state["generated_at_utc"],
        "release_state": state["release_state"],
        "issued_event_count": state["authorities"]["production"]["issuances"],
        "graded_scientific_object_count": state["authorities"]["production"]["grades"],
        "commercial_settlement_count": 0,
        "latest_event_results": state.get("latest_results", []),
        "grader": state["grader"],
        "status": "NO_ISSUANCE_NO_RESULTS" if not state["authorities"]["production"]["issuances"] else "RESULTS_AVAILABLE",
    }
    summary["payload_sha256"] = hashlib.sha256(canonical(summary)).hexdigest()
    archive = {
        "schema_version": "APEX_MMA_RESULTS_ARCHIVE_V1",
        "generated_at_utc": state["generated_at_utc"],
        "events": [],
        "revision_policy": "APPEND_ONLY_RESULT_AND_GRADE_REVISIONS",
    }
    archive["payload_sha256"] = hashlib.sha256(canonical(archive)).hexdigest()
    ops = {
        "schema_version": "APEX_MMA_OPS_SNAPSHOT_V1",
        "generated_at_utc": state["generated_at_utc"],
        "system_status": "TECHNICALLY_READY_SCIENCE_BLOCKED",
        "next_event": state["event"],
        "event_card": state["card"],
        "t3": state["t3"],
        "t2": state["t2"],
        "fighter_authority": state["authorities"]["fighter"],
        "market_outcomes_authority": {"status": "POPULATED_H2H_ONLY"},
        "testing_authority": state["authorities"]["testing"],
        "active_engine": "NO_RELEASE_SCIENTIFIC_GATE",
        "model_sha256": None,
        "t3_fight_count": 0,
        "t2_issued_position_count": 0,
        "grader": state["grader"],
        "latest_event_results": state.get("latest_results", []),
        "production_isolation": "PASS",
        "science_blocker": state["science_blocker"],
    }
    ops["payload_sha256"] = hashlib.sha256(canonical(ops)).hexdigest()
    outputs = {
        "data/mma_today.json": today,
        "data/mma_results_summary.json": summary,
        "data/mma_results_archive.json": archive,
        "data/mma_ops_snapshot.json": ops,
    }
    for relative, value in outputs.items():
        write_json(ROOT / relative, value)
    print(json.dumps({"status": "PASS", "outputs": sorted(outputs), "positions": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
