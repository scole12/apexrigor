"""Deploy a pushed apexrigor commit that Vercel never started building.

Measured 2026-10-01: GitHub main 0ee9f75 (NHL T-2, 17:00:20 ET) got no Vercel
deployment at all, so the live site kept the 07:00 board and the NHL post step
failed 3 times waiting for it. 3 of 196 commits since 2026-09-24 had no
deployment. This asks Vercel to build that exact commit, once, after it has
been missing for at least 2 minutes. It never edits files, never pushes, and
never deploys anything other than the commit already on GitHub main.
"""
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

PROJECT = 'prj_eZTtqClkwx7IcE7NhVAK6UFmBnnB'
TEAM = 'team_ZbMl7Z31fLqnzoCYHAY2a1rk'
REPO_ID = 1234114306
AUTH = Path('/root/.local/share/com.vercel.cli/auth.json')
STATE = Path('/var/opt/apex_site_ops/vercel_catchup')
WAIT_SECONDS = 120  # Vercel normally starts a git build within ~10 s of a push


def _call(url, body=None):
    token = json.loads(AUTH.read_text())['token']
    request = urllib.request.Request(
        url, data=None if body is None else json.dumps(body).encode(),
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
        method='GET' if body is None else 'POST')
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def ensure_deployment(commit):
    """Return a short status dict. Safe to call on every verification retry."""
    if not isinstance(commit, str) or len(commit) != 40:
        return {'status': 'SKIPPED_BAD_COMMIT'}
    found = _call(f'https://api.vercel.com/v6/deployments?projectId={PROJECT}&teamId={TEAM}&sha={commit}&limit=5')
    live = [d for d in found.get('deployments', []) if (d.get('state') or d.get('readyState')) not in ('ERROR', 'CANCELED')]
    if live:
        return {'status': 'DEPLOYMENT_EXISTS', 'deployment_id': live[0].get('uid'), 'state': live[0].get('state')}
    STATE.mkdir(parents=True, exist_ok=True)
    marker = STATE / (commit + '.json')
    record = json.loads(marker.read_text()) if marker.exists() else {}
    now = time.time()
    if 'first_missing_at' not in record:
        record['first_missing_at'] = now
        marker.write_text(json.dumps(record, indent=2) + '\n')
        return {'status': 'MISSING_WAITING', 'seconds_missing': 0}
    if record.get('requested_deployment_id'):
        return {'status': 'ALREADY_REQUESTED', 'deployment_id': record['requested_deployment_id']}
    waited = now - record['first_missing_at']
    if waited < WAIT_SECONDS:
        return {'status': 'MISSING_WAITING', 'seconds_missing': int(waited)}
    created = _call(f'https://api.vercel.com/v13/deployments?teamId={TEAM}', {
        'name': 'apexrigor', 'project': PROJECT, 'target': 'production',
        'gitSource': {'type': 'github', 'repoId': REPO_ID, 'ref': 'main', 'sha': commit}})
    record.update(requested_deployment_id=created.get('id'), requested_at=now)
    marker.write_text(json.dumps(record, indent=2) + '\n')
    return {'status': 'DEPLOYMENT_REQUESTED', 'deployment_id': created.get('id'), 'seconds_missing': int(waited)}


if __name__ == '__main__':
    import sys
    print(json.dumps(ensure_deployment(sys.argv[1])))
