"""Focused regressions for the fail-closed MMA public projection."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path
import uuid


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))

from _mma_forecast_contract import positions_sha256  # noqa: E402
from build_mma_public_payload import build_public_payloads  # noqa: E402


SYNTHETIC_RELEASE_ID = str(uuid.UUID("11111111-1111-4111-8111-111111111111"))


def state_fixture() -> dict:
    return {
        "schema_version": "APEX_MMA_PUBLIC_STATE_V2",
        "generated_at_utc": "2026-09-11T02:30:24Z",
        "release_state": "SEALED_RELEASE_NO_EVENT_ISSUANCE",
        "picks_published": False,
        "active_model": "SYNTHETIC_INTERNAL_CANDIDATE",
        "active_model_sha256": "a" * 64,
        "issuance_id": None,
        "issuance_status": None,
        "fight_count": 2,
        "card": [
            {
                "bout_id": "synthetic-bout-1",
                "fighter_a": "SYNTHETIC Fighter A",
                "fighter_b": "SYNTHETIC Fighter B",
                "official_display_order": 1,
            },
            {
                "bout_id": "synthetic-bout-2",
                "fighter_a": "SYNTHETIC Fighter C",
                "fighter_b": "SYNTHETIC Fighter D",
                "official_display_order": 2,
            },
        ],
        "positions": [],
        "positions_sha256": None,
        "event": {"event_date": "2026-09-12", "display_name": "SYNTHETIC TEST EVENT"},
        "t3": {"status": "SCHEDULED", "scheduled_utc": "2026-09-12T15:00:00Z"},
        "t2": {"status": "AWAITING_T2", "scheduled_utc": "2026-09-12T16:00:00Z"},
        "grader": {"status": "SCHEDULED", "schedule": "07:00 America/New_York"},
        "authorities": {
            "fighter": {"status": "SYNTHETIC"},
            "testing": {"status": "RESEARCH_COURT_SCORED_NO_RELEASE"},
            "production": {"issuances": 1, "grades": 14},
        },
        "card_reconciliation_status": "PASS",
        "science_blocker": "NO_CERTIFIED_EDGE",
        "latest_results": [],
        "results_archive": [],
    }


def issued_position() -> dict:
    return {
        "bout_id": "synthetic-bout-1",
        "matchup": "SYNTHETIC Fighter A vs SYNTHETIC Fighter B",
        "fighter_a": "SYNTHETIC Fighter A",
        "fighter_b": "SYNTHETIC Fighter B",
        "market": "WINNER",
        "selection": "SYNTHETIC Fighter A",
        "line": None,
        "price": -110,
        "probability": 0.57,
        "tier": "MODERATE",
        "sportsbook": "FanDuel",
        "rationale": "SYNTHETIC TEST ONLY. This is not a real forecast.",
        "trace": {
            "issuance_id": "synthetic-issuance",
            "model_sha256": "a" * 64,
            "release_id": SYNTHETIC_RELEASE_ID,
        },
    }


class MmaPublicReleaseGateTests(unittest.TestCase):
    def test_unissued_projection_redacts_model_without_mutating_raw_source(self):
        raw = state_fixture()
        before = copy.deepcopy(raw)
        public_state, outputs = build_public_payloads(raw)
        today = outputs["data/mma_today.json"]
        ops = outputs["data/mma_ops_snapshot.json"]

        self.assertEqual(raw, before)
        self.assertIsNone(public_state["active_model"])
        self.assertIsNone(public_state["active_model_sha256"])
        self.assertEqual(public_state["positions"], [])
        self.assertIsNone(today["active_model"])
        self.assertIsNone(today["active_model_sha256"])
        self.assertEqual(today["positions"], [])
        self.assertIsNone(ops["active_engine"])
        self.assertIsNone(ops["model_sha256"])

    def test_only_exact_sealed_release_can_carry_positions(self):
        raw = state_fixture()
        raw["picks_published"] = True
        raw["issuance_id"] = "synthetic-issuance"
        raw["issuance_status"] = "SEALED"
        raw["positions"] = [issued_position()]
        raw["positions_sha256"] = positions_sha256(raw["positions"])
        with self.assertRaisesRegex(ValueError, "sealed published issuance"):
            build_public_payloads(raw)

        raw["release_state"] = "SEALED_RELEASE_AVAILABLE"
        raw["science_gate"] = {
            "keep": "SYNTHETIC_TEST_ONLY",
            "edge_cert": "YES",
            "ci_fully_below_0": True,
            "production_issuance_authorized": True,
            "policy": "SYNTHETIC_TEST_ONLY",
            "authorized_release_id": SYNTHETIC_RELEASE_ID,
            "authorized_release_manifest_sha256": "b" * 64,
            "authorized_model_artifact_sha256": "a" * 64,
        }
        raw["active_model"] = "SYNTHETIC_TEST_ONLY"
        public_state, outputs = build_public_payloads(raw)
        self.assertEqual(public_state["positions"], raw["positions"])
        self.assertEqual(outputs["data/mma_today.json"]["active_model"], raw["active_model"])

    def test_false_publication_flag_redacts_even_an_exact_release_candidate(self):
        raw = state_fixture()
        raw["release_state"] = "SEALED_RELEASE_AVAILABLE"
        public_state, outputs = build_public_payloads(raw)
        self.assertIsNone(public_state["active_model"])
        self.assertIsNone(outputs["data/mma_today.json"]["active_model"])

    def test_results_counts_classify_production_grades_as_commercial(self):
        _, outputs = build_public_payloads(state_fixture())
        summary = outputs["data/mma_results_summary.json"]
        self.assertEqual(summary["commercial_settlement_count"], 14)
        self.assertEqual(summary["graded_scientific_object_count"], 0)

    def test_position_must_match_the_official_card_before_publication(self):
        raw = state_fixture()
        raw.update(
            picks_published=True,
            release_state="SEALED_RELEASE_AVAILABLE",
            issuance_id="synthetic-issuance",
            issuance_status="SEALED",
            science_gate={
                "keep": "SYNTHETIC_TEST_ONLY",
                "edge_cert": "YES",
                "ci_fully_below_0": True,
                "production_issuance_authorized": True,
                "policy": "SYNTHETIC_TEST_ONLY",
                "authorized_release_id": SYNTHETIC_RELEASE_ID,
                "authorized_release_manifest_sha256": "b" * 64,
                "authorized_model_artifact_sha256": "a" * 64,
            },
        )
        row = issued_position()
        row["fighter_a"] = "SYNTHETIC Missing Fighter"
        raw["positions"] = [row]
        raw["positions_sha256"] = positions_sha256(raw["positions"])
        with self.assertRaisesRegex(ValueError, "official-card fighter pair"):
            build_public_payloads(raw)

    def test_issued_projection_requires_exact_authorized_release_binding(self):
        raw = state_fixture()
        raw.update(
            picks_published=True,
            release_state="SEALED_RELEASE_AVAILABLE",
            issuance_id="synthetic-issuance",
            issuance_status="SEALED",
            science_gate={
                "keep": "SYNTHETIC_TEST_ONLY",
                "edge_cert": "YES",
                "ci_fully_below_0": True,
                "production_issuance_authorized": True,
                "policy": "SYNTHETIC_TEST_ONLY",
                "authorized_release_id": SYNTHETIC_RELEASE_ID,
                "authorized_release_manifest_sha256": "b" * 64,
                "authorized_model_artifact_sha256": "a" * 64,
            },
        )
        raw["active_model"] = "SYNTHETIC_TEST_ONLY"
        raw["positions"] = [issued_position()]
        raw["positions_sha256"] = positions_sha256(raw["positions"])
        public_state, _ = build_public_payloads(raw)
        self.assertEqual(public_state["science_gate"]["release_binding"], "EXACT_AUTHORIZED_RELEASE")

        raw["positions"][0]["trace"]["release_id"] = str(uuid.uuid4())
        raw["positions_sha256"] = positions_sha256(raw["positions"])
        with self.assertRaisesRegex(RuntimeError, "release identity"):
            build_public_payloads(raw)

    def test_current_generated_surface_uses_event_based_fail_closed_copy(self):
        about = (ROOT / "mma" / "about" / "index.html").read_text(encoding="utf-8")
        picks = (ROOT / "mma" / "index.html").read_text(encoding="utf-8")
        today = json.loads((ROOT / "data" / "mma_today.json").read_text(encoding="utf-8"))

        self.assertIn("TODAY'S CARD", picks)
        self.assertIn("Unsupported MMA public market", picks)
        self.assertNotIn("return rows.filter", picks)
        self.assertNotIn("Four boxes for each fight", about)
        self.assertNotIn("daily grader", about)
        self.assertNotIn('id="active-model"', about)
        self.assertIn("event-based", about)
        self.assertIn("7:00 AM Eastern the next morning", about)
        self.assertIn('id="science-state"', about)
        self.assertIn("P(WINNER, METHOD, TIME)", about)
        self.assertIn("forecast.code", picks)
        if not today["positions"]:
            self.assertIsNone(today["active_model"])
            self.assertIsNone(today["active_model_sha256"])


if __name__ == "__main__":
    unittest.main()
