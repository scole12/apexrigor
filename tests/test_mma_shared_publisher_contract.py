"""MMA ownership regressions for the serialized shared publisher."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))

import apex_shared_site_publisher as publisher  # noqa: E402


class MmaSharedPublisherContractTests(unittest.TestCase):
    def test_results_renderer_is_an_owned_mma_build_output(self):
        self.assertTrue(publisher.allowed_site_change("mma/results/render.js"))

    def test_legacy_four_market_assets_are_not_owned_outputs(self):
        self.assertFalse(publisher.allowed_site_change("mma/four-markets/index.html"))
        self.assertFalse(
            publisher.allowed_site_change("data/mma_four_markets_20260905.json")
        )

    def test_unrelated_paths_remain_forbidden(self):
        self.assertFalse(publisher.allowed_site_change("bin/arbitrary.py"))
        self.assertFalse(publisher.allowed_site_change("mma/arbitrary.js"))


if __name__ == "__main__":
    unittest.main()
