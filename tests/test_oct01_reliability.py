"""2026-10-01 shared publisher: waiting is not failure; a commit Vercel never built is requested once."""
import importlib.util, sys, tempfile, unittest
from pathlib import Path
from unittest import mock


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m; spec.loader.exec_module(m); return m


C = load('apex_vercel_catchup_t', '/opt/apex_site/bin/apex_vercel_catchup.py')
SHA = 'a' * 40


class CatchUp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(); C.STATE = Path(self.tmp)
        self.now = [1000.0]; self.calls = []

    def fake(self, deployments):
        def call(url, body=None):
            self.calls.append((url, body))
            return {'id': 'dpl_new'} if body else {'deployments': deployments}
        return call

    def run_at(self, t, deployments=()):
        self.now[0] = t
        with mock.patch.object(C, '_call', side_effect=self.fake(list(deployments))), mock.patch.object(C.time, 'time', return_value=t):
            return C.ensure_deployment(SHA)

    def test_existing_build_is_left_alone(self):
        self.assertEqual(self.run_at(0, [{'uid': 'dpl_x', 'state': 'BUILDING'}])['status'], 'DEPLOYMENT_EXISTS')
        self.assertFalse([c for c in self.calls if c[1]])

    def test_missing_build_requested_once_after_wait(self):
        self.assertEqual(self.run_at(0)['status'], 'MISSING_WAITING')
        self.assertEqual(self.run_at(C.WAIT_SECONDS - 1)['status'], 'MISSING_WAITING')
        self.assertEqual(self.run_at(C.WAIT_SECONDS + 1)['status'], 'DEPLOYMENT_REQUESTED')
        for t in range(5):
            self.assertEqual(self.run_at(C.WAIT_SECONDS + 60 * (t + 2))['status'], 'ALREADY_REQUESTED')
        posts = [c for c in self.calls if c[1]]
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0][1]['gitSource']['sha'], SHA)

    def test_errored_build_does_not_count(self):
        self.assertEqual(self.run_at(0, [{'uid': 'd', 'state': 'ERROR'}])['status'], 'MISSING_WAITING')

    def test_bad_commit_is_ignored(self):
        self.assertEqual(C.ensure_deployment('xyz')['status'], 'SKIPPED_BAD_COMMIT')


class Waiting(unittest.TestCase):
    def test_wait_markers(self):
        P = load('apex_shared_site_publisher_t', '/opt/apex_site/bin/apex_shared_site_publisher.py')
        self.assertTrue(P._is_wait_error('RuntimeError:DEPLOYMENT_NOT_REQUEST_DESCENDANT'))
        self.assertFalse(P._is_wait_error('RuntimeError:REQUEST_BOUND_NFL_SURFACE_CHANGED:x'))
        src = Path('/opt/apex_site/bin/apex_shared_site_publisher.py').read_text()
        self.assertIn("'WAITING_FOR_DEPLOYMENT' if _is_wait_error(error_text) else 'REQUEST_FAILED'", src)


if __name__ == '__main__':
    unittest.main(verbosity=2)
