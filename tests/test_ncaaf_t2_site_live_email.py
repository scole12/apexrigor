"""NCAAF T-2 email goes out after apexrigor.com serves the published picks, or at first kickoff.
Deployment state is mocked; nothing is published, emailed or written outside a temp directory."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))

import apex_shared_site_publisher as publisher  # noqa: E402

COMMIT = "a" * 40
LATER = "b" * 40
REQUESTED = "2026-10-02T21:00:30Z"          # 17:00 ET T-2
KICK = 1790982000000                        # 2026-10-02T23:00:00Z, first kickoff 19:00 ET


def deployment(sha=COMMIT, state="READY"):
    return {"readyState": state, "target": "production", "alias": ["apexrigor.com"],
            "url": "apexrigor-x.vercel.app", "meta": {"githubCommitSha": sha}}


class NcaafT2SiteLiveBeforeEmail(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        (base / "payload" / "data").mkdir(parents=True)
        (base / "payload" / "data" / "ncaaf_today.json").write_text(json.dumps(
            {"games": [{"kickoff_utc_ms": KICK - 6 * 3600000}, {"kickoff_utc_ms": KICK + 3600000}, {"kickoff_utc_ms": KICK}]}))
        self.receipt = base / "receipt.json"
        p = mock.patch.object(publisher, "receipt_path", lambda request: self.receipt); p.start(); self.addCleanup(p.stop)
        self.catch_up = mock.MagicMock()
        p = mock.patch.object(publisher, "_catch_up_vercel", self.catch_up); p.start(); self.addCleanup(p.stop)
        self.base = base

    def request(self, product="T2", payload=True):
        return publisher.Request("NCAAF", "rid", {"requested_at_utc": REQUESTED},
                                 self.base / "payload" if payload else None, "2026-10-02", product)

    def check(self, request, serves, now_ms):
        with mock.patch.object(publisher, "ncaaf_deployment_serves", serves):
            return publisher.ncaaf_t2_site_live_before_email(request, {"published_commit": COMMIT, "status": "PUBLISHED"},
                                                            now_ms=now_ms, poll_seconds=0)

    def test_live_site_email_proceeds_and_is_recorded(self):
        out = self.check(self.request(), lambda c: (True, {"deployed_commit": c}), KICK - 7000000)
        self.assertEqual(out["site_live_check"]["status"], "SITE_LIVE_BEFORE_EMAIL")
        self.assertEqual(out["status"], "PUBLISHED")

    def test_not_live_before_kickoff_waits(self):
        with self.assertRaises(RuntimeError) as caught:
            self.check(self.request(), lambda c: (False, {}), KICK - 7000000)
        self.assertTrue(publisher._is_wait_error(str(caught.exception)))
        self.catch_up.assert_called_once_with(COMMIT)

    def test_not_live_at_first_kickoff_email_goes_out_and_is_recorded(self):
        out = self.check(self.request(), lambda c: (False, {}), KICK)
        self.assertEqual(out["site_live_check"]["status"], "EMAIL_SENT_AT_FIRST_KICKOFF_SITE_NOT_LIVE")
        self.assertEqual(out["site_live_check"]["first_kickoff_utc_ms"], KICK)

    def test_deployment_lookup_error_counts_as_not_live(self):
        def broken(c): raise OSError("vercel down")
        with self.assertRaises(RuntimeError):
            self.check(self.request(), broken, KICK - 60000)
        out = self.check(self.request(), broken, KICK + 1)
        self.assertEqual(out["site_live_check"]["status"], "EMAIL_SENT_AT_FIRST_KICKOFF_SITE_NOT_LIVE")
        self.assertIn("vercel down", out["site_live_check"]["check_error"])

    def test_t3_and_results_are_not_held(self):
        never = mock.MagicMock(side_effect=AssertionError("must not check"))
        for product in ("T3", "RESULTS"):
            out = self.check(self.request(product), never, KICK - 7000000)
            self.assertNotIn("site_live_check", out)

    def test_other_sports_are_not_held(self):
        request = publisher.Request("NFL", "rid", {}, None, "2026-10-02", "T2")
        self.assertEqual(publisher.ncaaf_t2_site_live_before_email(request, {"x": 1}), {"x": 1})

    def test_email_already_started_is_not_held(self):
        self.receipt.write_text(json.dumps({"email_dispatch_at_utc": "2026-10-02T21:01:00Z"}))
        out = self.check(self.request(), lambda c: (False, {}), KICK - 7000000)
        self.assertNotIn("site_live_check", out)

    def test_first_kickoff_from_payload_and_fallback(self):
        self.assertEqual(publisher.ncaaf_first_kickoff_ms(self.request()), KICK)
        self.assertEqual(publisher.ncaaf_first_kickoff_ms(self.request(payload=False)), 1790974830000 + 2 * 3600000)


class NcaafDeploymentServes(unittest.TestCase):
    def serves(self, d, ancestry_rc=0):
        calls = []
        def fake_run(args, **kw):
            calls.append(args); return SimpleNamespace(returncode=ancestry_rc if "merge-base" in args else 0)
        with mock.patch.object(publisher, "vercel_deployment", lambda: d), \
             mock.patch.object(publisher.subprocess, "run", fake_run):
            return publisher.ncaaf_deployment_serves(COMMIT)[0], calls

    def test_exact_commit_ready(self):
        live, calls = self.serves(deployment())
        self.assertTrue(live); self.assertEqual(calls, [])

    def test_not_ready(self):
        self.assertFalse(self.serves(deployment(state="BUILDING"))[0])

    def test_later_deployment_containing_commit(self):
        self.assertTrue(self.serves(deployment(sha=LATER), ancestry_rc=0)[0])

    def test_later_deployment_without_commit(self):
        self.assertFalse(self.serves(deployment(sha=LATER), ancestry_rc=1)[0])

    def test_preview_or_other_alias_is_not_live(self):
        d = deployment(); d["target"] = None
        self.assertFalse(self.serves(d)[0])


if __name__ == "__main__":
    unittest.main()
