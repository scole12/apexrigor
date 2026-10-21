"""Issue 31: another sport's build must not bypass a published NCAAF email check."""
import importlib.util
import os
import sys

import pytest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

SOURCE = Path(os.environ.get("PUBLISHER_SOURCE", str(Path(__file__).resolve().parents[1] / "bin/apex_shared_site_publisher.py")))
spec = importlib.util.spec_from_file_location("issue31_publisher", SOURCE)
publisher = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = publisher
spec.loader.exec_module(publisher)


@pytest.mark.parametrize("proof_kind", ["absent", "wrong-request"])
def test_new_or_mismatched_request_still_waits_during_unrelated_build(tmp_path, monkeypatch, proof_kind):
    p = publisher
    request = p.Request(
        "NCAAF", "a" * 64,
        {"requested_at_utc": "2026-10-21T21:57:00Z"},
        tmp_path / "payload", "2026-10-21", "T2",
    )
    monkeypatch.setattr(p, "STATE_ROOT", tmp_path / "state")
    monkeypatch.setattr(p, "LOCK_PATH", tmp_path / "publisher.lock")
    monkeypatch.setattr(p, "ROOT", tmp_path / "site")
    monkeypatch.setattr(p, "_catch_up_vercel", Mock())
    monkeypatch.setattr(p, "deploy_check", lambda: {"status": "CURRENT"})
    monkeypatch.setattr(p, "prepare_due_ncaaf_records", lambda: [])
    monkeypatch.setattr(p, "discover_isolated", lambda: [request])
    monkeypatch.setattr(p, "_production_build_in_flight", lambda: True)
    monkeypatch.setattr(p, "failure_counts", lambda request: (0, 0))
    monkeypatch.setattr(p, "hourly_cleanup", lambda pending: {})
    monkeypatch.setattr(p, "owner_notice", Mock())
    monkeypatch.setattr(p.subprocess, "run", lambda *a, **kw: SimpleNamespace(stdout="", returncode=0))
    # This request's immutable payload is already on main; a newer other-sport build is running.
    published = {
        "status": "PUBLISHED_NO_CONTENT_CHANGE",
        "sport": "NCAAF", "request_id": request.request_id,
        "published_commit": "b" * 40, "changed_paths": [],
    }
    if proof_kind != "absent":
        p.atomic_json(p.ncaaf_site_wait_path(request), {
            "request_id": request.request_id if proof_kind == "matching" else "c" * 64,
            "request_commit": published["published_commit"],
            "first_wait_utc_ms": 1,
        })
    monkeypatch.setattr(p, "publish", Mock(return_value=published))
    check = Mock(return_value={**published, "site_live_check": {"status": "EMAIL_SENT_AFTER_BOUNDED_SITE_WAIT"}})
    monkeypatch.setattr(p, "ncaaf_t2_site_live_before_email", check)
    send = Mock(return_value={**published, "status": "PUBLISHED_EMAIL_VERIFIED"})
    monkeypatch.setattr(p, "dispatch_ncaaf_email", send)

    outcome = p.execute(dry_run=False)

    assert check.call_count == 0
    assert send.call_count == 0
    assert p.publish.call_count == 0
    assert outcome["requests"][0]["status"] == "WAITING_FOR_DEPLOYMENT"


def test_publisher_failure_notice_logs_without_email(monkeypatch, capsys):
    spawned = []
    monkeypatch.setattr(publisher.subprocess, "run", lambda argv, **kw: spawned.append(argv))
    publisher.owner_notice("publisher-fail:fixture", "Publish failed fixture", "Fixture failure detail")
    assert not any("apex_notify.py" in str(argv) for argv in spawned), (
        "Publisher failure notice still invokes the live SendGrid alert dispatcher"
    )
    captured = capsys.readouterr()
    recorded = captured.out + captured.err + repr(spawned)
    assert "Publish failed fixture" in recorded


