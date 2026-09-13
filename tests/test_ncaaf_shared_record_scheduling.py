"""Exercise the shared publisher's real scheduling hook in temporary storage."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

source = Path(os.environ.get('PUBLISHER_SOURCE', 'bin/apex_shared_site_publisher.py')).resolve()
spec = importlib.util.spec_from_file_location('publisher_schedule', source)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class Scheduling(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = self.root / 'sport'
        self.flags = self.state / 'grader_completion_state'; self.flags.mkdir(parents=True)
        self.addCleanup(patch.stopall)
        for key, value in {'ROOT': self.root / 'site', 'STATE_ROOT': self.root / 'shared',
                           'NCAAF_QUEUE': self.state / 'publication_queue',
                           'LOCK_PATH': self.root / 'publication.lock'}.items():
            patch.object(m, key, value).start()
        patch.object(m, 'discover', return_value=[]).start()
        patch.object(m, 'discover_nfl', return_value=[]).start()

    def record(self, day, products, handoff):
        (self.flags / (day + '.json')).write_text(json.dumps({
            'PRODUCTS_COMPLETE': products, 'RESULTS_SHARED_HANDOFF_COMPLETE': handoff}))

    def test_only_finished_products_without_handoff_are_prepared(self):
        self.record('2026-09-10', False, False)
        self.record('2026-09-11', True, True)
        self.record('2026-09-12', True, False)
        before = {f.name: f.read_bytes() for f in self.flags.iterdir()}
        with patch.object(m, 'run', return_value=json.dumps({'status': 'GENERATED_VERIFIED_ARTIFACT'})) as run:
            result = m.execute(dry_run=False)
        self.assertEqual(run.call_count, 1)
        command = run.call_args.args[0]
        self.assertEqual(command[command.index('--date') + 1], '2026-09-12')
        self.assertEqual(command[command.index('--output-root') + 1], str(self.root / 'shared/derived_results/ncaaf'))
        self.assertEqual(before, {f.name: f.read_bytes() for f in self.flags.iterdir()})
        self.assertEqual(result['shared_results_preparation'][0]['status'], 'GENERATED_VERIFIED_ARTIFACT')

    def test_explicit_legacy_dispositions_do_not_reopen_delivery(self):
        self.record('2026-08-29', True, False)
        p = self.flags / '2026-08-29.json'
        obj = json.loads(p.read_text())
        obj['historical_migration'] = 'OWNER_LOCKED_COMPLETE_NO_RECOMPUTE_NO_REDELIVERY'
        p.write_text(json.dumps(obj))
        for day in ('2026-08-30', '2026-08-31', '2026-09-01', '2026-09-02'):
            self.record(day, True, False)
            p = self.flags / (day + '.json')
            obj = json.loads(p.read_text())
            obj.update(completion_disposition='NOT_APPLICABLE_NO_SEALED_ISSUANCE', grade_count=0, final_grade_count=0)
            p.write_text(json.dumps(obj))
        before = {p.name: p.read_bytes() for p in self.flags.iterdir()}
        with patch.object(m, 'run') as run:
            result = m.execute(dry_run=False)
        run.assert_not_called()
        self.assertEqual(result['shared_results_preparation'], [])
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.flags.iterdir()})

    def test_dry_run_and_other_sport_never_generate(self):
        self.record('2026-09-12', True, False)
        with patch.object(m, 'run') as run:
            m.execute(dry_run=True)
            m.execute(dry_run=False, sport='NFL')
        run.assert_not_called()
        self.assertFalse((self.root / 'shared').exists())

    def test_producer_failure_is_saved_without_blocking_other_publications(self):
        self.record('2026-09-12', True, False)
        with patch.object(m, 'run', side_effect=RuntimeError('source mismatch')):
            result = m.execute(dry_run=False)
        self.assertEqual(result['status'], 'NO_PENDING_REQUEST')
        report = json.loads((self.root / 'shared/derived_results/ncaaf/preparation_status.json').read_text())
        self.assertEqual(report['status'], 'BLOCKED')
        self.assertIn('source mismatch', report['outcomes'][0]['error'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
