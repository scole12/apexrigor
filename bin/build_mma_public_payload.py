#!/usr/bin/env python3
"""Build fail-closed public MMA payloads from one sanitized state snapshot."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any
import uuid
from _mma_forecast_contract import (
    SEALED_RELEASE_STATE,
    SHA,
    forecast_status,
    positions_sha256,
    validated_card,
    validated_positions,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE = ROOT / "data/mma_system_state.json"


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(json.dumps(value, indent=2, sort_keys=True, default=str).encode() + b"\n")
    temporary.replace(path)


def with_payload_hash(value: dict[str, Any]) -> dict[str, Any]:
    value.pop("payload_sha256", None)
    value["payload_sha256"] = hashlib.sha256(canonical(value)).hexdigest()
    return value


def _nonnegative_count(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RuntimeError(f"{field} must be a nonnegative integer")
    return value


def science_gate_projection(state: dict[str, Any], *, issued: bool) -> dict[str, Any]:
    raw = state.get("science_gate")
    if raw is None and not issued:
        # Migration default for queued states created before the explicit gate.
        # It can only close production; it can never authorize an issuance.
        raw = {
            "keep": "NONE",
            "edge_cert": "NO",
            "ci_fully_below_0": False,
            "production_issuance_authorized": False,
            "policy": "STATUS_ONLY",
        }
    if not isinstance(raw, dict):
        raise RuntimeError("MMA science gate must be an object")
    gate = {
        "keep": str(raw.get("keep") or "NONE"),
        "edge_cert": str(raw.get("edge_cert") or "NO"),
        "ci_fully_below_0": raw.get("ci_fully_below_0") is True,
        "production_issuance_authorized": raw.get("production_issuance_authorized") is True,
        "policy": str(raw.get("policy") or "STATUS_ONLY"),
    }
    authorized_release_id = raw.get("authorized_release_id")
    authorized_manifest_sha256 = raw.get("authorized_release_manifest_sha256")
    authorized_model_sha256 = raw.get("authorized_model_artifact_sha256")
    try:
        uuid.UUID(str(authorized_release_id))
        release_id_valid = True
    except (ValueError, TypeError, AttributeError):
        release_id_valid = False
    gate["eligible"] = bool(
        gate["keep"] != "NONE"
        and gate["edge_cert"] == "YES"
        and gate["ci_fully_below_0"]
        and gate["production_issuance_authorized"]
        and release_id_valid
        and isinstance(authorized_manifest_sha256, str)
        and SHA.fullmatch(authorized_manifest_sha256)
        and isinstance(authorized_model_sha256, str)
        and SHA.fullmatch(authorized_model_sha256)
    )
    if issued and not gate["eligible"]:
        raise RuntimeError("MMA issuance is not backed by an eligible production science gate")
    if issued:
        positions = state.get("positions") or []
        position_release_ids = {
            str((position.get("trace") or {}).get("release_id") or "")
            for position in positions
        }
        if position_release_ids != {str(authorized_release_id)}:
            raise RuntimeError("MMA issuance release identity does not match the authorized science gate")
        if (
            state.get("active_model") != gate["keep"]
            or state.get("active_model_sha256") != authorized_model_sha256
        ):
            raise RuntimeError("MMA issuance model identity does not match the authorized science gate")
        gate["release_binding"] = "EXACT_AUTHORIZED_RELEASE"
    else:
        gate["release_binding"] = (
            "AUTHORIZED_RELEASE_AWAITING_EVENT_ISSUANCE" if gate["eligible"] else "NONE"
        )
    return gate


def public_state_projection(state: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if state.get("schema_version") not in {"APEX_MMA_PUBLIC_STATE_V1", "APEX_MMA_PUBLIC_STATE_V2"}:
        raise RuntimeError("unsupported MMA public state")

    card = validated_card(state)
    positions = validated_positions(state)
    issued = bool(positions)
    science_gate = science_gate_projection(state, issued=issued)
    public_state = deepcopy(state)
    public_state["card"] = card
    public_state["fight_count"] = len(card)
    public_state["positions"] = positions
    public_state["picks_published"] = issued
    public_state["positions_sha256"] = positions_sha256(positions) if issued else None
    public_state["science_gate"] = science_gate

    # The queued object is validated before this public projection is built.  Do
    # not advertise an internal candidate as an active public model when there
    # is no exact sealed event issuance.
    if not issued or state.get("release_state") != SEALED_RELEASE_STATE:
        public_state["active_model"] = None
        public_state["active_model_sha256"] = None
        public_state["science_blocker"] = (
            "EDGE_CERTIFIED_RELEASE_AWAITING_EVENT_ISSUANCE"
            if science_gate["eligible"]
            else "FAIL_CLOSED_KEEP_NONE_EDGE_CERT_NO"
        )

    return with_payload_hash(public_state), positions


def build_public_payloads(state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    public_state, positions = public_state_projection(state)
    issued = bool(positions)
    forecast = forecast_status(public_state, positions)
    production = public_state["authorities"]["production"]
    total_grades = _nonnegative_count(production["grades"], "authorities.production.grades")
    commercial_settlement_count = _nonnegative_count(
        production.get("commercial_grades", total_grades),
        "authorities.production.commercial_grades",
    )
    scientific_grade_count = _nonnegative_count(
        production.get("scientific_grades", 0),
        "authorities.production.scientific_grades",
    )
    if "commercial_grades" in production and total_grades != commercial_settlement_count + scientific_grade_count:
        raise RuntimeError("MMA production grade counts do not reconcile")

    today = {
        "schema_version": "APEX_MMA_TODAY_V1",
        "generated_at_utc": public_state["generated_at_utc"],
        "release_state": public_state["release_state"],
        "picks_published": issued,
        "active_model": public_state.get("active_model") if issued else None,
        "active_model_sha256": public_state.get("active_model_sha256") if issued else None,
        "event": public_state["event"],
        "fight_count": public_state["fight_count"],
        "card": public_state["card"],
        "positions": positions,
        "positions_sha256": positions_sha256(positions),
        "issuance_id": public_state.get("issuance_id") if issued else None,
        "issuance_status": public_state.get("issuance_status") if issued else None,
        "forecast": forecast,
        "t3": public_state["t3"],
        "t2": public_state["t2"],
        "authenticity": {
            "no_fabricated_positions": True,
            "no_authentic_fanduel_total_means_no_total_position": True,
            "card_reconciliation_status": public_state["card_reconciliation_status"],
        },
        "science_blocker": public_state["science_blocker"],
        "science_gate": public_state["science_gate"],
    }
    with_payload_hash(today)

    summary = {
        "schema_version": "APEX_MMA_RESULTS_SUMMARY_V1",
        "generated_at_utc": public_state["generated_at_utc"],
        "release_state": public_state["release_state"],
        "issued_event_count": production["issuances"],
        "graded_scientific_object_count": scientific_grade_count,
        "commercial_settlement_count": commercial_settlement_count,
        "latest_event_results": public_state.get("latest_results", []),
        "grader": public_state["grader"],
        "status": "NO_ISSUANCE_NO_RESULTS" if not production["issuances"] else "RESULTS_AVAILABLE",
        "current_event_forecast": forecast,
    }
    with_payload_hash(summary)
    archive = {
        "schema_version": "APEX_MMA_RESULTS_ARCHIVE_V1",
        "generated_at_utc": public_state["generated_at_utc"],
        "events": public_state.get("results_archive", []),
        "revision_policy": "APPEND_ONLY_RESULT_AND_GRADE_REVISIONS",
    }
    with_payload_hash(archive)
    ops = {
        "schema_version": "APEX_MMA_OPS_SNAPSHOT_V1",
        "generated_at_utc": public_state["generated_at_utc"],
        "system_status": forecast["code"],
        "next_event": public_state["event"],
        "event_card": public_state["card"],
        "t3": public_state["t3"],
        "t2": public_state["t2"],
        "fighter_authority": public_state["authorities"]["fighter"],
        "market_outcomes_authority": {"status": "POPULATED_H2H_ONLY"},
        "testing_authority": public_state["authorities"]["testing"],
        "active_engine": public_state.get("active_model") if issued else None,
        "model_sha256": public_state.get("active_model_sha256") if issued else None,
        "t3_fight_count": (
            public_state["t3"].get("bout_count")
            if isinstance(public_state["t3"].get("bout_count"), int)
            and not isinstance(public_state["t3"].get("bout_count"), bool)
            else None
        ),
        "t2_issued_position_count": len(positions),
        "grader": public_state["grader"],
        "latest_event_results": public_state.get("latest_results", []),
        "production_isolation": "PASS",
        "science_blocker": public_state["science_blocker"],
        "science_gate": public_state["science_gate"],
    }
    with_payload_hash(ops)
    outputs = {
        "data/mma_today.json": today,
        "data/mma_results_summary.json": summary,
        "data/mma_results_archive.json": archive,
        "data/mma_ops_snapshot.json": ops,
    }
    return public_state, outputs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--snapshot-state", action="store_true")
    args = parser.parse_args()
    state = json.loads(args.state.read_text(encoding="utf-8"))
    public_state, outputs = build_public_payloads(state)
    if args.snapshot_state or args.state.resolve() == DEFAULT_STATE.resolve():
        write_json(DEFAULT_STATE, public_state)
    for relative, value in outputs.items():
        write_json(ROOT / relative, value)
    print(json.dumps({"status": "PASS", "outputs": sorted(outputs), "positions": len(outputs["data/mma_today.json"]["positions"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
