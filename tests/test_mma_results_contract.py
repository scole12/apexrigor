"""MMA results identity, provenance, parity, and fused-Overall regressions."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
import build_mma_results_page as results_page  # noqa: E402


def position(*, bout: str = "bout-1", selection: str = "Alpha", line=None, tier: str = "STRONG"):
    return {
        "bout_id": bout,
        "market": "WINNER",
        "selection": selection,
        "line": line,
        "matchup": f"{selection} vs Beta",
        "tier": tier,
        "price": -110,
        "sportsbook": "FanDuel",
        "trace": {"issuance_id": "issue-1", "model_sha256": "a" * 64},
    }


def grade(
    *,
    bout: str = "bout-1",
    selection: str = "Alpha",
    line=None,
    result: str = "W",
    source: str = results_page.COMMERCIAL_SOURCE,
    market: str = "WINNER",
    grade_id: str = "grade-1",
    price: int = -110,
):
    return {
        "issuance_id": "issue-1",
        "bout_id": bout,
        "market": market,
        "selection": selection,
        "line": line,
        "result": result,
        "source": source,
        "commercial_grade_id": grade_id,
        "price": price,
    }


def seal_archive(value):
    value.pop("payload_sha256", None)
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    value["payload_sha256"] = hashlib.sha256(encoded).hexdigest()
    return value


def archive(positions=None, grades=None):
    issued_positions = positions if positions is not None else [position()]
    return seal_archive({
        "schema_version": "APEX_MMA_RESULTS_ARCHIVE_V1",
        "revision_policy": "APPEND_ONLY_RESULT_AND_GRADE_REVISIONS",
        "events": [
            {
                "official_issuance": True,
                "picks_published": True,
                "release_state": "SEALED_RELEASE_AVAILABLE",
                "issuance_status": "SEALED",
                "issuance_id": "issue-1",
                "active_model_sha256": "a" * 64,
                "event_date": "2026-09-05",
                "event_name": "UFC Test",
                "positions": issued_positions,
                "positions_sha256": results_page.positions_sha256(issued_positions),
                "latest_results": grades if grades is not None else [grade()],
            }
        ]
    })


def summary(*, wins: int = 1, losses: int = 0, pushes: int = 0):
    settled = wins + losses + pushes
    return {
        "overall_wins": 1935,
        "overall_losses": 1772,
        "overall_pushes": 26,
        "overall": {
            "wins": 1935,
            "losses": 1772,
            "pushes": 26,
            "positions_tracked": 3757,
            "win_rate_display": "52.2%",
        },
        "sports": {
            "mma": {
                "wins": wins,
                "losses": losses,
                "pushes": pushes,
                "positions_settled": settled,
                "settled_n": settled,
            }
        },
    }


class MmaResultsContractTests(unittest.TestCase):
    def test_exact_join_uses_issued_matchup_tier_order_and_h2h_alias(self):
        positions = [
            position(bout="bout-1", selection="Alpha", tier="ELITE"),
            position(bout="bout-2", selection="Gamma", tier="WEAK"),
        ]
        grades = [
            grade(bout="bout-2", selection="Gamma", result="L", grade_id="grade-2"),
            {
                **grade(market="H2H"),
                "matchup": "UNTRUSTED GRADE MATCHUP",
                "tier": "UNTRUSTED GRADE TIER",
            },
        ]
        ledger = results_page.build_results_ledger(
            archive(positions, grades), summary(wins=1, losses=1)
        )
        self.assertEqual([row["bout_id"] for row in ledger["rows"]], ["bout-1", "bout-2"])
        self.assertEqual(ledger["rows"][0]["matchup"], "Alpha vs Beta")
        self.assertEqual(ledger["rows"][0]["tier"], "ELITE")
        self.assertEqual(ledger["rows"][0]["market"], "WINNER")
        self.assertEqual(ledger["record"], {"W": 1, "L": 1, "P": 0, "settled": 2})

    def test_missing_or_foreign_market_and_source_fail_closed(self):
        cases = {
            "missing market": {**grade(), "market": None},
            "foreign market": {**grade(), "market": "LONGSHOT"},
            "missing source": {key: value for key, value in grade().items() if key != "source"},
            "foreign source": {**grade(), "source": "SCIENTIFIC_SCORE"},
        }
        for label, bad_grade in cases.items():
            with self.subTest(label=label):
                with self.assertRaisesRegex(results_page.ResultsContractError, "market|source"):
                    results_page.build_results_ledger(archive(grades=[bad_grade]), summary())

    def test_full_identity_must_match_exact_issued_selection_and_line(self):
        for label, bad_grade in (
            ("selection", grade(selection="Other Fighter")),
            ("line", grade(line=1.5)),
            ("issuance", {**grade(), "issuance_id": "other-issue"}),
            ("bout", grade(bout="other-bout")),
        ):
            with self.subTest(label=label):
                with self.assertRaisesRegex(results_page.ResultsContractError, "exactly match"):
                    results_page.build_results_ledger(archive(grades=[bad_grade]), summary())

    def test_equal_duplicate_is_deduped_and_conflict_fails_closed(self):
        duplicate = grade()
        value = archive(grades=[duplicate])
        value["events"][0]["results"] = [deepcopy(duplicate)]
        seal_archive(value)
        ledger = results_page.build_results_ledger(value, summary())
        self.assertEqual(len(ledger["rows"]), 1)

        value["events"][0]["results"][0]["result"] = "L"
        seal_archive(value)
        with self.assertRaisesRegex(results_page.ResultsContractError, "conflicting duplicate"):
            results_page.build_results_ledger(value, summary())

        repeated_position = position()
        ledger = results_page.build_results_ledger(
            archive(positions=[repeated_position, deepcopy(repeated_position)]), summary()
        )
        self.assertEqual(len(ledger["rows"]), 1)
        self.assertEqual(ledger["rows"][0]["order"], 1)

    def test_unofficial_research_and_unknown_outcome_fail_closed(self):
        research = archive()
        research["events"][0]["official_issuance"] = False
        seal_archive(research)
        with self.assertRaisesRegex(results_page.ResultsContractError, "official published"):
            results_page.build_results_ledger(research, summary())
        with self.assertRaisesRegex(results_page.ResultsContractError, "unknown commercial result"):
            results_page.build_results_ledger(
                archive(grades=[grade(result="IN_PROGRESS")]), summary()
            )

    def test_ungraded_positions_and_nonsettled_commercial_rows_do_not_enter_wlp(self):
        ungraded = archive()
        del ungraded["events"][0]["latest_results"]
        seal_archive(ungraded)
        ledger = results_page.build_results_ledger(
            ungraded, summary(wins=0, losses=0, pushes=0)
        )
        self.assertEqual(ledger["rows"], [])
        self.assertEqual(ledger["record"], {"W": 0, "L": 0, "P": 0, "settled": 0})

        grades = [
            grade(result="VOID"),
            grade(
                bout="bout-2",
                selection="Gamma",
                result="PENDING",
                grade_id="grade-2",
            ),
        ]
        ledger = results_page.build_results_ledger(
            archive(
                positions=[position(), position(bout="bout-2", selection="Gamma")],
                grades=grades,
            ),
            summary(wins=0, losses=0, pushes=0),
        )
        self.assertEqual([row["result"] for row in ledger["rows"]], ["VOID", "PENDING"])
        self.assertEqual(ledger["record"], {"W": 0, "L": 0, "P": 0, "settled": 0})

    def test_archive_record_must_equal_fused_mma_wlp_and_settled(self):
        with self.assertRaisesRegex(results_page.ResultsContractError, "parity failure"):
            results_page.build_results_ledger(archive(), summary(wins=0, losses=1))
        inconsistent = summary()
        inconsistent["sports"]["mma"]["positions_settled"] = 2
        with self.assertRaisesRegex(results_page.ResultsContractError, "internally inconsistent"):
            results_page.build_results_ledger(archive(), inconsistent)

    def test_method_and_time_grades_are_validated_but_never_enter_h2h(self):
        positions = [
            position(),
            {**position(bout="bout-2", selection="Alpha by decision"), "market": "METHOD"},
            {**position(bout="bout-3", selection="Round 3"), "market": "TIME"},
        ]
        grades = [
            grade(),
            grade(bout="bout-2", selection="Alpha by decision", market="METHOD", grade_id="grade-2"),
            grade(bout="bout-3", selection="Round 3", market="TIME", grade_id="grade-3"),
        ]
        ledger = results_page.build_results_ledger(archive(positions, grades), summary())
        self.assertEqual([row["market"] for row in ledger["rows"]], ["WINNER"])
        self.assertEqual(ledger["record"], {"W": 1, "L": 0, "P": 0, "settled": 1})

    def test_archive_release_hash_trace_and_price_must_reconcile(self):
        for label, mutate, pattern in (
            ("release", lambda value: value["events"][0].update(release_state="NO_RELEASE"), "official published"),
            ("position hash", lambda value: value["events"][0].update(positions_sha256="0" * 64), "position checksum"),
            ("trace", lambda value: value["events"][0]["positions"][0]["trace"].update(model_sha256="b" * 64), "model trace"),
            ("price", lambda value: value["events"][0]["latest_results"][0].update(price=-115), "price conflicts"),
        ):
            value = archive()
            mutate(value)
            if label == "trace":
                value["events"][0]["positions_sha256"] = results_page.positions_sha256(value["events"][0]["positions"])
            seal_archive(value)
            with self.subTest(label=label), self.assertRaisesRegex(results_page.ResultsContractError, pattern):
                results_page.build_results_ledger(value, summary())

        tampered = archive()
        tampered["payload_sha256"] = "0" * 64
        with self.assertRaisesRegex(results_page.ResultsContractError, "payload checksum mismatch"):
            results_page.build_results_ledger(tampered, summary())

    def test_fused_overall_is_validated_but_never_recomputed_from_mma(self):
        value = summary()
        before = deepcopy(value)
        ledger = results_page.build_results_ledger(archive(), value)
        self.assertEqual(value, before)
        script = results_page.render_javascript(ledger)
        self.assertIn('fetch("/data/apex_results_summary.json"', script)
        self.assertIn("overall.positions_tracked", script)
        self.assertNotIn('fetch("/data/mma_results_archive.json"', script)

        value["overall_wins"] = 0
        with self.assertRaisesRegex(results_page.ResultsContractError, "fused Overall mismatch"):
            results_page.build_results_ledger(archive(), value)

    def test_fused_mma_source_hashes_must_match_the_built_ledger(self):
        proof = {
            "data/mma_results_archive.json": "a" * 64,
            "data/mma_results_summary.json": "b" * 64,
        }
        value = summary()
        value["total_apex_fuse"] = {
            "sources": {
                "mma": [
                    {"path": path, "sha256": digest}
                    for path, digest in proof.items()
                ]
            }
        }
        ledger = results_page.build_results_ledger(
            archive(), value, source_proof=proof
        )
        self.assertEqual(ledger["source_proof"], proof)
        self.assertIn("MMA archive/fused-summary source parity failure", results_page.render_javascript(ledger))

        value["total_apex_fuse"]["sources"]["mma"][0]["sha256"] = "c" * 64
        with self.assertRaisesRegex(results_page.ResultsContractError, "source parity failure"):
            results_page.build_results_ledger(archive(), value, source_proof=proof)

    def test_repository_archive_matches_fused_counts_and_issued_display_fields(self):
        actual_archive = json.loads((ROOT / "data" / "mma_results_archive.json").read_text())
        actual_summary = json.loads((ROOT / "data" / "apex_results_summary.json").read_text())
        ledger = results_page.build_results_ledger(actual_archive, actual_summary)
        mma = actual_summary["sports"]["mma"]
        self.assertEqual(
            ledger["record"],
            {
                "W": mma["wins"],
                "L": mma["losses"],
                "P": mma["pushes"],
                "settled": mma["positions_settled"],
            },
        )
        issued = {}
        for event in actual_archive["events"]:
            for row in event["positions"]:
                key = (event["issuance_id"], row["bout_id"], row["selection"], row["line"])
                issued[key] = row
        for row in ledger["rows"]:
            key = (row["issuance_id"], row["bout_id"], row["selection"], row["line"])
            self.assertEqual(row["matchup"], issued[key]["matchup"])
            self.assertEqual(row["tier"], issued[key]["tier"])

    @unittest.skipUnless(shutil.which("node"), "Node is required for generated-render proof")
    def test_generated_render_uses_exact_live_fused_overall_and_fails_on_mma_drift(self):
        ledger = results_page.build_results_ledger(archive(), summary())
        render = results_page.render_javascript(ledger)
        node_harness = r'''
const fs=require("fs");
const root={innerHTML:""};
global.document={getElementById:()=>root};
const summary=JSON.parse(process.env.APEX_TEST_SUMMARY);
global.fetch=async()=>({ok:true,status:200,json:async()=>summary});
const errors=[];console.error=(error)=>errors.push(String(error));
eval(fs.readFileSync(0,"utf8"));
setImmediate(()=>{
  if(process.env.APEX_EXPECT_ERROR==="1"){
    if(!root.innerHTML.includes("temporarily unavailable")||!errors.some(x=>x.includes("parity failure")))process.exit(2);
  }else if(!root.innerHTML.includes(process.env.APEX_EXPECT_RECORD)||
           !root.innerHTML.includes(process.env.APEX_EXPECT_TRACKED+" POSITIONS TRACKED")||
           !root.innerHTML.includes(process.env.APEX_EXPECT_RATE)||
           !root.innerHTML.includes("MMA Winner")||!root.innerHTML.includes(">1-0<"))process.exit(3);
});
'''
        valid_environment = {
            **dict(__import__("os").environ),
            "APEX_TEST_SUMMARY": json.dumps(summary()),
            "APEX_EXPECT_RECORD": "1,935-1,772-26P",
            "APEX_EXPECT_TRACKED": "3,757",
            "APEX_EXPECT_RATE": "52.2%",
        }
        valid = subprocess.run(
            [shutil.which("node"), "-e", node_harness],
            input=render,
            text=True,
            env=valid_environment,
            capture_output=True,
            check=False,
        )
        self.assertEqual(valid.returncode, 0, valid.stderr)

        changed_overall = summary()
        changed_overall["overall"].update(
            wins=2000,
            losses=1800,
            pushes=30,
            positions_tracked=3900,
            win_rate_display="52.6%",
        )
        changed_overall.update(overall_wins=2000, overall_losses=1800, overall_pushes=30)
        updated = subprocess.run(
            [shutil.which("node"), "-e", node_harness],
            input=render,
            text=True,
            env={
                **valid_environment,
                "APEX_TEST_SUMMARY": json.dumps(changed_overall),
                "APEX_EXPECT_RECORD": "2,000-1,800-30P",
                "APEX_EXPECT_TRACKED": "3,900",
                "APEX_EXPECT_RATE": "52.6%",
            },
            capture_output=True,
            check=False,
        )
        self.assertEqual(updated.returncode, 0, updated.stderr)

        drifted = summary(wins=0, losses=1)
        failed = subprocess.run(
            [shutil.which("node"), "-e", node_harness],
            input=render,
            text=True,
            env={
                **dict(__import__("os").environ),
                "APEX_TEST_SUMMARY": json.dumps(drifted),
                "APEX_EXPECT_ERROR": "1",
            },
            capture_output=True,
            check=False,
        )
        self.assertEqual(failed.returncode, 0, failed.stderr)

    def test_builder_is_deterministic_in_an_isolated_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data").mkdir()
            archive_path = root / "data" / "mma_results_archive.json"
            archive_path.write_text(json.dumps(archive()))
            isolated_summary = summary()
            isolated_summary["total_apex_fuse"] = {
                "sources": {
                    "mma": [{
                        "path": "data/mma_results_archive.json",
                        "sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
                    }]
                }
            }
            (root / "data" / "apex_results_summary.json").write_text(json.dumps(isolated_summary))
            results_page.main(root)
            first = {
                path.name: path.read_bytes()
                for path in (root / "mma" / "results").iterdir()
            }
            results_page.main(root)
            second = {
                path.name: path.read_bytes()
                for path in (root / "mma" / "results").iterdir()
            }
            self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
