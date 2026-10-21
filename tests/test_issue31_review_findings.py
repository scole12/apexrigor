"""Independent execution of fresh Claude review reproductions for issue31."""
import json

import pytest

from tests.test_issue31_ncaaf_build_wait import publisher as p


def test_t3_retry_never_replaces_t2_delivery_manifest(tmp_path, monkeypatch):
    day = "2026-10-21"
    wt = tmp_path / "site"
    man = wt / f"data/ncaaf/{day}/full_slate_delivery_manifest.json"
    man.parent.mkdir(parents=True)
    man.write_text(json.dumps({"delivery_product": "T2", "queue_request_id": "b" * 64}))
    proof = f"data/ncaaf/{day}/T3_LIVING_HYDRATION_RECEIPT_20261021.json"
    (wt / proof).write_text(json.dumps({"status": "PASS", "request_started_at_utc_ms": 1, "captured_at_utc_ms": 2}))
    monkeypatch.setattr(p, "validate_payload_set", lambda r: {proof: "1" * 64})
    (tmp_path / "t3").mkdir()
    (tmp_path / "t3" / f"{day}.json").write_text(json.dumps({"status": "PASS", "slate_date_et": day, "nominal_t3_utc_ms": 1}))
    monkeypatch.setattr(p, "NCAAF_T3_ROOT", tmp_path / "t3")
    monkeypatch.setattr(p, "NCAAF_QUEUE", tmp_path / "q" / "publication_queue")
    manifest = dict(display_slate_date_et=day, count_scope="EXPLICIT_CANONICAL_AND_DISPLAY", display_date=day,
                    canonical_game_count=1, display_game_count=1, issued_game_count=0, official_position_count=0,
                    market_pending_game_count=0, internal_market_pending_game_count=0,
                    canonical_public_payload_sha256="c" * 64, sealed_day_payload_sha256="d" * 64)
    p.ncaaf_delivery_manifest(p.Request("NCAAF", "a" * 64, manifest, tmp_path / "payload", day, "T3"), wt)
    assert json.loads(man.read_text())["queue_request_id"] == "b" * 64


@pytest.mark.parametrize("message", [
    "RuntimeError:command failed (1): gh api --paginate repos/x/runs: HTTP 502: Bad Gateway (https://api.github.com/repos/x/runs)",
    "RuntimeError:command failed (1): gh api repos/x/runs: error connecting to api.github.com",
])
def test_gh_api_outage_is_a_global_fault(message):
    assert p._is_global_fault(message)


def test_bad_old_pointer_does_not_hide_todays_t2(tmp_path, monkeypatch, capsys):
    q = tmp_path / "q"
    monkeypatch.setattr(p, "NCAAF_QUEUE", q)
    bad = q / "2026-10-16/RESULTS/current.json"
    bad.parent.mkdir(parents=True)
    bad.write_text('{"status":"FAIL"}')
    rid = "c" * 64
    folder = q / "2026-10-21/T2" / rid
    folder.mkdir(parents=True)
    req = folder / "request.json"
    req.write_text(json.dumps(dict(sport="NCAAF", request_id=rid, slate_date_et="2026-10-21", product="T2",
                                  display_slate_date_et="2026-10-21", count_scope="EXPLICIT_CANONICAL_AND_DISPLAY")))
    (q / "2026-10-21/T2/current.json").write_text(json.dumps(dict(status="PASS",
        publication_state="QUEUED_FOR_SHARED_PUBLISHER", request_path=str(req),
        request_sha256=p.sha256_file(req), request_id=rid)))
    monkeypatch.setattr(p, "validate_payload_set", lambda r: {})
    monkeypatch.setattr(p, "is_complete", lambda r: False)
    found = p.discover_ncaaf("2026-10-21", "2026-10-20")
    assert any(r.product == "T2" and r.request_id == rid for r in found)
    assert not any(r.product == "RESULTS" and not r.manifest.get("discovery_error") for r in found)
    output = capsys.readouterr()
    reported = output.out + output.err + json.dumps([r.manifest for r in found if r.manifest.get("discovery_error")])
    assert "successful handoff" in reported


