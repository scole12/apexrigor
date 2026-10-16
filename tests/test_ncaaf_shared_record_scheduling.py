"""Exercise the shared publisher's real scheduling hook in temporary storage."""
import importlib.util
import json
import os
import subprocess
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
        patch.object(m, 'discover_isolated', return_value=[]).start()

    def record(self, day, products, handoff):
        (self.flags / (day + '.json')).write_text(json.dumps({
            'PRODUCTS_COMPLETE': products, 'RESULTS_SHARED_HANDOFF_COMPLETE': handoff}))

    def producer_calls(self, run):
        return [c for c in run.call_args_list if c.args[0][0] == sys.executable]

    def test_only_finished_products_without_handoff_are_prepared(self):
        self.record('2026-09-10', False, False)
        self.record('2026-09-11', True, True)
        self.record('2026-09-12', True, False)
        before = {f.name: f.read_bytes() for f in self.flags.iterdir()}
        with patch.object(m, 'run', return_value=json.dumps({'status': 'GENERATED_VERIFIED_ARTIFACT'})) as run:
            result = m.execute(dry_run=False)
        calls = self.producer_calls(run)
        self.assertEqual(len(calls), 1)
        command = calls[0].args[0]
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


class RecordSource(unittest.TestCase):
    """The record reads origin/main books, not the checkout; fetch failure falls back."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = self.root / 'sport'
        flags = self.state / 'grader_completion_state'; flags.mkdir(parents=True)
        (flags / '2026-09-12.json').write_text(json.dumps({'PRODUCTS_COMPLETE': True, 'RESULTS_SHARED_HANDOFF_COMPLETE': False}))
        remote, self.site, other = self.root / 'remote.git', self.root / 'site', self.root / 'other'
        sh = lambda *a, cwd=self.root: subprocess.run(a, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()
        self.sh = sh
        sh('git', 'init', '-q', '--bare', '-b', 'main', str(remote))
        for clone in (self.site, other):
            sh('git', 'clone', '-q', str(remote), str(clone))
            sh('git', 'checkout', '-q', '-B', 'main', cwd=clone)
            sh('git', 'config', 'user.email', 't@example.invalid', cwd=clone); sh('git', 'config', 'user.name', 't', cwd=clone)
        (self.site / 'data').mkdir(); (self.site / 'data/book.json').write_text('old')
        sh('git', 'add', '.', cwd=self.site); sh('git', 'commit', '-qm', 'old', cwd=self.site); sh('git', 'push', '-q', 'origin', 'main', cwd=self.site)
        sh('git', 'pull', '-q', 'origin', 'main', cwd=other)
        (other / 'data/book.json').write_text('new')
        sh('git', 'commit', '-qam', 'new', cwd=other); sh('git', 'push', '-q', 'origin', 'main', cwd=other)
        self.origin_commit = sh('git', 'rev-parse', 'HEAD', cwd=other)
        (self.site / 'data/book.json').write_text('dirty')  # stale and dirty checkout
        self.addCleanup(patch.stopall)
        for key, value in {'ROOT': self.site, 'STATE_ROOT': self.root / 'shared',
                           'NCAAF_QUEUE': self.state / 'publication_queue'}.items():
            patch.object(m, key, value).start()
        real_git = m.git
        patch.object(m, 'git', lambda *a, cwd=None, timeout=180: real_git(*a, cwd=cwd or self.site, timeout=timeout)).start()
        self.seen = []
        real_run = m.run

        def run(command, **kwargs):
            if command[0] != sys.executable:
                return real_run(command, **kwargs)
            data = Path(command[command.index('--site-data') + 1])
            self.seen.append((data, (data / 'book.json').read_text()))
            return json.dumps({'status': 'GENERATED_VERIFIED_ARTIFACT'})
        patch.object(m, 'run', run).start()

    def status(self):
        return json.loads((self.root / 'shared/derived_results/ncaaf/preparation_status.json').read_text())

    def test_books_come_from_fresh_origin_main_worktree(self):
        outcomes = m.prepare_due_ncaaf_records()
        self.assertEqual(outcomes[0]['status'], 'GENERATED_VERIFIED_ARTIFACT')
        self.assertEqual(self.seen[0][1], 'new')
        self.assertNotEqual(self.seen[0][0], self.site / 'data')
        self.assertEqual(self.status()['site_data_source'], {'mode': 'ORIGIN_MAIN_WORKTREE', 'commit': self.origin_commit})
        self.assertEqual((self.site / 'data/book.json').read_text(), 'dirty')
        self.assertEqual(self.sh('git', 'worktree', 'list', '--porcelain', cwd=self.site).count('worktree '), 1)
        self.assertEqual(list((self.root / 'shared/worktrees').iterdir()), [])

    def test_fetch_failure_falls_back_to_checkout_and_is_recorded(self):
        self.sh('git', 'remote', 'set-url', 'origin', str(self.root / 'missing.git'), cwd=self.site)
        outcomes = m.prepare_due_ncaaf_records()
        self.assertEqual(outcomes[0]['status'], 'GENERATED_VERIFIED_ARTIFACT')
        self.assertEqual(self.seen, [(self.site / 'data', 'dirty')])
        source = self.status()['site_data_source']
        self.assertEqual(source['mode'], 'CHECKOUT_FALLBACK')
        self.assertIn('fetch', source['error'])
        self.assertEqual(self.status()['status'], 'PASS')

    def test_hourly_cleanup_recovers_abandoned_record_worktree(self):
        pid = os.fork()
        if pid == 0:  # killed mid-preparation: the context manager's cleanup never runs
            with m.ncaaf_record_site_data() as (_, source):
                os._exit(23 if source['mode'] == 'ORIGIN_MAIN_WORKTREE' else 1)
        self.assertEqual(os.waitstatus_to_exitcode(os.waitpid(pid, 0)[1]), 23)
        worktrees = self.root / 'shared/worktrees'
        registered = lambda: self.sh('git', 'worktree', 'list', '--porcelain', cwd=self.site).count('worktree ')
        self.assertEqual(len([p for p in worktrees.iterdir() if (p / 'site/data/book.json').is_file()]), 1)
        self.assertEqual(registered(), 2)
        active = worktrees / ('mma-' + 'a' * 64); active.mkdir()
        result = m.hourly_cleanup({'a' * 64})
        self.assertEqual(result['worktrees_removed'], 1)
        self.assertEqual(list(worktrees.iterdir()), [active])
        self.assertEqual(registered(), 1)

    def test_hourly_cleanup_keeps_names_mkdtemp_cannot_make(self):
        worktrees = self.root / 'shared/worktrees'; worktrees.mkdir(parents=True, exist_ok=True)
        kept = [worktrees / 'ncaaf-record-abc', worktrees / 'ncaaf-record-backup_long']
        for path in kept:
            path.mkdir(); (path / 'sentinel').write_text('keep')
        self.assertEqual(m.hourly_cleanup(set())['worktrees_removed'], 0)
        for path in kept:
            self.assertEqual((path / 'sentinel').read_text(), 'keep')


if __name__ == '__main__':
    unittest.main(verbosity=2)
