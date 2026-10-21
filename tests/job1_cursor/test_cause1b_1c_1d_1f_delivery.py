"""#23 causes 1b, 1c, 1d and 1f in the shared publisher.

1b: the T-2 email waited (almost daily) for a deploy of the newest origin/main, which other
    sports' pushes kept superseding (DEPLOYMENT_NOT_REQUEST_DESCENDANT).
1c: one sport's fault (Oct 20 NBA unowned paths) stopped NCAAF for 24 h through the 10-failure cap.
1d: re-issued requests blocked email (NCAA_EMAIL_RECONCILIATION_REQUIRED, Oct 8-10), a deploy skew
    raised AttributeError 'delivery_lock' (Oct 7), and a push race was rejected (Oct 9).
1f: /opt/apex_site ran a publisher 25 commits behind origin/main.
"""
import json
import types
from pathlib import Path

import pytest

import pubsupport
from pubsupport import commit_all, deployment, git, init_repo, write_json

KICK = 1792537200000                     # 2026-10-20 19:00 ET first kickoff
T2_REQUESTED = "2026-10-20T21:00:30Z"     # 17:00 ET


@pytest.fixture
def publisher(tmp_path, monkeypatch):
    p = pubsupport.load_publisher()
    monkeypatch.setattr(p, "STATE_ROOT", tmp_path / "state")
    monkeypatch.setattr(p, "LOCK_PATH", tmp_path / "publisher.lock")
    monkeypatch.setattr(p, "NCAAF_QUEUE", tmp_path / "queue")
    notices = []
    monkeypatch.setattr(p, "owner_notice", lambda key, subject, body: notices.append((key, subject)))
    monkeypatch.setattr(p, "_catch_up_vercel", lambda commit: None)
    p.notices = notices
    return p


# --- 1b: the T-2 email waits for the request's commit, and not forever ---------------------------
@pytest.fixture
def history(tmp_path):
    """origin/main: A = this NCAAF request, B = a later NHL push (A is an ancestor of B)."""
    repo = init_repo(tmp_path / "site")
    write_json(repo / "data/nhl_today.json", {"v": 0})
    write_json(repo / "data/ncaaf_today.json", {"v": 0})
    commit_all(repo, "base")
    write_json(repo / "data/ncaaf_today.json", {"v": 1})
    a = commit_all(repo, "Publish NCAAF production state")
    write_json(repo / "data/nhl_today.json", {"v": 2})
    b = commit_all(repo, "Publish NHL sealed production state")
    return repo, a, b


def t2(p, tmp_path, source_hashes=None):
    payload = tmp_path / "payload"
    write_json(payload / "data/ncaaf_today.json", {"games": [{"kickoff_utc_ms": KICK}]})
    manifest = {"requested_at_utc": T2_REQUESTED,
                "source_hashes": source_hashes or {"data/ncaaf_today.json": "0" * 64}}
    return p.Request("NCAAF", "a" * 64, manifest, payload, "2026-10-20", "T2")


def test_retry_after_other_sport_push_accepts_deploy_that_contains_the_request(publisher, history, tmp_path, monkeypatch):
    repo, a, b = history
    monkeypatch.setattr(publisher, "ROOT", repo)
    monkeypatch.setattr(publisher, "vercel_deployment", lambda: deployment(a))
    # Retry: nothing left to commit, origin/main has moved on to the NHL push B (not deployed yet).
    out = publisher.ncaaf_t2_site_live_before_email(
        t2(publisher, tmp_path), {"status": "PUBLISHED_NO_CONTENT_CHANGE", "published_commit": b},
        now_ms=KICK - 7000000, poll_seconds=0)
    assert out["site_live_check"]["status"] == "SITE_LIVE_BEFORE_EMAIL"
    assert out["site_live_check"]["published_commit"] == a


