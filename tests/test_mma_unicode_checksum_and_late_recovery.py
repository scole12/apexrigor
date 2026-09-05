"""MMA publication regressions; synthetic inputs never enter public data."""
import hashlib
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bin'))
from _mma_forecast_contract import positions_sha256, forecast_status

class MmaUnicodeAndRecoveryTests(unittest.TestCase):
    def test_checksum_matches_immutable_issuance_encoding(self):
        positions = [{'selection': 'SYNTHETIC Farès', 'rationale': 'SYNTHETIC — not a pick'}]
        expected = hashlib.sha256(json.dumps(positions, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
        self.assertEqual(positions_sha256(positions), expected)

    def test_accent_changes_are_not_silently_normalized(self):
        self.assertNotEqual(positions_sha256([{'selection': 'Farès'}]), positions_sha256([{'selection': 'Fares'}]))

    def test_late_run_is_not_described_as_on_time(self):
        state = {'t2': {'status': 'SEALED_LATE_RECOVERY', 'timeliness': 'FAIL', 'actual_utc': '2026-09-05T15:23:06Z'}}
        result = forecast_status(state, [{'synthetic': True}])
        self.assertIn('late recovery', result['headline'])
        self.assertIn('11:23 AM EDT', result['detail'])
        self.assertIn('not backdated', result['detail'])

if __name__ == '__main__':
    unittest.main()
