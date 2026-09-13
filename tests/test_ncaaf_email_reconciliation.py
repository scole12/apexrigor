"""Regression checks for dispatch decisions, with external calls replaced by sinks."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import hashlib
from email.message import EmailMessage
from email.policy import SMTP

SOURCE = Path(os.environ.get('PUBLISHER_SOURCE', str(Path(__file__).resolve().parents[1] / 'bin/apex_shared_site_publisher.py')))
spec = importlib.util.spec_from_file_location('publisher_under_test', SOURCE)
p = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = p
spec.loader.exec_module(p)


class EmailReconciliation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.addCleanup(patch.stopall)
        patch.object(p, 'STATE_ROOT', self.root).start()
        self.request = p.Request('NCAAF', 'a' * 64,
                                 {'canonical_public_payload_sha256': 'b' * 64},
                                 None, '2026-09-11', 'RESULTS')
        self.publication = {'status': 'PUBLISHED', 'sport': 'NCAAF',
                            'request_id': self.request.request_id,
                            'published_commit': 'new-commit'}
        self.path = p.receipt_path(self.request)
        self.shell = patch.object(p, 'run', return_value='').start()
        self.history = patch.object(p, 'matching_ncaaf_workflow_runs', return_value=[]).start()
        self.wait = patch.object(p, 'wait_for_ncaaf_workflow', return_value=self.run_row()).start()
        self.evidence = patch.object(p, 'preserve_ncaaf_email_evidence',
                                     return_value={'status': 'PASS', 'message_id': '<retained>'}).start()

    def run_row(self, conclusion='success', status='completed', run_id=123):
        return {'databaseId': run_id, 'status': status, 'conclusion': conclusion,
                'url': 'https://example.invalid/run/' + str(run_id)}

    def prior(self, **fields):
        p.atomic_json(self.path, {**self.publication, **fields})

    def dispatches(self):
        return [call for call in self.shell.call_args_list
                if call.args and call.args[0][:3] == ['gh', 'workflow', 'run']]

    def test_new_request_dispatches_once(self):
        result = p.dispatch_ncaaf_email(self.request, self.publication)
        self.assertEqual(len(self.dispatches()), 1)
        self.assertTrue(result['status'].endswith('_EMAIL_VERIFIED'))

    def test_saved_failed_run_is_not_resent(self):
        self.prior(email_workflow_run_id=123, email_dispatch_at_utc='2026-09-12T01:00:00Z')
        self.history.return_value = [self.run_row('failure')]
        self.evidence.side_effect = RuntimeError('provider evidence unavailable')
        with self.assertRaises(RuntimeError):
            p.dispatch_ncaaf_email(self.request, self.publication)
        self.assertEqual(len(self.dispatches()), 0)

    def test_failed_run_found_without_local_id_is_not_resent(self):
        self.history.return_value = [self.run_row('failure')]
        self.evidence.side_effect = RuntimeError('provider evidence unavailable')
        with self.assertRaises(RuntimeError):
            p.dispatch_ncaaf_email(self.request, self.publication)
        self.assertEqual(len(self.dispatches()), 0)

    def test_lost_dispatch_response_is_not_resent(self):
        self.prior(status='PUBLISHED_EMAIL_DISPATCH_INTENT',
                   email_dispatch_at_utc='2026-09-12T01:00:00Z', email_workflow_run_id=None)
        with self.assertRaises(RuntimeError):
            p.dispatch_ncaaf_email(self.request, self.publication)
        self.assertEqual(len(self.dispatches()), 0)

    def test_failed_run_with_provider_acceptance_reconciles_without_send(self):
        self.history.return_value = [self.run_row('failure')]
        result = p.dispatch_ncaaf_email(self.request, self.publication)
        self.assertEqual(len(self.dispatches()), 0)
        self.evidence.assert_called_once_with(self.request, self.run_row('failure'))
        self.assertTrue(result['status'].endswith('_EMAIL_VERIFIED'))

    def test_two_failed_runs_are_ambiguous(self):
        self.history.return_value = [self.run_row('failure', run_id=123),
                                     self.run_row('failure', run_id=124)]
        with self.assertRaises(RuntimeError):
            p.dispatch_ncaaf_email(self.request, self.publication)
        self.assertEqual(len(self.dispatches()), 0)

    def test_active_run_is_reconciled_without_new_dispatch(self):
        self.history.return_value = [self.run_row(None, 'in_progress')]
        result = p.dispatch_ncaaf_email(self.request, self.publication)
        self.assertEqual(len(self.dispatches()), 0)
        self.assertTrue(result['status'].endswith('_EMAIL_VERIFIED'))

    def test_timeout_keeps_durable_intent_for_next_process(self):
        self.wait.side_effect = RuntimeError('transport timed out')
        with self.assertRaises(RuntimeError):
            p.dispatch_ncaaf_email(self.request, self.publication)
        self.assertEqual(len(self.dispatches()), 1)
        self.wait.side_effect = None
        with self.assertRaises(RuntimeError):
            p.dispatch_ncaaf_email(self.request, self.publication)
        self.assertEqual(len(self.dispatches()), 1)

    def test_publication_does_not_erase_email_intent(self):
        self.prior(status='PUBLISHED_EMAIL_DISPATCH_INTENT',
                   email_workflow_run_id=123, email_dispatch_at_utc='2026-09-12T01:00:00Z')
        patch.object(p, 'LOCK_PATH', self.root / 'publication.lock').start()
        patch.object(p, 'discover', return_value=[self.request]).start()
        patch.object(p, 'publish', return_value=dict(self.publication)).start()

        def inspect_prior(request, receipt):
            saved = json.loads(self.path.read_text())
            self.assertEqual(saved.get('email_workflow_run_id'), 123)
            self.assertEqual(saved.get('email_dispatch_at_utc'), '2026-09-12T01:00:00Z')
            return receipt

        patch.object(p, 'dispatch_ncaaf_email', side_effect=inspect_prior).start()
        p.execute(dry_run=False)


class HistoryCoverage(unittest.TestCase):
    def test_attempt_on_second_page_is_found(self):
        request = p.Request('NCAAF', 'a' * 64,
                            {'requested_at_utc': '2026-09-12T01:00:00Z'}, None,
                            '2026-09-11', 'RESULTS')
        row = {'id': 7, 'display_title': p.ncaaf_workflow_title(request),
               'status': 'completed', 'conclusion': 'failure',
               'html_url': 'https://example.invalid/run/7', 'head_sha': 'b' * 40,
               'run_attempt': 1}
        pages = [{'total_count': 2, 'workflow_runs': [{**row, 'id': 8, 'display_title': 'Other request'}]},
                 {'total_count': 2, 'workflow_runs': [row]}]
        with patch.object(p, 'run', return_value="\n".join(json.dumps(page) for page in pages)):
            result = p.matching_ncaaf_workflow_runs(request)
        self.assertEqual([r['databaseId'] for r in result], [7])

    def test_incomplete_history_blocks_decision(self):
        request = p.Request('NCAAF', 'a' * 64,
                            {'requested_at_utc': '2026-09-12T01:00:00Z'}, None,
                            '2026-09-11', 'RESULTS')
        with patch.object(p, 'run', return_value=json.dumps({'total_count': 1, 'workflow_runs': []})):
            with self.assertRaises(RuntimeError):
                p.matching_ncaaf_workflow_runs(request)


class PhysicalEmailEvidence(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(patch.stopall)
        self.root = Path(self.temp.name)
        patch.object(p, 'STATE_ROOT', self.root).start()
        self.request = p.Request('NCAAF', 'a' * 64,
                                 {'canonical_public_payload_sha256': 'b' * 64, 'source_hashes': {}},
                                 None, '2026-09-11', 'RESULTS')
        self.message_id = '<ncaaf-20260911-results-' + 'b' * 20 + '@apexrigor.com>'
        msg = EmailMessage()
        msg['From'] = 'sender@example.invalid'
        msg['To'] = 'recipient@example.invalid'
        msg['Message-ID'] = self.message_id
        msg.set_content('Test evidence; never sent.')
        self.attachments = []
        for name in ('APEX_TOTAL_RECORD_20260911.png', 'NCAAF_PRIOR_DAY_SLATE_20260911.png',
                     'NCAAF_DETAILED_RESULTS_20260911.pdf'):
            body = ('fixture ' + name).encode()
            digest = hashlib.sha256(body).hexdigest()
            msg.add_attachment(body, maintype='application', subtype='octet-stream', filename=name)
            self.request.manifest['source_hashes']['data/ncaaf/2026-09-11/results/' + name] = digest
            self.attachments.append({'filename': name, 'sha256': digest})
        self.eml = msg.as_bytes(policy=SMTP)
        self.transaction = {
            'request_id': self.request.request_id, 'slate_date': self.request.slate_date,
            'delivery_mode': 'NORMAL', 'message_id': self.message_id, 'attachment_count': 3,
            'envelope_recipients': ['recipient@example.invalid'],
            'smtp_recipient_responses': [{'recipient': 'recipient@example.invalid', 'code': 250, 'accepted': True}],
            'smtp_data_response_code': 250, 'delivery_state': 'PROVIDER_ACCEPTED',
            'credentials_recorded': False, 'attachments': self.attachments,
            'mime_sha256': hashlib.sha256(self.eml).hexdigest(),
        }
        self.evidence_root = self.root / 'email_evidence/ncaaf' / self.request.request_id
        self.evidence_root.mkdir(parents=True)

    def preserve(self, attempt=1):
        (self.evidence_root / 'message.eml').write_bytes(self.eml)
        (self.evidence_root / 'transaction.json').write_text(json.dumps(self.transaction))
        return p.preserve_ncaaf_email_evidence(self.request, {'databaseId': 123, 'attempt': attempt})

    def test_exact_physical_evidence_is_accepted(self):
        self.assertEqual(self.preserve()['status'], 'PASS')

    def test_modified_message_is_rejected(self):
        self.eml = self.eml.replace(b'Test evidence', b'Tampered evidence')
        with self.assertRaises(RuntimeError):
            self.preserve()

    def test_attachment_manifest_cannot_substitute_another_file(self):
        self.attachments[0]['sha256'] = 'c' * 64
        with self.assertRaises(RuntimeError):
            self.preserve()

    def test_rerun_cannot_claim_one_send(self):
        with self.assertRaises(RuntimeError):
            self.preserve(attempt=2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