def test_later_other_sport_deploy_does_not_serve_the_ncaaf_publish(publisher, history, tmp_path, monkeypatch):
    repo, a, b = history
    monkeypatch.setattr(publisher, "ROOT", repo)
    monkeypatch.setattr(publisher, "vercel_deployment", lambda: deployment(b))
    with pytest.raises(RuntimeError, match="DEPLOYMENT_NOT_REQUEST_DESCENDANT"):
        publisher.ncaaf_t2_site_live_before_email(
            t2(publisher, tmp_path), {"status": "PUBLISHED", "published_commit": a},
            now_ms=KICK - 7000000, poll_seconds=0)


def test_site_wait_is_bounded_without_alert_when_production_is_ready(publisher, history, tmp_path, monkeypatch):
    repo, a, b = history
    monkeypatch.setattr(publisher, "ROOT", repo)
    monkeypatch.setattr(publisher, "receipt_path", lambda request: tmp_path / "receipts" / "r.json")
    base = git("rev-list", "--max-parents=0", "HEAD", cwd=repo)
    monkeypatch.setattr(publisher, "vercel_deployment", lambda: deployment(base))   # READY, not ERROR
    request = t2(publisher, tmp_path)
    first = KICK - 7200000
    with pytest.raises(RuntimeError) as waiting:
        publisher.ncaaf_t2_site_live_before_email(request, {"status": "PUBLISHED", "published_commit": a},
                                                  now_ms=first, poll_seconds=0)
    assert publisher._is_wait_error(str(waiting.value))
    with pytest.raises(RuntimeError):
        publisher.ncaaf_t2_site_live_before_email(request, {"status": "PUBLISHED_NO_CONTENT_CHANGE", "published_commit": b},
                                                  now_ms=first + 19 * 60000, poll_seconds=0)
    out = publisher.ncaaf_t2_site_live_before_email(request, {"status": "PUBLISHED_NO_CONTENT_CHANGE", "published_commit": b},
                                                    now_ms=first + 20 * 60000, poll_seconds=0)
    assert out["site_live_check"]["status"] == "EMAIL_SENT_AFTER_BOUNDED_SITE_WAIT"
    assert out["site_live_check"]["published_commit"] == a
    assert publisher.notices == []


def test_deployed_commit_missing_locally_is_fetched_not_read_as_not_descendant(tmp_path):
    p = pubsupport.load_publisher()
    origin = init_repo(tmp_path / "origin")
    write_json(origin / "x.json", {"v": 1})
    a = commit_all(origin, "a")
    clone = tmp_path / "clone"
    git("clone", "-q", str(origin), str(clone), cwd=tmp_path)
    write_json(origin / "x.json", {"v": 2})
    later = commit_all(origin, "later push the clone has not fetched")
    assert p.commit_contains(later, a, repo=clone) is True


# --- 1c: only the request's own failures count toward the daily cap -----------------------------
def run_execute(p, monkeypatch, error, times):
    request = p.Request("NCAAF", "b" * 64, {"requested_at_utc": T2_REQUESTED}, None, "2026-10-20", "T2")
    calls = []

    def publish(req, dry_run):
        calls.append(1)
        raise error
    monkeypatch.setattr(p, "discover_isolated", lambda: [request])
    monkeypatch.setattr(p, "publish", publish)
    monkeypatch.setattr(p, "prepare_due_ncaaf_records", lambda: [])
    monkeypatch.setattr(p, "deploy_check", lambda: {"status": "CURRENT"})
    monkeypatch.setattr(p, "hourly_cleanup", lambda pending: {})
    monkeypatch.setattr(p.subprocess, "run", lambda *a, **k: types.SimpleNamespace(stdout="", returncode=0))
    results = [p.execute(dry_run=False) for _ in range(times)]
    return calls, results


def test_other_sport_fault_never_stops_ncaaf(publisher, monkeypatch):
    error = RuntimeError("shared publisher produced unowned paths: ['nba/about/index.html', 'nba/index.html', 'nba/results/index.html']")
    calls, results = run_execute(publisher, monkeypatch, error, 12)
    assert len(calls) == 12
    assert results[-1]["requests"][0]["status"] == "BLOCKED_BY_GLOBAL_FAULT"
    assert results[-1]["hard_failure_count"] == 0
    assert [k for k, _ in publisher.notices].count("publisher-global:" + "b" * 64) == 1


