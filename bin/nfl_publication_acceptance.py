"""Read the existing exact-stage acceptance authority; never arm or send email."""
import hashlib
import json
from pathlib import Path

SCOPE = Path('/var/opt/apex_nfl/production/stage_delivery/sunday-20260913-scope.json')
COHORTS = Path('/var/opt/apex_nfl/state/cohorts')
ISSUANCES = Path('/var/opt/apex_nfl/issuance')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def receipt_bound_issuance(path, receipt, receipt_sha256, issuance_path=None):
    """Validate the existing canonical bytes derived from a Grok-bound T2.

    This is read-only compatibility with receipt-only scopes, not a new
    acceptance or issuance. Keep this projection identical to cohort_runtime's
    sealed_issuance.v2 writer, including its canonical JSON encoding.
    """
    def canonical(value):
        return json.dumps(value, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=False, allow_nan=False).encode('utf-8')
    identity = {key: receipt[key] for key in
                ('cohort_id', 'release_id', 'release_manifest_sha256', 'positions')}
    identity.update(t2_receipt_sha256=receipt_sha256,
                    ruleset_sha256=receipt['settlement_ruleset_sha256'])
    issuance_id = hashlib.sha256(canonical(identity)).hexdigest()
    bound = ISSUANCES.resolve() / (issuance_id + '.json')
    if bound.resolve() != bound or (issuance_path is not None and Path(issuance_path).resolve() != bound):
        return False
    expected = {key: receipt[key] for key in (
        'cohort_id', 'game_ids', 'kickoff_ts', 'release_id', 'release_manifest_path',
        'release_manifest_sha256', 'settlement_ruleset_id', 'settlement_ruleset_path',
        'settlement_ruleset_sha256', 't3_receipt_path', 't3_receipt_sha256', 'positions')}
    expected.update(schema='apex.nfl.sealed_issuance.v2', issuance_id=issuance_id,
                    issued_at=receipt['sealed_at'], t2_receipt_path=str(path),
                    t2_receipt_sha256=receipt_sha256)
    if not isinstance(expected['positions'], list) or not expected['positions'] or receipt.get('official_position_count') != len(expected['positions']):
        return False
    for prefix in ('release_manifest', 'settlement_ruleset', 't3_receipt'):
        if sha(expected[prefix + '_path']) != expected[prefix + '_sha256']:
            return False
    # Equality to the receipt-derived serialization rejects even whitespace
    # drift, extra fields or a changed canonical ID without a scope hash for it.
    return bound.read_bytes() == canonical(expected) + b'\n'


def accepted_stage(path, issuance_path=None):
    """Publication acceptance persists after the email arming window expires."""
    try:
        path = Path(path).resolve()
        path.relative_to(COHORTS.resolve())
        if scheduled_accepted_stage(path, issuance_path):
            return True
        policy = json.loads(SCOPE.read_text())
        receipt = json.loads(path.read_text())
        stage = receipt.get('stage')
        binding = policy.get('accepted_stages', {}).get(stage, {})
        if not (
            policy.get('schema') == 'apex.nfl.exact_stage_delivery_scope.v1'
            and stage in {'T3', 'T2'}
            and receipt.get('schema') == 'apex.nfl.cohort_' + stage.lower() + '_receipt.v2'
            and receipt.get('status') == 'PASS'
            and not receipt.get('preview_only') and not receipt.get('diagnostic_not_issuance')
            and receipt.get('cohort_id') == policy.get('cohort_id') == path.parent.name
            and path.name == stage + '.json'
            and receipt.get('game_ids') == policy.get('game_ids')
            and binding.get('receipt_path') == str(path)
            and binding.get('receipt_sha256') == sha(path)
            and binding.get('reviewer') == 'Grok' and binding.get('verdict') == 'PASS'
        ):
            return False
        if stage == 'T3':
            return issuance_path is None
        issuance_fields = {'issuance_path', 'issuance_id', 'issuance_sha256'}
        if not issuance_fields.intersection(binding):
            return (receipt.get('release_id') == policy.get('release_id')
                    and receipt_bound_issuance(path, receipt, binding['receipt_sha256'], issuance_path))
        # Partial or invalid explicit bindings never fall back to receipt-only.
        bound = Path(binding.get('issuance_path', '')).resolve()
        bound.relative_to(ISSUANCES.resolve())
        if issuance_path is not None and Path(issuance_path).resolve() != bound:
            return False
        issuance = json.loads(bound.read_text())
        return (
            issuance.get('schema') == 'apex.nfl.sealed_issuance.v2'
            and bound.name == str(issuance.get('issuance_id')) + '.json'
            and binding.get('issuance_id') == issuance.get('issuance_id')
            and binding.get('issuance_sha256') == sha(bound)
            and issuance.get('t2_receipt_path') == str(path)
            and issuance.get('t2_receipt_sha256') == sha(path)
            and issuance.get('cohort_id') == receipt.get('cohort_id')
            and issuance.get('release_id') == receipt.get('release_id') == policy.get('release_id')
            and issuance.get('release_manifest_sha256') == receipt.get('release_manifest_sha256')
            and issuance.get('game_ids') == receipt.get('game_ids')
            and issuance.get('issued_at') == receipt.get('sealed_at')
            and issuance.get('positions') == receipt.get('positions')
            and receipt.get('official_position_count') == len(issuance.get('positions', []))
        )
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return False


