"""Same-date NCAAF DISPLAY revisions may publish when verified; backlog rules stay intact."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

SOURCE = Path(
    os.environ.get(
        "PUBLISHER_SOURCE",
        str(Path(__file__).resolve().parents[1] / "bin/apex_shared_site_publisher.py"),
    )
)
spec = importlib.util.spec_from_file_location("display_revision_publisher", SOURCE)
p = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = p
spec.loader.exec_module(p)

REVISION_SHA = "a" * 64
OTHER_SHA = "b" * 64
ISSUANCE_A = "1" * 64
ISSUANCE_B = "2" * 64
SLATE = "2026-10-17"


def picks_payload(revision_sha: str | None = None, issuance_ids=(ISSUANCE_A,)):
    games = [
        {
            "positions": [
                {"issuance_id": iid, "position_id": iid}
                for iid in issuance_ids
            ]
        }
    ]
    payload = {"slate": {"slate_date_et": SLATE, "games": games}}
    if revision_sha:
        payload["public_rating_revision"] = {"sha256": revision_sha}
    return payload


class SameDateDisplayRevision(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.payload = self.root / "payload"
        self.site = self.root / "site"
        self.payload.mkdir()
        self.site.mkdir()

    def manifest(self, **extra):
        base = {
            "source_hashes": {},
            "display_slate_date_et": SLATE,
        }
        base.update(extra)
        return base

    def put(self, root: Path, name: str, value):
        body = value if isinstance(value, bytes) else json.dumps(value).encode()
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        return body

    def display_request(self, manifest):
        return p.Request("NCAAF", "c" * 64, manifest, self.payload, SLATE, "DISPLAY")

    def results_request(self, manifest):
        return p.Request("NCAAF", "d" * 64, manifest, self.payload, SLATE, "RESULTS")

    def seed_display_pair(self, current_picks, incoming_picks, manifest_extra=None):
        manifest = self.manifest(**(manifest_extra or {}))
        self.put(self.site, "data/ncaaf_today.json", current_picks)
        self.put(self.site, "ncaaf/index.html", b"current html")
        self.put(self.payload, "data/ncaaf_today.json", incoming_picks)
        self.put(self.payload, "ncaaf/index.html", b"incoming html")
        for name in ("data/ncaaf_today.json", "ncaaf/index.html"):
            manifest["source_hashes"][name] = hashlib.sha256(
                (self.payload / name).read_bytes()
            ).hexdigest()
        return manifest

    def test_newer_site_date_still_skipped(self):
        manifest = self.manifest()
        self.put(self.site, "data/ncaaf_today.json", picks_payload())
        self.put(self.site, "ncaaf/index.html", b"newer")
        self.put(self.payload, "data/ncaaf_today.json", picks_payload(revision_sha=REVISION_SHA))
        self.put(self.payload, "ncaaf/index.html", b"incoming")
        site_payload = json.loads((self.site / "data/ncaaf_today.json").read_text())
        site_payload["slate"]["slate_date_et"] = "2026-10-18"
        self.put(self.site, "data/ncaaf_today.json", site_payload)
        request = self.display_request(manifest)
        skipped = p.publication_skip_paths(request, self.site)
        self.assertIn("data/ncaaf_today.json", skipped)
        self.assertIn("ncaaf/index.html", skipped)

    def test_same_date_without_revision_still_skipped(self):
        manifest = self.seed_display_pair(picks_payload(), picks_payload())
        request = self.display_request(manifest)
        skipped = p.publication_skip_paths(request, self.site)
        self.assertEqual(skipped, {"data/ncaaf_today.json", "ncaaf/index.html"})

    def test_same_date_with_matching_revision_is_not_skipped(self):
        manifest = self.seed_display_pair(
            picks_payload(),
            picks_payload(revision_sha=REVISION_SHA),
            {"public_rating_revision_sha256": REVISION_SHA},
        )
        request = self.display_request(manifest)
        skipped = p.publication_skip_paths(request, self.site)
        self.assertNotIn("data/ncaaf_today.json", skipped)
        self.assertNotIn("ncaaf/index.html", skipped)

    def test_same_date_with_matching_revision_copies_payload(self):
        manifest = self.seed_display_pair(
            picks_payload(),
            picks_payload(revision_sha=REVISION_SHA),
            {"public_rating_revision_sha256": REVISION_SHA},
        )
        request = self.display_request(manifest)
        p.copy_queued_payload(request, self.site)
        self.assertEqual(
            (self.site / "ncaaf/index.html").read_bytes(),
            b"incoming html",
        )
        self.assertEqual(
            json.loads((self.site / "data/ncaaf_today.json").read_text())[
                "public_rating_revision"
            ]["sha256"],
            REVISION_SHA,
        )

    def test_mismatched_revision_sha_still_skipped(self):
        manifest = self.seed_display_pair(
            picks_payload(),
            picks_payload(revision_sha=OTHER_SHA),
            {"public_rating_revision_sha256": REVISION_SHA},
        )
        request = self.display_request(manifest)
        skipped = p.publication_skip_paths(request, self.site)
        self.assertEqual(skipped, {"data/ncaaf_today.json", "ncaaf/index.html"})

    def test_results_same_date_still_skips_public_state(self):
        manifest = self.seed_display_pair(
            picks_payload(),
            picks_payload(revision_sha=REVISION_SHA),
            {"public_rating_revision_sha256": REVISION_SHA},
        )
        results = {
            "season_year": 2026,
            "latest_graded_slate": SLATE,
            "positions": [{"position_id": ISSUANCE_A, "result": "W"}],
        }
        for root in (self.payload, self.site):
            self.put(root, "data/ncaaf_results_cumulative.json", results)
        request = self.results_request(manifest)
        skipped = p.publication_skip_paths(request, self.site)
        self.assertEqual(skipped, {"data/ncaaf_today.json", "ncaaf/index.html"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
