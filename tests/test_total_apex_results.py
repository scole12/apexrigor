"""Regression checks for the public graded-book fusion boundary."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
from apex_total_results import fuse_summary
from build_total_apex_results import build


class TotalResultsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = self.root / "data"
        self.data.mkdir()
        self.base = {"sports": {"mlb": {"wins": 9, "losses": 5, "pushes": 1},
                                "nfl": {"wins": 2, "losses": 3, "pushes": 0}},
                     "sports_included": ["mlb", "nfl"], "overall": {"wins": 9999}}

    def put(self, name, value):
        (self.data / (name + ".json")).write_text(json.dumps(value))

    def mma(self, bout, result="W", issuance="event-1"):
        return {"bout_id": bout, "issuance_id": issuance, "market": "WINNER",
                "commercial_grade_id": issuance + bout, "result": result,
                "source": "PRODUCTION_COMMERCIAL_GRADES", "graded_at_utc": "2026-09-06T10:00:00Z"}

    def test_mma_archive_plus_latest_is_cumulative_and_deduplicated(self):
        old, new = self.mma("old", "L"), self.mma("new", issuance="event-2")
        self.put("mma_results_archive", {"events": [
            {"event_date": "2026-09-01", "latest_results": [old]},
            {"event_date": "2026-09-05", "latest_results": [new]}]})
        self.put("mma_results_summary", {"latest_event_results": [new, {**new, "market": "TOTALS"}]})
        fused = fuse_summary(self.base, data_dir=self.data)
        self.assertEqual(fused["sports_included"], ["mlb", "nfl", "mma"])
        self.assertEqual((fused["overall_wins"], fused["overall_losses"], fused["overall_pushes"]), (12, 9, 1))
        self.assertEqual(fused["sports"]["mma"]["source_row_count"], 2)
        self.assertEqual(fused, fuse_summary(fused, data_dir=self.data))
        self.assertEqual(fused["sports"]["mlb"], self.base["sports"]["mlb"])

    def test_fuse_provenance_is_checkout_path_independent(self):
        self.put("mma_results_summary", {"latest_event_results": [self.mma("one")]})
        first = fuse_summary(self.base, data_dir=self.data)
        with tempfile.TemporaryDirectory() as second_root:
            second_data = Path(second_root) / "nested" / "data"
            shutil.copytree(self.data, second_data)
            second = fuse_summary(self.base, data_dir=second_data)
        self.assertEqual(first, second)
        self.assertEqual(first["total_apex_fuse"]["builder"], "bin/apex_total_results.py")
        self.assertTrue(all(
            source["path"].startswith("data/")
            for sources in first["total_apex_fuse"]["sources"].values()
            for source in sources
        ))

    def test_conflicting_mma_snapshot_does_not_replace_summary(self):
        self.put("apex_results_summary", self.base)
        self.put("mma_results_summary", {"latest_event_results": [self.mma("one"), self.mma("one", "L")]})
        before = (self.data / "apex_results_summary.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            build(self.root)
        self.assertEqual(before, (self.data / "apex_results_summary.json").read_bytes())

    def test_scientific_and_pending_rows_do_not_create_graded_sports(self):
        self.put("mma_results_summary", {"latest_event_results": [
            {**self.mma("science"), "source": "SCIENTIFIC_SCORE"}, self.mma("pending", "PENDING")]})
        fused = fuse_summary(self.base, data_dir=self.data)
        self.assertNotIn("mma", fused["sports_included"])
        self.assertEqual(fused["overall_wins"], 11)

    def test_ncaaf_lifetime_book_and_count_validation(self):
        book = {"positions": [{"position_id": "n1", "result": "W", "slate_date": "2026-09-05"},
                              {"position_id": "n2", "result": "PUSH", "slate_date": "2026-09-05"}],
                "lifetime_record": {"W": 1, "L": 0, "PUSH": 1}}
        self.put("ncaaf_results_cumulative", book)
        self.put("ncaaf_results_summary", book)
        fused = fuse_summary(self.base, data_dir=self.data)
        self.assertEqual(fused["sports"]["ncaaf"]["positions_settled"], 2)
        self.assertEqual(fused["overall_pushes"], 2)
        book["lifetime_record"]["W"] = 2
        self.put("ncaaf_results_cumulative", book)
        with self.assertRaisesRegex(ValueError, "mismatch"):
            fuse_summary(self.base, data_dir=self.data)

    def test_nhl_enters_only_when_issued_book_is_graded(self):
        book = {"sport": "NHL", "status": "UNISSUED", "issuances": [], "grades": []}
        self.put("nhl_results_archive", book)
        self.assertNotIn("nhl", fuse_summary(self.base, data_dir=self.data)["sports_included"])
        book.update(status="ACTIVE", issuances=[{"issuance_id": "i1", "slate_date": "2026-09-09",
                    "positions": [{"position_id": "p1", "market": "TOTALS"}]}])
        self.put("nhl_results_archive", book)
        self.assertNotIn("nhl", fuse_summary(self.base, data_dir=self.data)["sports_included"])
        book["grades"] = [{"grade_id": "g1", "issuance_id": "i1", "settlements": [{"position_id": "p1", "result": "LOSS"}]},
                          {"grade_id": "g2", "supersedes_grade_id": "g1", "issuance_id": "i1", "settlements": [{"position_id": "p1", "result": "WIN"}]}]
        self.put("nhl_results_archive", book)
        fused = fuse_summary(self.base, data_dir=self.data)
        self.assertIn("nhl", fused["sports_included"])
        self.assertEqual((fused["sports"]["nhl"]["wins"], fused["sports"]["nhl"]["losses"]), (1, 0))
        book["grades"][0]["supersedes_grade_id"] = "g2"
        self.put("nhl_results_archive", book)
        with self.assertRaisesRegex(ValueError, "Cyclic"):
            fuse_summary(self.base, data_dir=self.data)

    def test_unbound_grade_and_duplicate_positions_are_rejected(self):
        self.put("nhl_results_archive", {"sport": "NHL", "issuances": [], "grades": [
            {"grade_id": "g", "issuance_id": "i", "settlements": [{"position_id": "missing", "result": "WIN"}]}]})
        with self.assertRaisesRegex(ValueError, "Unbound"):
            fuse_summary(self.base, data_dir=self.data)

    def test_duplicate_cumulative_positions_are_rejected(self):
        row = {"position_id": "same", "result": "W"}
        self.put("ncaaf_results_cumulative", {"positions": [row, row], "lifetime_record": {"W": 2}})
        with self.assertRaisesRegex(ValueError, "duplicate"):
            fuse_summary(self.base, data_dir=self.data)

    def test_canonical_archive_writer_retains_other_sports_on_rebuild(self):
        path = Path("/opt/apex_mlb/current/bin/apex_canonical_results_summary.py")
        if not path.is_file():
            self.skipTest("canonical MLB writer is available only on the production host")
        spec = importlib.util.spec_from_file_location("canonical_results_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        projection = deepcopy(self.base)
        projection.update(overall_wins=9, overall_losses=5, overall_pushes=1, latest_graded_date="")
        projection["sports"].pop("nfl")
        archive = self.data / "results_archive.json"
        archive.write_text(json.dumps({"_canonical_grader_receipt_projection": projection}))
        self.put("apex_results_summary", self.base)
        self.put("mma_results_summary", {"latest_event_results": [self.mma("one")]})
        dest = self.data / "apex_results_summary.json"
        module.write_canonical_results_summary(source_path=archive, out_path=dest)
        first = json.loads(dest.read_text())
        module.write_canonical_results_summary(source_path=archive, out_path=dest)
        self.assertEqual(first, json.loads(dest.read_text()))
        self.assertEqual(first["sports_included"], ["mlb", "nfl", "mma"])
        self.assertEqual(first["overall_wins"], 12)


if __name__ == "__main__":
    unittest.main()
