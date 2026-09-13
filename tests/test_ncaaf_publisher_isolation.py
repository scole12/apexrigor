"""A real local Git remote verifies that publication leaves unrelated work alone."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(os.environ.get('PUBLISHER_SOURCE', str(Path(__file__).resolve().parents[1] / 'bin/apex_shared_site_publisher.py')))
spec = importlib.util.spec_from_file_location('publication_under_test', SOURCE)
p = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = p
spec.loader.exec_module(p)


class IsolatedPublication(unittest.TestCase):
    def test_dirty_work_is_preserved_while_validated_payload_is_published(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            remote, checkout = base / 'remote.git', base / 'checkout'

            def git(*args, cwd=base):
                result = subprocess.run(['git', *args], cwd=cwd, check=True,
                                        text=True, capture_output=True)
                return result.stdout.rstrip('\r\n')

            git('init', '--bare', str(remote))
            git('clone', str(remote), str(checkout))
            git('checkout', '-b', 'main', cwd=checkout)
            git('config', 'user.name', 'Local regression', cwd=checkout)
            git('config', 'user.email', 'regression@example.invalid', cwd=checkout)
            (checkout / 'other-sport.txt').write_text('committed original\n')
            git('add', '.', cwd=checkout)
            git('commit', '-m', 'fixture', cwd=checkout)
            git('push', '-u', 'origin', 'main', cwd=checkout)
            (checkout / 'other-sport.txt').write_text('unsaved other sport work\n')
            (checkout / 'pending.txt').write_text('untracked work\n')
            before = git('status', '--porcelain', cwd=checkout)
            original_head = git('rev-parse', 'HEAD', cwd=checkout)

            def publish_payload(request, worktree):
                self.assertEqual((worktree / 'other-sport.txt').read_text(), 'committed original\n')
                self.assertFalse((worktree / 'pending.txt').exists())
                target = worktree / 'data/ncaaf/results.txt'
                target.parent.mkdir(parents=True)
                target.write_text('validated result fixture\n')
                return {'changed_paths': ['data/ncaaf/results.txt'], 'audit_tail': 'fixture'}

            def bound_git(*args, cwd=None, timeout=180):
                return p.run(['git', *args], cwd=cwd or checkout, timeout=timeout)

            request = p.Request('NCAAF', 'a' * 64, {}, None, '2026-09-11', 'RESULTS')
            with patch.object(p, 'ROOT', checkout), patch.object(p, 'CANONICAL_REMOTE', str(remote)), \
                 patch.object(p, 'STATE_ROOT', base / 'state'), patch.object(p, 'git', side_effect=bound_git), \
                 patch.object(p, 'build_request', side_effect=publish_payload):
                receipt = p.publish(request, dry_run=False)

            self.assertEqual(receipt['status'], 'PUBLISHED')
            self.assertEqual(git('status', '--porcelain', cwd=checkout), before)
            self.assertEqual(git('rev-parse', 'HEAD', cwd=checkout), original_head)
            self.assertEqual((checkout / 'other-sport.txt').read_text(), 'unsaved other sport work\n')
            self.assertEqual((checkout / 'pending.txt').read_text(), 'untracked work\n')
            self.assertEqual(git('--git-dir=' + str(remote), 'show', 'main:other-sport.txt'), 'committed original')
            self.assertEqual(git('--git-dir=' + str(remote), 'show', 'main:data/ncaaf/results.txt'), 'validated result fixture')


if __name__ == '__main__':
    unittest.main(verbosity=2)