@pytest.fixture
def request_history(tmp_path, monkeypatch):
    import subprocess
    site = tmp_path / "site"
    site.mkdir()

    def git(*args):
        return subprocess.run(["git", *args], cwd=site, check=True, capture_output=True, text=True).stdout.strip()

    git("init", "-q", "-b", "main")
    git("config", "user.name", "Issue31 fixture")
    git("config", "user.email", "fixture@example.invalid")
    target = site / "data/ncaaf_today.json"
    target.parent.mkdir()
    target.write_text('{"games":[{"kickoff_utc_ms":1792537200000}]}')
    git("add", ".")
    git("commit", "-qm", "NCAAF request")
    own = git("rev-parse", "HEAD")
    (site / "data/nhl_today.json").write_text('{"fixture":1}')
    git("add", ".")
    git("commit", "-qm", "NHL later publication")
    later = git("rev-parse", "HEAD")
    remote = tmp_path / "origin.git"
    git("init", "--bare", "--initial-branch=main", str(remote))
    git("remote", "add", "origin", str(remote))
    git("push", "-u", "origin", "main")
    monkeypatch.setattr(p, "CANONICAL_REMOTE", str(remote))
    monkeypatch.setattr(p, "git", lambda *args, cwd=None, timeout=180: p.run(["git", *args], cwd=cwd or site, timeout=timeout))
    monkeypatch.setattr(p, "ROOT", site)
    monkeypatch.setattr(p, "STATE_ROOT", tmp_path / "state")
    monkeypatch.setattr(p, "_catch_up_vercel", lambda commit: None)
    request = p.Request("NCAAF", "e" * 64, {
        "requested_at_utc": "2026-10-20T21:00:30Z",
        "source_hashes": {"data/ncaaf_today.json": p.sha256_file(target)},
    }, site, "2026-10-20", "T2")
    return site, own, later, git, request


def live_deployment(commit):
    return {"readyState": "READY", "target": "production", "alias": ["apexrigor.com"],
            "url": "fixture.invalid", "meta": {"githubCommitSha": commit}}


def test_later_sport_deployment_serves_unchanged_ncaaf(request_history, monkeypatch):
    site, own, later, git, request = request_history
    monkeypatch.setattr(p, "vercel_deployment", lambda: live_deployment(later))
    out = p.ncaaf_t2_site_live_before_email(request, {"status": "PUBLISHED", "published_commit": own},
                                          now_ms=1792530200000, poll_seconds=0)
    assert out["site_live_check"]["status"] == "SITE_LIVE_BEFORE_EMAIL"


def test_descendant_with_changed_ncaaf_is_not_request_live(request_history, monkeypatch):
    site, own, later, git, request = request_history
    (site / "data/ncaaf_today.json").write_text('{"different_ncaaf_request":true}')
    git("add", ".")
    git("commit", "-qm", "Different NCAAF publication")
    changed = git("rev-parse", "HEAD")
    monkeypatch.setattr(p, "vercel_deployment", lambda: live_deployment(changed))
    with pytest.raises(RuntimeError, match="DEPLOYMENT_NOT_REQUEST_DESCENDANT"):
        p.ncaaf_t2_site_live_before_email(request, {"status": "PUBLISHED", "published_commit": own},
                                        now_ms=1792530200000, poll_seconds=0)


def test_receipt_keeps_own_commit_after_other_sport_tip(request_history, monkeypatch):
    site, own, later, git, request = request_history
    monkeypatch.setattr(p, "vercel_deployment", lambda: live_deployment(own))
    monkeypatch.setattr(p, "build_request", lambda request, worktree: {"changed_paths": []})
    before = git("rev-parse", "origin/main")
    publication = p.publish(request, dry_run=False)
    out = p.ncaaf_t2_site_live_before_email(request, publication, now_ms=1792530200000, poll_seconds=0)
    assert git("rev-parse", "origin/main") == before == later
    assert out["site_live_check"]["published_commit"] == own
    assert out["published_commit"] == own