def test_push_race_is_not_the_requests_fault(publisher, monkeypatch):
    error = RuntimeError("command failed (1): git push origin HEAD:main: ! [rejected] HEAD -> main (fetch first)")
    calls, results = run_execute(publisher, monkeypatch, error, 11)
    assert len(calls) == 11 and results[-1]["requests"][0]["fault_scope"] == "GLOBAL"


def test_request_own_fault_still_stops_after_ten(publisher, monkeypatch):
    calls, results = run_execute(publisher, monkeypatch, RuntimeError("queued payload hash mismatch: data/ncaaf_today.json"), 11)
    assert len(calls) == 10
    assert results[-1]["requests"][0]["status"] == "SKIPPED_AFTER_REPEATED_FAILURES"


def test_rejected_push_raises_a_global_fault(tmp_path, monkeypatch):
    p = pubsupport.load_publisher()
    remote = tmp_path / "remote.git"
    git("init", "-q", "--bare", "-b", "main", str(remote), cwd=tmp_path)
    checkout = init_repo(tmp_path / "checkout")
    write_json(checkout / "data/ncaaf_today.json", {"v": 0})
    commit_all(checkout, "base")
    git("remote", "add", "origin", str(remote), cwd=checkout)
    git("push", "-q", "-u", "origin", "main", cwd=checkout)
    other = tmp_path / "other"
    git("clone", "-q", str(remote), str(other), cwd=tmp_path)
    git("config", "user.email", "o@example.invalid", cwd=other)
    git("config", "user.name", "o", cwd=other)

    def build(request, worktree):
        write_json(worktree / "data/ncaaf_today.json", {"v": 1})
        # Another sport pushes while this request builds.
        write_json(other / "data/nhl_today.json", {"v": 1})
        commit_all(other, "NHL")
        git("push", "-q", "origin", "main", cwd=other)
        return {"changed_paths": ["data/ncaaf_today.json"], "audit_tail": "ok"}

    def bound_git(*args, cwd=None, timeout=180):
        return p.run(["git", *args], cwd=cwd or checkout, timeout=timeout)
    monkeypatch.setattr(p, "ROOT", checkout)
    monkeypatch.setattr(p, "CANONICAL_REMOTE", str(remote))
    monkeypatch.setattr(p, "STATE_ROOT", tmp_path / "state")
    monkeypatch.setattr(p, "git", bound_git)
    monkeypatch.setattr(p, "build_request", build)
    request = p.Request("NCAAF", "c" * 64, {}, None, "2026-10-20", "T3")
    with pytest.raises(p.GlobalPublicationFault, match="PUSH_RACE"):
        p.publish(request, dry_run=False)


# --- 1d: email supersede rule and interface pin -------------------------------------------------
OLD, NEW = "1" * 64, "2" * 64


def queue(p, tmp_path, current):
    root = p.NCAAF_QUEUE / "2026-10-09" / "T3"
    for request_id in (OLD, NEW):
        (root / request_id).mkdir(parents=True, exist_ok=True)
    write_json(root / "current.json", {"request_id": current})


def runs(p, monkeypatch, rows):
    page = {"total_count": len(rows), "workflow_runs": [
        {"id": i + 1, "display_title": f"NCAA T3 2026-10-09 {rid}", "status": status, "conclusion": "success",
         "html_url": "u", "head_sha": "h", "run_attempt": 1} for i, (rid, status) in enumerate(rows)]}
    monkeypatch.setattr(p, "run", lambda command, cwd, timeout=180: json.dumps(page))


def request_t3(p, request_id):
    return p.Request("NCAAF", request_id, {"requested_at_utc": "2026-10-09T13:00:00Z"}, None, "2026-10-09", "T3")


