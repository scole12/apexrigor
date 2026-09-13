"""Exercise real queued bytes: dated results survive while newer public state stays put."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('backlog_publisher', os.environ.get('PUBLISHER_SOURCE', str(Path(__file__).resolve().parents[1] / 'bin/apex_shared_site_publisher.py')))
p = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = p
spec.loader.exec_module(p)


class ResultsBacklog(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.payload, self.site = self.root / 'payload', self.root / 'site'
        self.payload.mkdir(); self.site.mkdir()
        self.row1 = {'position_id': '1' * 64, 'result': 'W'}
        self.row2 = {'position_id': '2' * 64, 'result': 'L'}
        self.incoming = {'season_year': 2026, 'latest_graded_slate': '2026-09-11', 'positions': [self.row1]}
        self.existing = {'season_year': 2026, 'latest_graded_slate': '2026-09-12', 'positions': [self.row1, self.row2]}
        self.request = p.Request('NCAAF', 'a' * 64, {
            'source_hashes': {}, 'season_year': 2026, 'graded_slate_date_et': '2026-09-11',
            'display_slate_date_et': '2026-09-12', 'count_scope': 'EXPLICIT_CANONICAL_AND_DISPLAY',
            'display_date': 'September 12, 2026', 'graded_date': 'September 11, 2026',
            'canonical_game_count': 1, 'display_game_count': 1, 'issued_game_count': 1,
            'official_position_count': 2, 'market_pending_game_count': 0,
            'internal_market_pending_game_count': 0, 'canonical_public_payload_sha256': 'b' * 64,
            'sealed_day_payload_sha256': 'c' * 64,
        }, self.payload, '2026-09-11', 'RESULTS')

    def put(self, root, name, value):
        body = value if isinstance(value, bytes) else json.dumps(value).encode()
        target = root / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(body)
        if root == self.payload:
            self.request.manifest['source_hashes'][name] = hashlib.sha256(body).hexdigest()
        return body

    def prepare(self, current_day='2026-09-12'):
        self.put(self.payload, 'data/ncaaf_today.json', {'slate': {'slate_date_et': '2026-09-12'}, 'old': True})
        self.put(self.payload, 'ncaaf/index.html', b'old rendering')
        self.put(self.site, 'data/ncaaf_today.json', {'slate': {'slate_date_et': current_day}, 'keep': True})
        self.put(self.site, 'ncaaf/index.html', b'current issued rendering')
        for root, data in [(self.payload, self.incoming), (self.site, self.existing)]:
            self.put(root, 'data/ncaaf_results_cumulative.json', data)
            self.put(root, 'data/ncaaf_results_summary.json', data)
            self.put(root, 'data/ncaaf_results_archive.json', data['positions'])
        for name in ['APEX_TOTAL_RECORD_20260911.png', 'NCAAF_PRIOR_DAY_SLATE_20260911.png', 'NCAAF_DETAILED_RESULTS_20260911.pdf']:
            self.put(self.payload, 'data/ncaaf/2026-09-11/results/' + name, ('frozen ' + name).encode())

    def test_older_results_deliver_dated_bytes_without_replacing_newer_public_state(self):
        self.prepare()
        before = {str(f.relative_to(self.site)): f.read_bytes() for f in self.site.rglob('*') if f.is_file()}
        p.copy_queued_payload(self.request, self.site)
        p.ncaaf_delivery_manifest(self.request, self.site)
        for name, body in before.items():
            self.assertEqual((self.site / name).read_bytes(), body)
        snapshot = p.results_cumulative_snapshot(self.request)
        self.assertEqual((self.site / snapshot).read_bytes(), (self.payload / 'data/ncaaf_results_cumulative.json').read_bytes())
        manifest = json.loads((self.site / 'data/ncaaf/2026-09-11/full_slate_delivery_manifest.json').read_text())
        self.assertEqual(manifest['results_cumulative_path'], snapshot)
        self.assertEqual(len(manifest['results_files']), 4)
        self.assertNotIn('data/ncaaf_results_cumulative.json', manifest['results_files'])
        for name, digest in manifest['results_files'].items():
            self.assertEqual(hashlib.sha256((self.site / name).read_bytes()).hexdigest(), digest)

    def test_results_can_advance_a_prior_picks_date(self):
        self.prepare(current_day='2026-09-11')
        p.copy_queued_payload(self.request, self.site)
        self.assertEqual((self.site / 'ncaaf/index.html').read_bytes(), b'old rendering')

    def test_later_picks_date_is_preserved(self):
        self.prepare(current_day='2026-09-13')
        p.copy_queued_payload(self.request, self.site)
        self.assertEqual((self.site / 'ncaaf/index.html').read_bytes(), b'current issued rendering')

    def test_new_results_extend_existing_positions(self):
        self.incoming, self.existing = self.existing, self.incoming
        self.prepare()
        p.copy_queued_payload(self.request, self.site)
        self.assertEqual(json.loads((self.site / 'data/ncaaf_results_cumulative.json').read_text()), self.incoming)

    def test_newer_results_cannot_drop_previously_published_positions(self):
        self.incoming = {'season_year': 2026, 'latest_graded_slate': '2026-09-13', 'positions': [self.row2]}
        self.prepare()
        with self.assertRaisesRegex(RuntimeError, 'DROP_PUBLISHED_POSITIONS'):
            p.copy_queued_payload(self.request, self.site)

    def test_settled_result_conflict_is_held(self):
        self.incoming = {'season_year': 2026, 'latest_graded_slate': '2026-09-13', 'positions': [{**self.row1, 'result': 'L'}, self.row2]}
        self.prepare()
        with self.assertRaisesRegex(RuntimeError, 'SETTLEMENT_CONFLICT'):
            p.copy_queued_payload(self.request, self.site)

    def test_existing_dated_snapshot_cannot_be_rewritten(self):
        self.prepare()
        self.put(self.site, p.results_cumulative_snapshot(self.request), b'already frozen different data')
        with self.assertRaisesRegex(RuntimeError, 'DATED_SNAPSHOT_CONFLICT'):
            p.copy_queued_payload(self.request, self.site)

    def test_missing_latest_identity_is_held(self):
        del self.existing['latest_graded_slate']
        self.prepare()
        with self.assertRaisesRegex(RuntimeError, 'LATEST_IDENTITY_ABSENT'):
            p.copy_queued_payload(self.request, self.site)


if __name__ == '__main__':
    unittest.main(verbosity=2)
