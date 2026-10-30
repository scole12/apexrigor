"""Fixed fixtures for NFL queue selection and evidence-bound result reuse."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

BIN = Path(__file__).resolve().parents[1] / 'bin'
sys.path.insert(0, str(BIN))
import nfl_timing_repair as repair


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def request(identifier='f' * 64):
    value = {'schema': 'apex.nfl.sealed_issuance.v2', 'issuance_id': identifier,
             't2_receipt_path': '/fixture/T2.json', 'cohort_id': 'cohort',
             'game_date': '2026-10-29', 'game_ids': ['game'],
             'kickoff_ts': '2026-10-30T00:15:00Z', 'issued_at': '2026-10-29T22:15:50Z'}
    return SimpleNamespace(sport='NFL', request_id=identifier,
                           manifest={'schema': 'apex.nfl.publication_queue.v1', 'issuance': value})


def api_fixture(tmp_path):
    return SimpleNamespace(STATE_ROOT=tmp_path / 'state', sha256_file=sha,
                           load_json=lambda path: json.loads(path.read_text()),
                           _git_env=lambda path: {}, git=lambda *args, **kwargs: 'b' * 40)


@pytest.mark.parametrize('change', ['same', 'future', 'cohort', 'games', 'later', 'bad_hash', 'committed', 'pushed'])
def test_schedule_selection_preserves_unrelated_and_durable_requests(tmp_path, change):
    api = api_fixture(tmp_path)
    picks = request()
    event = {'schema': 'apex.nfl.schedule_refresh_event.v1', 'status': 'PASS',
             'clock': {'measured_at': '2026-10-28T11:01:26Z', 'NEXT_T2': {
                 'cohort_id': 'cohort', 'game_ids': ['game'], 'at_et': '2026-10-29T18:15:00-04:00'}}}
    slot = event['clock']['NEXT_T2']
    if change == 'future': slot['at_et'] = '2026-11-01T18:15:00-05:00'
    if change == 'cohort': slot['cohort_id'] = 'other'
    if change == 'games': slot['game_ids'] = ['other']
    if change == 'later': event['clock']['measured_at'] = '2026-10-29T22:16:00Z'
    source = tmp_path / 'event.json'
    write(source, event)
    refresh = SimpleNamespace(sport='NFL', request_id='0' * 64, manifest={
        'schema': 'apex.nfl.stage_publication_queue.v2', 'status': 'QUEUED',
        'stage': 'SCHEDULE_REFRESH', 'stage_receipt_path': str(source),
        'stage_receipt_sha256': sha(source) if change != 'bad_hash' else 'bad'})
    if change in {'committed', 'pushed'}:
        write(api.STATE_ROOT / 'publication_intents/nfl' / (refresh.request_id + '.json'),
              {'phase': change.upper()})
    result = repair.select_requests([refresh, picks], [picks], api, '2026-10-29')
    assert result[0] is picks  # adversarial filename order and product=None
    assert (refresh in result) == (change != 'same')
    # A completed accepted issuance also defers the same redundant request.
    if change == 'same':
        assert repair.select_requests([refresh], [picks], api, '2026-10-29') == []
        assert not (api.STATE_ROOT / 'receipts').exists()
        assert source.exists()


@pytest.fixture
def reuse(tmp_path, monkeypatch):
    api = api_fixture(tmp_path)
    root = tmp_path / 'results'
    root.mkdir()
    sealed = b'{"rows":[]}'
    digest = hashlib.sha256(sealed).hexdigest()
    target = root / (digest + '.json')
    target.write_bytes(sealed)
    bound = {'path': str(target), 'sha256': digest}
    write(root / 'current.json', bound)
    monkeypatch.setattr(repair, 'RESULT_ROOT', root)
    site = tmp_path / 'site'
    summary = {'schema_version': 'APEX_NFL_RESULTS_SUMMARY_V1', 'sport': 'NFL',
               'canonical_result': bound, 'scientific_release_state': 'READY',
               'generated_at_utc': '2026-10-28T00:00:00Z',
               'message': 'Exact sealed NFL issuance and grade state.'}
    write(site / repair.RESULT_JSON[0], summary)
    write(site / repair.RESULT_JSON[1], {'schema_version': 'APEX_NFL_RESULTS_ARCHIVE_V2',
                                       'sport': 'NFL', 'canonical_result': bound})
    html = site / 'nfl/results/index.html'
    html.parent.mkdir(parents=True)
    html.write_bytes(b'published results HTML')
    baseline = {name: (site / name).read_bytes()
                for name in (*repair.RESULT_JSON, 'nfl/results/index.html')}
    monkeypatch.setattr(repair, 'blob', lambda api, worktree, commit, name: baseline[name])
    monkeypatch.setattr(repair.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(returncode=0))
    receipt = api.STATE_ROOT / 'receipts/nfl/prior.json'
    write(receipt, {'sport': 'NFL', 'status': 'PUBLISHED', 'published_commit': 'a' * 40,
                    'live_readback': {'status': 'PASS'},
                    'nfl_surface_hashes': {name: sha(site / name) for name in repair.RESULT_JSON}})
    calls = []

    def build(command, **kwargs):
        calls.append('--board-only' in command)
        write(site / 'data/nfl_today.json', {'scientific_release_state': 'READY'})
        if '--board-only' in command:
            html.write_bytes(b'board renderer changed results route')

    api.run_nfl_build = build
    return SimpleNamespace(api=api, site=site, root=root, receipt=receipt,
                           baseline=baseline, calls=calls, bound=bound)


def test_valid_reuse_preserves_json_timestamps_and_results_html(reuse):
    guard = repair.build_issuance(request(), reuse.site, reuse.api)
    assert callable(guard)
    guard()
    assert reuse.calls == [True]
    assert all((reuse.site / name).read_bytes() == body for name, body in reuse.baseline.items())


@pytest.mark.parametrize('fault', ['stale', 'corrupt', 'missing_evidence', 'bad_evidence', 'target_corrupt', 'first_message', 'html_corrupt'])
def test_invalid_baseline_uses_full_build(reuse, fault):
    summary = reuse.site / repair.RESULT_JSON[0]
    if fault == 'stale':
        value = json.loads(summary.read_text()); value['canonical_result'] = {}; write(summary, value)
    elif fault == 'corrupt': summary.write_bytes(summary.read_bytes() + b' ')
    elif fault == 'missing_evidence': reuse.receipt.unlink()
    elif fault == 'bad_evidence':
        value = json.loads(reuse.receipt.read_text()); value['nfl_surface_hashes'] = {}; write(reuse.receipt, value)
    elif fault == 'target_corrupt': Path(reuse.bound['path']).write_bytes(b'corrupt')
    elif fault == 'first_message':
        value = json.loads(summary.read_text()); value['message'] = 'No NFL positions have been issued; no performance is claimed.'; write(summary, value)
    else: (reuse.site / 'nfl/results/index.html').write_bytes(b'corrupt')
    assert repair.build_issuance(request(), reuse.site, reuse.api) is None
    assert reuse.calls == [False]


@pytest.mark.parametrize('when', ['during_build', 'before_consumption', 'science'])
def test_changed_state_falls_back_to_full_current_build(reuse, when):
    original = reuse.api.run_nfl_build

    def build(command, **kwargs):
        original(command, **kwargs)
        if '--board-only' in command:
            if when == 'during_build': write(reuse.root / 'current.json', {})
            if when == 'science': write(reuse.site / 'data/nfl_today.json', {'scientific_release_state': 'CHANGED'})

    reuse.api.run_nfl_build = build
    guard = repair.build_issuance(request(), reuse.site, reuse.api)
    if when == 'before_consumption':
        write(reuse.root / 'current.json', {})
        guard()
    else:
        assert guard is None
    assert reuse.calls == [True, False]


def test_schedule_and_other_sports_always_use_full_build(reuse):
    other = SimpleNamespace(sport='NFL', request_id='schedule', manifest={
        'schema': 'apex.nfl.stage_publication_queue.v2', 'stage': 'SCHEDULE_REFRESH'})
    assert repair.build_issuance(other, reuse.site, reuse.api) is None
    assert reuse.calls == [False]

def _next_day_case(tmp_path):
    api = api_fixture(tmp_path)
    api.receipt_path = lambda req: (
        api.STATE_ROOT / 'receipts' / req.sport.lower() / (req.request_id + '.json'))
    picks = request()
    source = tmp_path / 'schedule.json'
    write(source, {
        'schema': 'apex.nfl.schedule_refresh_event.v1', 'status': 'PASS',
        'clock': {'measured_at': '2026-10-28T11:01:26Z', 'NEXT_T2': {
            'cohort_id': 'cohort', 'game_ids': ['game'],
            'at_et': '2026-10-29T18:15:00-04:00'}}})
    refresh = SimpleNamespace(sport='NFL', request_id='0' * 64, manifest={
        'schema': 'apex.nfl.stage_publication_queue.v2', 'status': 'QUEUED',
        'stage': 'SCHEDULE_REFRESH', 'stage_receipt_path': str(source),
        'stage_receipt_sha256': sha(source)})
    proof = {'sport': 'NFL', 'request_id': picks.request_id,
             'status': 'PUBLISHED', 'published_commit': 'a' * 40,
             'live_readback': {'status': 'PASS', 'published_commit': 'a' * 40}}
    return api, picks, refresh, proof


def _file_bytes(root):
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('fault', [
    None, 'missing', 'failed', 'wrong_request', 'wrong_sport',
    'not_published', 'invalid_commit', 'wrong_readback_commit',
    'missing_readback_commit'])
def test_next_day_supersession_requires_exact_successful_publication(tmp_path, fault):
    api, picks, refresh, proof = _next_day_case(tmp_path)
    if fault == 'failed': proof['live_readback']['status'] = 'FAIL'
    if fault == 'wrong_request': proof['request_id'] = 'e' * 64
    if fault == 'wrong_sport': proof['sport'] = 'MLB'
    if fault == 'not_published': proof['status'] = 'PUSHED'
    if fault == 'invalid_commit': proof['published_commit'] = 'g' * 40
    if fault == 'wrong_readback_commit': proof['live_readback']['published_commit'] = 'b' * 40
    if fault == 'missing_readback_commit': del proof['live_readback']['published_commit']
    if fault != 'missing': write(api.receipt_path(picks), proof)
    before = _file_bytes(tmp_path)
    assert repair.select_requests([refresh], [picks], api, '2026-10-30') == (
        [] if fault is None else [refresh])
    assert _file_bytes(tmp_path) == before


@pytest.mark.parametrize('phase', ['STARTED', 'BUILT', 'COMMITTED', 'PUSHED'])
def test_next_day_supersession_preserves_every_existing_durable_intent(tmp_path, phase):
    api, picks, refresh, proof = _next_day_case(tmp_path)
    write(api.receipt_path(picks), proof)
    write(api.STATE_ROOT / 'publication_intents/nfl' / (refresh.request_id + '.json'),
          {'phase': phase})
    before = _file_bytes(tmp_path)
    assert repair.select_requests([refresh], [picks], api, '2026-10-30') == [refresh]
    assert _file_bytes(tmp_path) == before


def test_supersession_does_not_remove_non_nfl_request(tmp_path):
    api, picks, refresh, proof = _next_day_case(tmp_path)
    write(api.receipt_path(picks), proof)
    refresh.sport = 'MLB'
    before = _file_bytes(tmp_path)
    assert repair.select_requests([refresh], [picks], api, '2026-10-30') == [refresh]
    assert _file_bytes(tmp_path) == before