def test_reissued_request_is_not_blocked_by_the_superseded_requests_finished_run(publisher, tmp_path, monkeypatch):
    queue(publisher, tmp_path, current=NEW)
    runs(publisher, monkeypatch, [(OLD, "completed")])
    assert publisher.matching_ncaaf_workflow_runs(request_t3(publisher, NEW)) == []


def test_superseded_run_still_in_progress_keeps_blocking(publisher, tmp_path, monkeypatch):
    queue(publisher, tmp_path, current=NEW)
    runs(publisher, monkeypatch, [(OLD, "in_progress")])
    with pytest.raises(RuntimeError, match="NCAA_EMAIL_RECONCILIATION_REQUIRED"):
        publisher.matching_ncaaf_workflow_runs(request_t3(publisher, NEW))


def test_a_request_that_is_not_current_supersedes_nothing(publisher, tmp_path, monkeypatch):
    queue(publisher, tmp_path, current=OLD)
    runs(publisher, monkeypatch, [(OLD, "completed")])
    with pytest.raises(RuntimeError, match="NCAA_EMAIL_RECONCILIATION_REQUIRED"):
        publisher.matching_ncaaf_workflow_runs(request_t3(publisher, NEW))


def test_superseded_request_whose_email_was_delivered_keeps_blocking(publisher, tmp_path, monkeypatch):
    queue(publisher, tmp_path, current=NEW)
    runs(publisher, monkeypatch, [(OLD, "completed")])
    old = publisher.Request("NCAAF", OLD, {}, None, "2026-10-09", "T3")
    write_json(publisher.receipt_path(old), {"status": "PUBLISHED_EMAIL_VERIFIED", "email_external_action_count": 1})
    with pytest.raises(RuntimeError, match="NCAA_EMAIL_RECONCILIATION_REQUIRED"):
        publisher.matching_ncaaf_workflow_runs(request_t3(publisher, NEW))


def test_email_workflow_is_read_not_waited_on_inside_the_shared_lock(publisher, monkeypatch):
    monkeypatch.setattr(publisher, "matching_ncaaf_workflow_runs",
                        lambda request: [{"databaseId": 5, "status": "in_progress", "conclusion": None}])
    monkeypatch.setattr(publisher.time, "sleep", lambda seconds: pytest.fail("slept inside the publisher lock"))
    with pytest.raises(RuntimeError) as caught:
        publisher.wait_for_ncaaf_workflow(request_t3(publisher, NEW), 5)
    assert "NCAA_EMAIL_WORKFLOW_PENDING" in str(caught.value) and publisher._is_wait_error(str(caught.value))


def test_dispatched_run_not_listed_yet_waits_and_is_never_resent(publisher, monkeypatch):
    from datetime import datetime, timezone
    request = request_t3(publisher, NEW)
    write_json(publisher.receipt_path(request), {"status": "PUBLISHED_EMAIL_DISPATCH_INTENT",
                                                 "email_dispatch_at_utc": datetime.now(timezone.utc).isoformat()})
    commands = []
    monkeypatch.setattr(publisher, "matching_ncaaf_workflow_runs", lambda request: [])
    monkeypatch.setattr(publisher, "run", lambda command, cwd=None, timeout=180: commands.append(command) or "")
    with pytest.raises(RuntimeError) as caught:
        publisher.dispatch_ncaaf_email(request, {"status": "PUBLISHED"})
    assert publisher._is_wait_error(str(caught.value))
    assert not any(command[:3] == ["gh", "workflow", "run"] for command in commands)


def results_email_module(**attributes):
    module = types.ModuleType("ncaaf_results_email")
    module.__dict__.update(attributes)
    return module