@pytest.mark.parametrize("mode", ["queued", "manual", "legacy", "wrong-frozen-id", "unsafe-id"])
def test_workflow_reads_exact_request_manifest(tmp_path, monkeypatch, mode):
    """Execute the workflow's real manifest-selection/identity code; no mail code is run."""
    import os
    import pathlib
    import textwrap
    from datetime import datetime
    workflow = pathlib.Path(p.__file__).resolve().parents[1] / ".github/workflows/ncaaf-full-slate-delivery.yml"
    source = workflow.read_text().split("\n          else:\n", 1)[1]
    selection = textwrap.dedent(source.split("              public_sha=manifest['canonical_public_payload_sha256']", 1)[0])
    rid = "a" * 64
    root = tmp_path / "data/ncaaf/2026-10-21"
    root.mkdir(parents=True)
    shared = {"slate_date": "2026-10-21", "queue_request_id": rid if mode == "legacy" else "b" * 64, "selected": "shared"}
    (root / "full_slate_delivery_manifest.json").write_text(json.dumps(shared))
    frozen = root / "delivery" / (rid + ".json")
    frozen.parent.mkdir()
    if mode != "legacy":
        frozen.write_text(json.dumps({"slate_date": "2026-10-21", "queue_request_id": "c" * 64 if mode == "wrong-frozen-id" else rid, "selected": "frozen"}))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SLATE_DATE", "2026-10-21")
    monkeypatch.setenv("DELIVERY_MODE", "NORMAL")
    monkeypatch.setenv("PRODUCT", "T3")
    monkeypatch.setenv("REQUEST_ID", "manual" if mode == "manual" else "../outside" if mode == "unsafe-id" else rid)
    context = {"os": os, "pathlib": pathlib, "datetime": datetime, "json": json}
    if mode in {"wrong-frozen-id", "unsafe-id"}:
        with pytest.raises(AssertionError):
            exec(selection, context)
    else:
        exec(selection, context)
        assert context["manifest"]["selected"] == ("frozen" if mode == "queued" else "shared")


@pytest.mark.parametrize("error", ["HTTP 401 Unauthorized", "HTTP 403 Forbidden", "HTTP 404 Not Found", "HTTP 422 invalid payload", "queued payload hash mismatch"])
def test_request_errors_still_count_against_request(error):
    assert not p._is_global_fault(error)


def test_other_date_ncaaf_data_does_not_hold_unchanged_t2(request_history, monkeypatch):
    site, own, later, git, request = request_history
    target = site / "data/ncaaf/2026-10-19/results/fixture.json"
    target.parent.mkdir(parents=True)
    target.write_text('{"unrelated_prior_day":true}')
    git("add", ".")
    git("commit", "-qm", "Unrelated prior-day NCAAF result")
    newer = git("rev-parse", "HEAD")
    monkeypatch.setattr(p, "vercel_deployment", lambda: live_deployment(newer))
    out = p.ncaaf_t2_site_live_before_email(request, {"status": "PUBLISHED", "published_commit": own},
                                          now_ms=1792530200000, poll_seconds=0)
    assert out["site_live_check"]["status"] == "SITE_LIVE_BEFORE_EMAIL"