@pytest.mark.parametrize("content_state", ["unchanged", "unpublished", "tampered"])
def test_email_resume_cannot_commit_push_or_send_unpublished_content(tmp_path, monkeypatch, content_state):
    """Exercise the actual publication/resume code against a local bare Git remote."""
    import hashlib
    import subprocess

    p = publisher
    remote, checkout = tmp_path / "remote.git", tmp_path / "site"
    payload = tmp_path / "payload"
    relative = "data/ncaaf_today.json"
    original = b'{"games": [{"id": "fixture-game"}]}\n'
    next_content = original if content_state == "unchanged" else b'{"games": [{"id": "unpublished-game"}]}\n'

    def local_git(*args, cwd=tmp_path):
        completed = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
        return completed.stdout.rstrip("\r\n")

    local_git("init", "--bare", "--initial-branch=main", str(remote))
    local_git("clone", str(remote), str(checkout))
    local_git("config", "user.name", "Issue31 fixture", cwd=checkout)
    local_git("config", "user.email", "fixture@example.invalid", cwd=checkout)
    target = checkout / relative
    target.parent.mkdir(parents=True)
    target.write_bytes(original)
    delivery = checkout / "data/ncaaf/2026-10-21/full_slate_delivery_manifest.json"
    delivery.parent.mkdir(parents=True)
    import json
    delivery.write_text(json.dumps({"queue_request_id": "e" * 64, "delivery_product": "T2", "slate_date": "2026-10-21"}))
    local_git("add", ".", cwd=checkout)
    local_git("commit", "-m", "Already published NCAAF fixture", cwd=checkout)
    local_git("push", "-u", "origin", "main", cwd=checkout)
    commit = local_git("rev-parse", "HEAD", cwd=checkout)
    (checkout / "untracked-work.txt").write_text("preserve this local work")
    before_status = local_git("status", "--porcelain", cwd=checkout)
    path = payload / relative
    path.parent.mkdir(parents=True)
    path.write_bytes(next_content)
    expected_hash = hashlib.sha256(next_content).hexdigest()
    request = p.Request("NCAAF", "e" * 64, {"source_hashes": {relative: expected_hash}},
                        payload, "2026-10-21", "T2")
    if content_state == "tampered":
        path.write_bytes(b"payload modified after freezing")

    monkeypatch.setattr(p, "STATE_ROOT", tmp_path / "state")
    monkeypatch.setattr(p, "LOCK_PATH", tmp_path / "publisher.lock")
    monkeypatch.setattr(p, "ROOT", checkout)
    monkeypatch.setattr(p, "CANONICAL_REMOTE", str(remote))
    monkeypatch.setattr(p, "_catch_up_vercel", lambda commit: None)
    monkeypatch.setattr(p, "deploy_check", lambda: {"status": "CURRENT"})
    monkeypatch.setattr(p, "prepare_due_ncaaf_records", lambda: [])
    monkeypatch.setattr(p, "discover_isolated", lambda: [request])
    monkeypatch.setattr(p, "_production_build_in_flight", lambda: True)
    monkeypatch.setattr(p, "failure_counts", lambda request: (0, 0))
    monkeypatch.setattr(p, "global_failure_count", lambda request: 0)
    monkeypatch.setattr(p, "hourly_cleanup", lambda pending: {})
    monkeypatch.setattr(p, "owner_notice", lambda *a: None)
    git_commands = []

    def bound_git(*args, cwd=None, timeout=180):
        git_commands.append(args)
        if args and args[0] in {"push", "commit", "add"}:
            raise AssertionError("Email resume attempted a mutating publication command: " + repr(args))
        return local_git(*args, cwd=cwd or checkout)

    monkeypatch.setattr(p, "git", bound_git)
    actual_commit_contains = p.commit_contains
    monkeypatch.setattr(p, "commit_contains", lambda deployed, published: actual_commit_contains(deployed, published, repo=checkout))

    def build(request, worktree):
        # Stand-in renderer validates frozen payload bytes before staging its own sport content.
        p.validate_payload_set(request)
        output = worktree / relative
        changed = output.read_bytes() != path.read_bytes()
        if changed:
            output.write_bytes(path.read_bytes())
        return {"changed_paths": [relative] if changed else [], "audit_tail": "fixture"}

    monkeypatch.setattr(p, "build_request", build)
    check = Mock(side_effect=lambda req, result: {**result, "site_live_check": {"status": "SITE_LIVE_BEFORE_EMAIL"}})
    send = Mock(side_effect=lambda req, result: {**result, "status": "PUBLISHED_EMAIL_VERIFIED"})
    monkeypatch.setattr(p, "ncaaf_t2_site_live_before_email", check)
    monkeypatch.setattr(p, "dispatch_ncaaf_email", send)
    p.atomic_json(p.ncaaf_site_wait_path(request), {
        "request_id": request.request_id, "request_commit": commit, "first_wait_utc_ms": 1,
    })

    p.execute(dry_run=False)

    assert send.call_count == (1 if content_state == "unchanged" else 0)
    assert not any(args[0] in {"push", "commit", "add"} for args in git_commands)
    assert local_git("--git-dir=" + str(remote), "rev-parse", "main") == commit
    assert local_git("rev-parse", "HEAD", cwd=checkout) == commit
    assert local_git("status", "--porcelain", cwd=checkout) == before_status
    assert target.read_bytes() == original