def test_results_email_interface_skew_is_a_named_global_fault(publisher, monkeypatch):
    request = publisher.Request("NCAAF", "d" * 64, {}, None, "2026-10-07", "RESULTS")
    monkeypatch.setitem(__import__("sys").modules, "ncaaf_results_email",
                        results_email_module(INTERFACE_VERSION="apex.ncaaf.results_email.v2", confirmed_email=lambda *a, **k: None))
    with pytest.raises(publisher.GlobalPublicationFault, match="NCAAF_EMAIL_INTERFACE_MISMATCH.*delivery_lock"):
        publisher.dispatch_ncaaf_email(request, {"status": "PUBLISHED"})
    old = results_email_module(INTERFACE_VERSION="apex.ncaaf.results_email.v1", delivery_lock=lambda d: None,
                               confirmed_email=lambda *a, **k: None)
    with pytest.raises(publisher.GlobalPublicationFault, match="v1"):
        publisher.require_results_email_interface(old)
    publisher.require_results_email_interface(results_email_module(delivery_lock=lambda d: None, confirmed_email=lambda *a: None))


# --- 1f: stale publisher deploy is reported -----------------------------------------------------
def test_deploy_check_reports_a_publisher_behind_origin_main(tmp_path):
    remote = tmp_path / "remote.git"
    git("init", "-q", "--bare", "-b", "main", str(remote), cwd=tmp_path)
    upstream = init_repo(tmp_path / "upstream")
    (upstream / "bin").mkdir()
    (upstream / "bin/apex_shared_site_publisher.py").write_bytes(pubsupport.PUBLISHER.read_bytes())
    (upstream / "bin/site_route_owners.py").write_bytes((pubsupport.BIN / "site_route_owners.py").read_bytes())
    commit_all(upstream, "publisher")
    git("remote", "add", "origin", str(remote), cwd=upstream)
    git("push", "-q", "-u", "origin", "main", cwd=upstream)
    droplet = tmp_path / "opt_apex_site"
    git("clone", "-q", str(remote), str(droplet), cwd=tmp_path)
    p = pubsupport.load_publisher(droplet / "bin/apex_shared_site_publisher.py")
    assert p.deploy_check(droplet)["status"] == "CURRENT"
    write_json(droplet / "data/mlb_today.json", {"local": True})          # uncommitted live data
    with (upstream / "bin/apex_shared_site_publisher.py").open("a") as handle:
        handle.write("\n# reviewed fix merged on main\n")
    commit_all(upstream, "fix")
    git("push", "-q", "origin", "main", cwd=upstream)
    git("fetch", "-q", "origin", cwd=droplet)
    report = p.deploy_check(droplet)
    assert report["status"] == "STALE" and report["publisher_matches_origin_main"] is False
    assert report["commits_behind_origin_main"] == 1
    assert "data/mlb_today.json" in report["dirty_data_paths"]


def test_site_build_failure_already_on_main_does_not_block_the_request(publisher, tmp_path, monkeypatch):
    worktree = init_repo(tmp_path / "wt" / "site")
    write_json(worktree / "bin/placeholder.json", {})
    commit_all(worktree, "base")

    def tool(root, name, *args):
        raise RuntimeError(f"command failed (1): {root}/bin/{name}: audit: /nfl missing route")
    monkeypatch.setattr(publisher, "python_tool", tool)
    assert "PREEXISTING_SITE_BUILD_FAILURE_ON_MAIN" in publisher.validate_site_build(worktree)


def test_site_build_failure_caused_by_the_request_fails_closed(publisher, tmp_path, monkeypatch):
    worktree = init_repo(tmp_path / "wt" / "site")
    write_json(worktree / "bin/placeholder.json", {})
    commit_all(worktree, "base")

    def tool(root, name, *args):
        if Path(root).name == "site":
            raise RuntimeError("command failed (1): audit: /ncaaf missing sport selector")
        return "PASS"
    monkeypatch.setattr(publisher, "python_tool", tool)
    with pytest.raises(RuntimeError) as caught:
        publisher.validate_site_build(worktree)
    assert not isinstance(caught.value, publisher.GlobalPublicationFault)
    assert not publisher._is_global_fault(str(caught.value))
