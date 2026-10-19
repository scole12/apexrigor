"""Offline publisher integration tests: real local bare Git remote, fake reader."""
import importlib.util
import io
from datetime import date
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('publish_nba', ROOT / 'bin/publish_nba.py')
pub = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pub)
DAY = date(2026, 10, 20)


class PublishNBA(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.remote, self.root, self.other = (base / name for name in ('origin.git', 'publish', 'other'))
        subprocess.run(['git', 'init', '--bare', '--initial-branch=main', str(self.remote)],
                       capture_output=True, check=True)
        subprocess.run(['git', 'clone', str(self.remote), str(self.root)], capture_output=True, check=True)
        for key, value in (('user.name', 'Fixture'), ('user.email', 'fixture@example.invalid'),
                           ('core.autocrlf', 'false')):
            pub.git(self.root, 'config', key, value)
        (self.root / 'data').mkdir()
        for name in pub.FILES:
            (self.root / name).write_text(json.dumps(dict(sport='NBA', positions=[], schedule_updated_at='old'))+'\n')
        (self.root / 'other-sport.txt').write_text('original\n')
        pub.git(self.root, 'add', '.')
        pub.git(self.root, 'commit', '-m', 'fixture')
        pub.git(self.root, 'push', '-u', 'origin', 'main')
        subprocess.run(['git', 'clone', str(self.remote), str(self.other)], capture_output=True, check=True)
        for key, value in (('user.name', 'Other fixture'), ('user.email', 'other@example.invalid')):
            pub.git(self.other, 'config', key, value)

    def fake_build(self, *args, **kwargs):
        today = self.root / pub.FILES[0]
        data = json.loads(today.read_text())
        data['schedule_updated_at'] = 'new'
        if self.change:
            data['positions'] = [{'position_id': 'sealed-fixture'}]
        today.write_text(json.dumps(data)+'\n')
        return subprocess.CompletedProcess(args, 0)

    def build(self, change):
        self.change = change
        real_run = subprocess.run
        def run(args, **kwargs):
            return self.fake_build(args, **kwargs) if args[0] == sys.executable else real_run(args, **kwargs)
        with patch.object(pub.subprocess, 'run', side_effect=run):
            return pub.build_payloads(self.root, DAY)

    def test_timestamp_only_does_not_commit(self):
        before = (self.root / pub.FILES[0]).read_bytes()
        self.assertFalse(self.build(False))
        self.assertEqual((self.root / pub.FILES[0]).read_bytes(), before)
        self.assertIsNone(pub.commit_payloads(self.root, DAY))

    def test_changed_build_commits_only_nba_with_requested_author(self):
        self.assertTrue(self.build(True))
        sha = pub.commit_payloads(self.root, DAY)
        self.assertEqual(pub.git(self.root, 'show', '--format=', '--name-only', sha).stdout.strip(), pub.FILES[0])
        self.assertEqual(pub.git(self.root, 'show', '-s', '--format=%an <%ae>', sha).stdout.strip(),
                         'APEX NBA publish <noreply@anthropic.com>')
        self.assertEqual(pub.push_once_with_rebase(self.root, 'main'), sha)
        self.assertEqual(pub.git(self.remote, 'rev-parse', 'main').stdout.strip(), sha)

    def advance_remote(self, conflict=False):
        target = self.other / (pub.FILES[0] if conflict else 'other-sport.txt')
        target.write_text('remote conflicting edit\n' if conflict else 'remote retained change\n')
        pub.git(self.other, 'add', '.')
        pub.git(self.other, 'commit', '-m', 'concurrent remote writer')
        pub.git(self.other, 'push', 'origin', 'main')

    def test_rejected_push_fetches_rebases_and_retries_once(self):
        self.build(True)
        old = pub.commit_payloads(self.root, DAY)
        self.advance_remote()
        real_git = pub.git
        with patch.object(pub, 'git', wraps=real_git) as calls:
            sha = pub.push_once_with_rebase(self.root, 'main')
        self.assertNotEqual(sha, old)
        self.assertEqual(sum(c.args[1] == 'push' for c in calls.call_args_list), 2)
        self.assertEqual(sum('rebase' in c.args for c in calls.call_args_list), 1)
        self.assertEqual(pub.git(self.remote, 'rev-parse', 'main').stdout.strip(), sha)
        self.assertEqual((self.root / 'other-sport.txt').read_text(), 'remote retained change\n')
        self.assertIn('sealed-fixture', (self.root / pub.FILES[0]).read_text())

    def test_rebase_conflict_aborts_without_second_push(self):
        self.build(True)
        old = pub.commit_payloads(self.root, DAY)
        self.advance_remote(conflict=True)
        real_git = pub.git
        with patch.object(pub, 'git', wraps=real_git) as calls:
            with self.assertRaisesRegex(pub.PublishError, 'rebase conflict'):
                pub.push_once_with_rebase(self.root, 'main')
        self.assertEqual(sum(c.args[1] == 'push' for c in calls.call_args_list), 1)
        self.assertEqual(pub.git(self.root, 'rev-parse', 'HEAD').stdout.strip(), old)
        self.assertEqual(pub.git(self.root, 'status', '--porcelain').stdout, '')

    def test_second_rejection_stops(self):
        self.build(True)
        pub.commit_payloads(self.root, DAY)
        self.advance_remote()
        real_git = pub.git
        def run(root, *args, **kwargs):
            if args[0] == 'push':
                return subprocess.CompletedProcess(args, 1, '', '! [rejected] (fetch first)')
            return real_git(root, *args, **kwargs)
        with patch.object(pub, 'git', side_effect=run) as calls:
            with self.assertRaisesRegex(pub.PublishError, 'single rebase/retry'):
                pub.push_once_with_rebase(self.root, 'main')
        self.assertEqual(sum(c.args[1] == 'push' for c in calls.call_args_list), 2)

    def test_staged_unrelated_file_is_rejected(self):
        self.build(True)
        (self.root / 'other-sport.txt').write_text('keep existing work\n')
        pub.git(self.root, 'add', 'other-sport.txt')
        with self.assertRaisesRegex(pub.PublishError, 'outside the NBA'):
            pub.commit_payloads(self.root, DAY)

    def test_dry_run_has_no_commit_push_or_deployment(self):
        self.build(True)
        with patch.object(pub, 'prepare'), patch.object(pub, 'build_payloads', return_value=True), \
             patch.object(pub, 'commit_payloads') as commit, patch.object(pub, 'push_once_with_rebase') as push, \
             patch.object(pub, 'deploy') as deploy, patch('sys.stdout'), patch('sys.stderr'):
            self.assertEqual(pub.main(['--date', str(DAY), '--checkout', str(self.root),
                                       '--branch', 'nba/publish-dryrun', '--dry-run']), 0)
        commit.assert_not_called()
        push.assert_not_called()
        deploy.assert_not_called()
        self.assertEqual(pub.git(self.root, 'status', '--porcelain').stdout, '')

    def test_nonmain_branch_never_deploys(self):
        self.build(True)
        with patch.object(pub, 'prepare'), patch.object(pub, 'build_payloads', return_value=True), \
             patch.object(pub, 'vercel_token') as token, patch.object(pub, 'deploy') as deploy, \
             patch('sys.stdout'), patch('sys.stderr'):
            self.assertEqual(pub.main(['--date', str(DAY), '--checkout', str(self.root),
                                       '--branch', 'nba/publish-dryrun']), 0)
        token.assert_not_called()
        deploy.assert_not_called()
        self.assertEqual(pub.git(self.remote, 'show', 'nba/publish-dryrun:' + pub.FILES[0]).returncode, 0)

    def test_exact_commit_production_request_requires_alias(self):
        sha = 'a' * 40
        with patch.object(pub, 'api', side_effect=[{'id': 'dpl_fixture'},
             {'readyState': 'READY', 'aliasAssigned': False, 'alias': []},
             {'readyState': 'READY', 'aliasAssigned': True, 'alias': ['apexrigor.com'],
              'gitSource': {'sha': sha}, 'ready': 1792440000000}]) as api, \
             patch.object(pub.time, 'sleep'):
            deployment, ready = pub.deploy(sha, 'fixture-token')
        self.assertEqual(deployment, 'dpl_fixture')
        self.assertTrue(ready.endswith('+00:00'))
        request = api.call_args_list[0].args
        self.assertEqual(request[1], '/v13/deployments?teamId=' + pub.TEAM)
        self.assertEqual(request[2]['gitSource'],
                         dict(type='github', repoId=1234114306, ref='main', sha=sha))
        self.assertEqual(request[2]['target'], 'production')
        self.assertEqual(len(api.call_args_list), 3)

    def test_failed_deployment_and_deadline(self):
        with patch.object(pub, 'api', side_effect=[{'id': 'dpl_fixture'}, {'readyState': 'ERROR'}]):
            with self.assertRaisesRegex(pub.PublishError, 'ended ERROR'):
                pub.deploy('a' * 40, 'fixture-token')
        with patch.object(pub, 'api', return_value={'id': 'dpl_fixture'}), \
             patch.object(pub.time, 'monotonic', side_effect=[0, 301]):
            with self.assertRaisesRegex(pub.PublishError, 'within 5 minutes'):
                pub.deploy('a' * 40, 'fixture-token')

    def test_failure_json_does_not_expose_exception_credentials(self):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(pub, 'prepare', side_effect=ValueError('secret://credential')), \
             patch('sys.stdout', out), patch('sys.stderr', err):
            self.assertEqual(pub.main(['--date', str(DAY), '--checkout', str(self.root)]), 1)
        result = json.loads(out.getvalue())
        self.assertEqual(result['step'], 'prepare checkout')
        self.assertNotIn('secret://credential', out.getvalue() + err.getvalue())


if __name__ == '__main__':
    unittest.main(verbosity=2)
