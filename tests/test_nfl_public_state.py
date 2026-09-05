from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def load(name: str) -> dict[str, object]:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


class NFLPublicStateTest(unittest.TestCase):
    def test_science_blocked_state_has_no_position(self) -> None:
        today = load("nfl_today.json")
        self.assertEqual(today["schema_version"], "APEX_NFL_TODAY_V1")
        # The infrastructure has been exercised, but the first event-relative
        # T-3/T-2 cohort is not due yet. The public contract must not collapse
        # those two facts into a premature runtime-ready claim.
        self.assertEqual(today["technical_status"], "ARMED_NOT_YET_EXERCISED")
        self.assertTrue(today["capture_health"]["completion_ledger_present"])
        self.assertEqual(today["capture_health"]["critical_missed_capture_count"], 0)
        self.assertEqual(today["capture_health"]["sealed_t3_cohort_count"], 0)
        self.assertEqual(today["capture_health"]["sealed_t2_cohort_count"], 0)
        self.assertEqual(
            today["scientific_release_state"],
            "SCIENCE_BLOCKED_NO_QUALIFIED_CHAMPION",
        )
        self.assertIs(today["public_issuance"], False)
        self.assertEqual(today["position_count"], 0)
        self.assertEqual(today["positions"], [])
        self.assertEqual(
            today["science"],
            {
                "ATS": "NO_QUALIFIED_CHAMPION",
                "PROPS": "NO_QUALIFIED_CHAMPION",
                "TOTALS": "NO_QUALIFIED_CHAMPION",
            },
        )

    def test_week_one_schedule_is_canonical_and_position_free(self) -> None:
        slate = load("nfl_today.json")["slate"]
        games = slate["games"]
        self.assertEqual(slate["season"], 2026)
        self.assertEqual(slate["season_type"], "REG")
        self.assertEqual(slate["week"], 1)
        self.assertEqual(slate["game_count"], 16)
        self.assertEqual(len(games), 16)
        self.assertEqual(len({game["game_id"] for game in games}), 16)
        self.assertTrue(all(game["positions"] == [] for game in games))
        self.assertEqual(
            games,
            sorted(games, key=lambda game: (game["kickoff_utc"], game["game_id"])),
        )

    def test_hydration_and_runtime_identity_are_consistent(self) -> None:
        today = load("nfl_today.json")
        state = load("nfl_system_state.json")
        self.assertEqual(state["schema_version"], "APEX_NFL_PUBLIC_STATE_V1")
        self.assertEqual(today["hydration"], state["hydration"])
        self.assertEqual(today["runtime"], state["runtime"])
        self.assertEqual(today["hydration"]["status"], "PASS")
        self.assertEqual(
            today["hydration"]["retrieval_mode"], "LIVE_NETWORK_RETRIEVAL"
        )
        self.assertEqual(today["hydration"]["source_to_target_parity"], "PASS")
        self.assertEqual(today["hydration"]["cross_authority_completion"], "PASS")
        self.assertEqual(today["runtime"]["sealed_file_hash_mismatch_count"], 0)

    def test_empty_result_ledger_reconciles(self) -> None:
        summary = load("nfl_results_summary.json")
        archive = load("nfl_results_archive.json")
        self.assertEqual(summary["schema_version"], "APEX_NFL_RESULTS_SUMMARY_V1")
        self.assertEqual(archive["schema_version"], "APEX_NFL_RESULTS_ARCHIVE_V1")
        self.assertEqual(summary["issued_position_count"], 0)
        self.assertEqual(summary["graded_position_count"], 0)
        self.assertEqual(summary["ungraded_position_count"], 0)
        self.assertEqual(archive["issuances"], [])
        self.assertEqual(archive["grades"], [])

    def test_nfl_routes_are_complete(self) -> None:
        for path in (
            ROOT / "nfl" / "index.html",
            ROOT / "nfl" / "results" / "index.html",
            ROOT / "nfl" / "about" / "index.html",
        ):
            text = path.read_text(encoding="utf-8")
            self.assertEqual(text.count('<nav class="sport-nav"'), 1)
            self.assertIn('href="/nfl', text)
            self.assertNotIn("sport-unavailable", text)

    def test_nfl_pages_are_future_issuance_capable(self) -> None:
        picks = (ROOT / "nfl" / "index.html").read_text(encoding="utf-8")
        results = (ROOT / "nfl" / "results" / "index.html").read_text(encoding="utf-8")
        self.assertIn("if(positions===0)", picks)
        self.assertIn("SEALED T-2", picks)
        self.assertIn("issuedPanel", picks)
        self.assertNotIn("d.position_count!==0", picks)
        self.assertIn("if(issued===0)", results)
        self.assertIn("Exact Sealed Position Ledger", results)
        self.assertNotIn("d.issued_position_count!==0", results)


if __name__ == "__main__":
    unittest.main()
