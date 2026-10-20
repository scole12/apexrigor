#!/usr/bin/env python3
"""Publish sealed NBA payloads from the Geekom; non-main branches never deploy."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

REPO = 'https://github.com/scole12/apexrigor.git'
PROJECT = 'prj_eZTtqClkwx7IcE7NhVAK6UFmBnnB'
TEAM = 'team_ZbMl7Z31fLqnzoCYHAY2a1rk'
FILES = tuple('data/nba_' + name + '.json' for name in
              ('today', 'results_archive', 'results_summary'))
SOURCE = Path(__file__).resolve().parent


class PublishError(RuntimeError):
    pass


def git(root, *args, check=True):
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True,
                            text=True, encoding='utf-8', errors='replace', timeout=120)
    if check and result.returncode:
        raise PublishError('git ' + args[0] + ' failed (exit ' + str(result.returncode) + ')')
    return result


def prepare(root, branch):
    if root == SOURCE.parent or root in SOURCE.parents:
        raise PublishError('checkout must be a dedicated publish clone')
    if not root.exists():
        root.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(['git', 'clone', REPO, str(root)], capture_output=True, timeout=120)
        if result.returncode:
            raise PublishError('clone failed')
    # Never discard existing work, including untracked files, or use another repo.
    if git(root, 'rev-parse', '--show-toplevel').stdout.strip().replace('\\', '/').lower() != root.as_posix().lower():
        raise PublishError('checkout must be the clone root')
    if git(root, 'remote', 'get-url', 'origin').stdout.strip() != REPO:
        raise PublishError('checkout origin is not the NBA site repository')
    if git(root, 'status', '--porcelain', '--untracked-files=all').stdout.strip():
        raise PublishError('publish clone is dirty; preserve and reconcile its existing work')
    git(root, 'check-ref-format', '--branch', branch)
    git(root, 'fetch', 'origin', 'main')
    git(root, 'checkout', '-B', branch, 'origin/main')
    # Owner-authorized reset applies only to this verified clean dedicated clone.
    git(root, 'reset', '--hard', 'origin/main')


def build_payloads(root, day):
    before = {name: (root / name).read_bytes() for name in FILES}
    result = subprocess.run([sys.executable, str(SOURCE / 'build_nba_public_payload.py'),
                             '--date', day.isoformat(), '--root', str(root), '--data-only'],
                            capture_output=True, timeout=120)
    if result.returncode:
        raise PublishError('NBA read-only builder failed (exit ' + str(result.returncode) +
                           '); verify reader configuration/connectivity; credentials withheld')
    # A refresh timestamp alone is not a source-data change.
    old = {name: json.loads(value) for name, value in before.items()}
    new = {name: json.loads((root / name).read_bytes()) for name in FILES}
    old[FILES[0]].pop('schedule_updated_at', None)
    new[FILES[0]].pop('schedule_updated_at', None)
    if old == new:
        for name, value in before.items():
            (root / name).write_bytes(value)
    changed = git(root, 'diff', '--name-only').stdout.splitlines()
    if set(changed) - set(FILES):
        raise PublishError('builder changed files outside the three NBA payloads')
    return bool(changed)


def commit_payloads(root, day):
    git(root, 'add', '--', *FILES)
    if git(root, 'diff', '--cached', '--quiet', check=False).returncode == 0:
        return None
    staged = git(root, 'diff', '--cached', '--name-only').stdout.splitlines()
    if set(staged) - set(FILES):
        raise PublishError('refusing staged files outside the NBA payloads')
    git(root, '-c', 'user.name=APEX NBA publish', '-c', 'user.email=noreply@anthropic.com',
        'commit', '--author=APEX NBA publish <noreply@anthropic.com>',
        '-m', 'Publish NBA sealed picks and results ' + day.isoformat())
    return git(root, 'rev-parse', 'HEAD').stdout.strip()


def push_once_with_rebase(root, branch):
    pushed = git(root, 'push', 'origin', 'HEAD:refs/heads/' + branch, check=False)
    if pushed.returncode:
        if not any(s in pushed.stderr for s in ('(fetch first)', '(non-fast-forward)')):
            raise PublishError('push failed; not a non-fast-forward rejection')
        git(root, 'fetch', 'origin', branch)
        rebased = git(root, '-c', 'user.name=APEX NBA publish',
                      '-c', 'user.email=noreply@anthropic.com', 'rebase', 'FETCH_HEAD', check=False)
        if rebased.returncode:
            git(root, 'rebase', '--abort')
            raise PublishError('push rebase conflict; preserved local commit; no retry push')
        retry = git(root, 'push', 'origin', 'HEAD:refs/heads/' + branch, check=False)
        if retry.returncode:
            raise PublishError('push failed after the single rebase/retry')
    return git(root, 'rev-parse', 'HEAD').stdout.strip()


def vercel_token():
    candidates = []
    for key in ('APPDATA', 'LOCALAPPDATA'):
        if os.environ.get(key):
            candidates.append(Path(os.environ[key]) / 'com.vercel.cli' / 'Data' / 'auth.json')
            candidates.append(Path(os.environ[key]) / 'com.vercel.cli' / 'auth.json')
    if os.environ.get('APPDATA'):
        candidates.append(Path(os.environ['APPDATA']) / 'xdg.data/com.vercel.cli/auth.json')
    candidates += [Path.home() / '.local/share/com.vercel.cli/auth.json',
                   Path.home() / '.config/com.vercel.cli/auth.json']
    for path in candidates:
        if path.is_file():
            token = json.loads(path.read_text(encoding='utf-8')).get('token')
            if token:
                return token
    raise PublishError('Geekom Vercel CLI login token not found')


def api(token, path, body=None, timeout=30):
    request = urllib.request.Request('https://api.vercel.com' + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def deploy(commit, token):
    deadline = time.monotonic() + 300
    created = api(token, '/v13/deployments?teamId=' + TEAM, {
        'name': 'apexrigor', 'project': PROJECT, 'target': 'production',
        'gitSource': {'type': 'github', 'repoId': 1234114306, 'ref': 'main', 'sha': commit}})
    deployment_id = created['id']
    # Bounded synchronous deployment readiness check, never a scheduled job.
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        info = api(token, '/v13/deployments/' + deployment_id + '?teamId=' + TEAM,
                   timeout=min(30, remaining))
        if info.get('readyState') in ('ERROR', 'CANCELED'):
            raise PublishError('deployment ' + deployment_id + ' ended ' + info['readyState'])
        if (info.get('readyState') == 'READY' and info.get('aliasAssigned')
                and 'apexrigor.com' in info.get('alias', [])):
            actual = (info.get('gitSource') or {}).get('sha') or info.get('meta', {}).get('githubCommitSha')
            if actual != commit:
                raise PublishError('deployment commit does not match pushed commit')
            return deployment_id, datetime.fromtimestamp(info['ready'] / 1000, timezone.utc).isoformat()
        time.sleep(min(5, max(0, deadline - time.monotonic())))
    raise PublishError('deployment ' + deployment_id + ' not READY with apexrigor.com alias within 5 minutes')


def readback(root, commit):
    def fetch(path):
        request = urllib.request.Request('https://apexrigor.com/' + path + '?nba_publish=' + commit,
                                         headers={'Cache-Control': 'no-cache'})
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()
    page = fetch('nba/').decode('utf-8')
    if 'NBA' not in page or 'id="games"' not in page:
        raise PublishError('production NBA page missing expected board')
    today = json.loads((root / FILES[0]).read_bytes())
    day = date.fromisoformat(today['slate_date'])
    label = (day.strftime('%A, %B ') + str(day.day) + day.strftime(', %Y')).upper()
    if label not in page or str(len(today['positions'])) + ' POSITIONS' not in page:
        raise PublishError('production NBA board does not match the new payload')
    for name in FILES:
        if json.loads(fetch(name)) != json.loads((root / name).read_bytes()):
            raise PublishError('production readback mismatch: ' + name)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date', required=True, type=date.fromisoformat)
    parser.add_argument('--checkout', required=True, type=Path)
    parser.add_argument('--branch', default='main', help='non-main branches never deploy')
    parser.add_argument('--dry-run', action='store_true', help='build and show diff; no commit, push or deploy')
    args = parser.parse_args(argv)
    result = dict(commit=None, deployment_id=None, ready_time=None)
    step = 'prepare checkout'
    try:
        root = args.checkout.resolve()
        prepare(root, args.branch)
        step = 'build NBA payloads'
        changed = build_payloads(root, args.date)
        if args.dry_run or args.branch != 'main':
            print(git(root, 'diff', '--', *FILES).stdout, file=sys.stderr, end='')
        if args.dry_run:
            result.update(status='dry_run', changed=changed,
                          commit=git(root, 'rev-parse', 'HEAD').stdout.strip())
            git(root, 'restore', '--', *FILES)
        elif not changed:
            result.update(status='unchanged', commit=git(root, 'rev-parse', 'HEAD').stdout.strip())
        else:
            # Fail before changing remote main when production credentials are missing.
            step = 'Vercel login'
            token = vercel_token() if args.branch == 'main' else None
            step = 'commit NBA payloads'
            result['commit'] = commit_payloads(root, args.date)
            step = 'push NBA payloads'
            result['commit'] = push_once_with_rebase(root, args.branch)
            if args.branch == 'main':
                step = 'deploy exact commit'
                result['deployment_id'], result['ready_time'] = deploy(result['commit'], token)
                step = 'production readback'
                readback(root, result['commit'])
                result['status'] = 'published'
            else:
                result['status'] = 'branch_only'
        print(json.dumps(result))
        return 0
    except Exception as exc:
        # Subprocess/HTTP exceptions can contain credential-bearing URLs or headers.
        message = str(exc) if isinstance(exc, PublishError) else type(exc).__name__ + ' (details withheld)'
        result.update(status='failed', step=step, error=message)
        print('NBA publish failed at ' + step + ': ' + message, file=sys.stderr)
        print(json.dumps(result))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