def test_frozen_manifest_cannot_be_overwritten(tmp_path, monkeypatch):
    day, rid = "2026-10-21", "c" * 64
    site = tmp_path / "site"
    saved = site / f"data/ncaaf/{day}/delivery/{rid}.json"
    saved.parent.mkdir(parents=True)
    before = json.dumps({"queue_request_id": rid, "slate_date": day, "delivery_product": "T2", "original_evidence": True}).encode()
    saved.write_bytes(before)
    monkeypatch.setattr(p, "validate_payload_set", lambda request: {"data/ncaaf_today.json": "1" * 64})
    manifest = {key: 1 for key in ("canonical_game_count", "display_game_count", "issued_game_count",
                                  "official_position_count", "market_pending_game_count", "internal_market_pending_game_count")}
    manifest.update(display_slate_date_et=day, count_scope="EXPLICIT_CANONICAL_AND_DISPLAY", display_date=day,
                    canonical_public_payload_sha256="1" * 64, sealed_day_payload_sha256="2" * 64)
    try:
        p.ncaaf_delivery_manifest(p.Request("NCAAF", rid, manifest, tmp_path, day, "T2"), site)
    except RuntimeError:
        pass
    assert saved.read_bytes() == before


def test_successful_push_intent_survives_post_push_fetch_failure(tmp_path, monkeypatch):
    calls = {"fetch": 0, "push": 0}
    def fake_git(*args, cwd=None, timeout=180):
        if args[0] == "remote": return p.CANONICAL_REMOTE
        if args[0] == "branch": return "main"
        if args[0] == "fetch":
            calls["fetch"] += 1
            if calls["fetch"] == 2: raise RuntimeError("fixture post-push fetch failure")
        if args[0] == "push": calls["push"] += 1
        if args[0] == "rev-parse": return "a" * 40
        if args[:2] == ("diff", "--cached"): return "data/ncaaf_today.json"
        return ""
    monkeypatch.setattr(p, "git", fake_git)
    monkeypatch.setattr(p, "STATE_ROOT", tmp_path)
    monkeypatch.setattr(p, "build_request", lambda request, site: {"changed_paths": ["data/ncaaf_today.json"]})
    request = p.Request("NCAAF", "d" * 64, {}, tmp_path, "2026-10-21", "T2")
    try:
        p.publish(request, dry_run=False)
    except RuntimeError as error:
        assert "post-push fetch failure" in str(error)
    assert calls["push"] == 1
    intent = tmp_path / "publication_intents/ncaaf" / (request.request_id + ".json")
    assert intent.is_file(), "Successful push must remain known before fallible followup reads"
    assert json.loads(intent.read_text())["published_commit"] == "a" * 40


def test_frozen_manifest_is_ncaaf_owned_and_reaches_real_local_commit(request_history, monkeypatch):
    """Use actual manifest writer, ownership registry and publication Git commands."""
    from dataclasses import replace
    site, own, later, git, request = request_history
    fields = {key: 1 for key in ("canonical_game_count", "display_game_count", "issued_game_count",
                                 "official_position_count", "market_pending_game_count", "internal_market_pending_game_count")}
    fields.update(request.manifest)
    fields.update(display_slate_date_et=request.slate_date, count_scope="EXPLICIT_CANONICAL_AND_DISPLAY",
                  display_date=request.slate_date, canonical_public_payload_sha256="1" * 64,
                  sealed_day_payload_sha256="2" * 64)
    request = replace(request, manifest=fields)
    monkeypatch.setattr(p, "validate_payload_set", lambda req: req.manifest["source_hashes"])

    def render(req, worktree):
        p.ncaaf_delivery_manifest(req, worktree)
        changed = sorted(p.dirty_paths(worktree))
        assert all(p.owned_by("NCAAF", path) for path in changed)
        return {"changed_paths": changed}

    monkeypatch.setattr(p, "build_request", render)
    result = p.publish(request, dry_run=False)
    frozen = p.ncaaf_frozen_manifest_path(request)
    saved = json.loads(git("show", result["published_commit"] + ":" + frozen))
    remote_saved = json.loads(git("show", "origin/main:" + frozen))
    assert saved == remote_saved
    assert saved["queue_request_id"] == request.request_id
    assert saved["delivery_product"] == "T2"
    assert frozen in result["changed_paths"]