def accepted_issuance(path, payload):
    try:
        if json.loads(Path(path).read_text()) != payload:
            return False
    except (OSError, ValueError, TypeError):
        return False
    # Exact preexisting September 10 history is carried forward, not newly accepted.
    # No other v2 issuance can use this compatibility exception.
    if Path(path).name == '00f8e3ae8d6dde39b7503e61e1829538eb1b3614e653e17ffafc5300a97bc243.json' and sha(path) == '88ebc8aefea0bc19f4eb2fc980ebd4272d4ad7a063f8081f31011de703f2ec23':
        return True
    # Preserve independently verified historical published-card import handling.
    if payload.get('schema') == 'apex.nfl.published_card_issuance.v1':
        return True
    return accepted_stage(payload.get('t2_receipt_path', ''), path)


def scheduled_accepted_stage(path, issuance_path=None):
    """Read exact deterministic acceptance written by the reviewed NFL workflow."""
    try:
        import os
        root = Path('/var/opt/apex_nfl/production/stage_delivery')
        receipt = json.loads(path.read_text())
        stage = receipt['stage']
        if stage not in ('T3','T2'):
            return False
        event = hashlib.sha256(f'{stage}:{path}'.encode()).hexdigest()
        output = root / event
        acceptance = json.loads((output / 'ACCEPTANCE.json').read_text())
        policy_path = Path(os.environ.get('APEX_NFL_WORKFLOW_POLICY', str(root/'scheduled-delivery.json')))
        policy = json.loads(policy_path.read_text())
        if not (policy.get('enabled') is True and acceptance.get('schema') == 'apex.nfl.scheduled_stage_acceptance.v1'
                and acceptance['status'] == 'PASS' and acceptance['receipt_path'] == str(path)
                and acceptance['receipt_sha256'] == sha(path) and acceptance['policy_sha256'] == sha(policy_path)
                and receipt.get('status') == 'PASS' and not receipt.get('preview_only')
                and not receipt.get('diagnostic_not_issuance') and path.name == stage+'.json'
                and path.parent.name == receipt['cohort_id']):
            return False
        for name, expected in acceptance['product_files'].items():
            if Path(name).name != name or sha(output/name) != expected:
                return False
        if stage == 'T3':
            return issuance_path is None
        bound = Path(acceptance['issuance_path']).resolve()
        bound.relative_to(ISSUANCES.resolve())
        if issuance_path is not None and Path(issuance_path).resolve() != bound:
            return False
        issuance = json.loads(bound.read_text())
        return (sha(bound) == acceptance['issuance_sha256'] and bound.stem == issuance['issuance_id']
                == acceptance['issuance_id'] and issuance['t2_receipt_sha256'] == sha(path)
                and issuance['t2_receipt_path'] == str(path) and issuance['positions'] == receipt['positions'])
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return False
