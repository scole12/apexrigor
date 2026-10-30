"""NFL-only queue ordering and conservative, publication-bound results reuse."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from zoneinfo import ZoneInfo

NY = ZoneInfo('America/New_York')
RESULT_ROOT = Path('/var/opt/apex_nfl/grades/sealed_results')
RESULT_JSON = ('data/nfl_results_summary.json', 'data/nfl_results_archive.json')


def stamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('timezone required')
    return result


def issuance(request):
    manifest = request.manifest
    value = manifest.get('issuance')
    if (request.sport != 'NFL' or
            manifest.get('schema') != 'apex.nfl.publication_queue.v1' or
            not isinstance(value, dict) or
            value.get('schema') != 'apex.nfl.sealed_issuance.v2' or
            not value.get('t2_receipt_path') or
            value.get('issuance_id') != request.request_id):
        return None
    return value


def day(value):
    result = stamp(value['kickoff_ts']).astimezone(NY).date().isoformat()
    if value.get('game_date', result) != result:
        raise ValueError('issuance date mismatch')
    return result


def games(value):
    rows = value['game_ids']
    if (not isinstance(rows, list) or not rows or
            any(not isinstance(row, str) or not row for row in rows) or
            len(set(rows)) != len(rows)):
        raise ValueError('invalid game identity')
    return set(rows)


def select_requests(requests, accepted, api, today):
    """Defer redundant refreshes without changing queues or publication receipts."""
    current = []
    candidates = []
    for request in accepted:
        value = issuance(request)
        try:
            if not value:
                continue
            issuance_day = day(value)
            games(value)
            stamp(value['issued_at'])
            if issuance_day == today:
                current.append(request)
                candidates.append((request, 'pending_current_day'))
                continue
            receipt = api.load_json(
                api.STATE_ROOT / 'receipts/nfl' / (request.request_id + '.json'))
            if not isinstance(receipt, dict):
                continue
            commit = receipt.get('published_commit')
            readback = receipt.get('live_readback')
            if (receipt.get('sport') == 'NFL' and
                    receipt.get('request_id') == request.request_id and
                    receipt.get('status') == 'PUBLISHED' and
                    isinstance(commit, str) and
                    re.fullmatch('[a-fA-F0-9]{40}', commit) and
                    isinstance(readback, dict) and
                    readback.get('status') == 'PASS' and
                    readback.get('published_commit') == commit):
                candidates.append((request, 'already_published'))
        except (OSError, KeyError, TypeError, ValueError, RuntimeError):
            continue
    current.sort(key=lambda request: (stamp(issuance(request)['issued_at']), request.request_id))
    candidates.sort(key=lambda item: (stamp(issuance(item[0])['issued_at']), item[0].request_id))
    selected = []
    for request in requests:
        queue = request.manifest
        deferred = None
        if (request.sport == 'NFL' and
                queue.get('schema') == 'apex.nfl.stage_publication_queue.v2' and
                queue.get('stage') == 'SCHEDULE_REFRESH'):
            intent = api.STATE_ROOT / 'publication_intents/nfl' / (request.request_id + '.json')
            # Preserve every existing durable intent, including COMMITTED/PUSHED.
            if not intent.exists():
                try:
                    source = Path(queue['stage_receipt_path'])
                    if (queue.get('status') != 'QUEUED' or
                            api.sha256_file(source) != queue['stage_receipt_sha256']):
                        raise ValueError('refresh binding')
                    event = api.load_json(source)
                    if (event.get('schema') != 'apex.nfl.schedule_refresh_event.v1' or
                            event.get('status') != 'PASS'):
                        raise ValueError('refresh event')
                    clock = event['clock']
                    slot = clock['NEXT_T2']
                    slot_day = stamp(slot['at_et']).astimezone(NY).date().isoformat()
                    for candidate, reason in candidates:
                        value = issuance(candidate)
                        if (slot.get('cohort_id') == value.get('cohort_id') and
                                bool(value.get('cohort_id')) and slot_day == day(value) and
                                games(slot) == games(value) and
                                stamp(clock['measured_at']) < stamp(value['issued_at'])):
                            deferred = (candidate.request_id, reason)
                            break
                except (OSError, KeyError, TypeError, ValueError, RuntimeError):
                    pass
        if deferred:
            print(json.dumps({'status': 'DEFERRED_REDUNDANT_SCHEDULE',
                              'request_id': request.request_id,
                              'accepted_issuance_id': deferred[0],
                              'derived_reason': deferred[1]}, sort_keys=True),
                  file=sys.stderr, flush=True)
        else:
            selected.append(request)
    ranks = {request.request_id: index for index, request in enumerate(current)}
    return sorted(selected, key=lambda request: (
        0 if request.request_id in ranks else 1,
        ranks.get(request.request_id, 0), request.request_id))


def pointer(api):
    value = api.load_json(RESULT_ROOT / 'current.json')
    if set(value) != {'path', 'sha256'}:
        raise ValueError('result pointer keys')
    digest = value['sha256']
    if not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest):
        raise ValueError('result digest')
    target = RESULT_ROOT / (digest + '.json')
    if value['path'] != str(target) or target.resolve() != target:
        raise ValueError('result pointer target')
    if api.sha256_file(target) != digest:
        raise ValueError('result target hash')
    return value


def blob(api, worktree, commit, relative):
    return subprocess.check_output(
        ['git', 'show', commit + ':' + relative], cwd=worktree,
        stderr=subprocess.PIPE, timeout=30, env=api._git_env(worktree))


def baseline(worktree, api):
    bound = pointer(api)
    bodies = {name: (worktree / name).read_bytes() for name in RESULT_JSON}
    summary, archive = (json.loads(bodies[name]) for name in RESULT_JSON)
    if (summary.get('schema_version') != 'APEX_NFL_RESULTS_SUMMARY_V1' or
            archive.get('schema_version') != 'APEX_NFL_RESULTS_ARCHIVE_V2' or
            any(value.get('sport') != 'NFL' or value.get('canonical_result') != bound
                for value in (summary, archive))):
        raise ValueError('baseline result binding')
    # Missing scientific/message state (including older grader-only summaries)
    # falls back to the existing full builder.
    if not isinstance(summary.get('scientific_release_state'), str):
        raise ValueError('baseline scientific state absent')
    if summary.get('message') != 'Exact sealed NFL issuance and grade state.':
        raise ValueError('first issuance message requires full build')
    paths = {'nfl/results/index.html'}
    for root in ('nfl/results', 'public/nfl/results'):
        paths.update(path.relative_to(worktree).as_posix()
                     for path in (worktree / root).rglob('*') if path.is_file())
    for name in paths:
        bodies[name] = (worktree / name).read_bytes()
    base = api.git('rev-parse', 'HEAD', cwd=worktree)
    if any(blob(api, worktree, base, name) != body for name, body in bodies.items()):
        raise ValueError('baseline differs from source commit')
    hashes = {name: hashlib.sha256(bodies[name]).hexdigest() for name in RESULT_JSON}
    for path in sorted((api.STATE_ROOT / 'receipts/nfl').glob('*.json')):
        try:
            receipt = api.load_json(path)
            commit = receipt.get('published_commit')
            if (receipt.get('sport') != 'NFL' or receipt.get('status') != 'PUBLISHED' or
                    receipt.get('live_readback', {}).get('status') != 'PASS' or
                    not isinstance(commit, str) or not re.fullmatch('[a-f0-9]{40}', commit) or
                    any(receipt.get('nfl_surface_hashes', {}).get(name) != digest
                        for name, digest in hashes.items())):
                continue
            ancestor = subprocess.run(
                ['git', 'merge-base', '--is-ancestor', commit, base], cwd=worktree,
                capture_output=True, timeout=30, env=api._git_env(worktree))
            if ancestor.returncode != 0:
                continue
            # HTML has no receipt hash: authenticate its bytes through the same
            # accepted source commit, rather than inventing publication evidence.
            if all(blob(api, worktree, commit, name) == body for name, body in bodies.items()):
                if pointer(api) != bound:
                    raise ValueError('pointer changed during baseline check')
                return bound, bodies, summary
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
            continue
    raise ValueError('no accepted publication authenticates baseline')


def build_issuance(request, worktree, api):
    command = [sys.executable, str(worktree / 'bin/build_nfl_public_payload.py'),
               '--output-root', str(worktree)]

    def full():
        api.run_nfl_build(command, cwd=worktree)

    if issuance(request) is None:
        full()
        return None
    try:
        bound, bodies, summary = baseline(worktree, api)
    except (OSError, KeyError, TypeError, ValueError, RuntimeError, subprocess.SubprocessError):
        full()
        return None
    api.run_nfl_build([*command, '--board-only'], cwd=worktree)
    try:
        today = api.load_json(worktree / 'data/nfl_today.json')
        if (pointer(api) != bound or
                today.get('scientific_release_state') != summary['scientific_release_state']):
            raise ValueError('result reuse state changed')
        # Board rendering also touches the results route. Keep its authenticated
        # baseline bytes, including timestamps, on the reuse path.
        for name, body in bodies.items():
            (worktree / name).write_bytes(body)
    except (OSError, KeyError, TypeError, ValueError, RuntimeError):
        full()
        return None

    def finish():
        try:
            if pointer(api) != bound or any(
                    (worktree / name).read_bytes() != body for name, body in bodies.items()):
                raise ValueError('result reuse changed before consumption')
        except (OSError, TypeError, ValueError, RuntimeError):
            # Full builder loads the current pointer itself; no reused result
            # objects or old pointer are supplied to it.
            full()

    return finish
