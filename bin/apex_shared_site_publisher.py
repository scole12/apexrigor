#!/usr/bin/env python3
"""Consume validated sport-scoped queues at the one shared site/Git boundary.

Sport runtimes never open the shared checkout.  This deterministic process
validates immutable queue bytes, builds only the affected public surfaces in a
disposable worktree, runs the whole-site integrity checks, and publishes one
serialized GitHub ``main`` transaction.  It never runs a model or invents a
position.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
STATE_ROOT = Path(
    os.environ.get("APEX_SHARED_PUBLISHER_STATE_ROOT", "/var/opt/apex_site_publisher")
)
LOCK_PATH = Path("/run/lock/apex-shared-site-publication.lock")
NCAAF_QUEUE = Path("/var/opt/apex_ncaaf/production/publication_queue")
NCAAF_T3_ROOT = Path("/var/opt/apex_ncaaf/production/t3")
MMA_QUEUE = Path("/var/opt/apex_mma/production/publication_queue")
NFL_QUEUE = Path("/var/opt/apex_nfl/production/publication_queue")
NFL_ISSUANCE = Path("/var/opt/apex_nfl/production/issuance")
CANONICAL_REMOTE = "github.com/scole12/apexrigor.git"
NY = ZoneInfo("America/New_York")
FINAL_RECEIPT_STATES = {
    "PUBLISHED",
    "PUBLISHED_NO_CONTENT_CHANGE",
    "PUBLISHED_EMAIL_DISPATCHED",
    "PUBLISHED_NO_CONTENT_CHANGE_EMAIL_DISPATCHED",
    "PUBLISHED_EMAIL_VERIFIED",
    "PUBLISHED_NO_CONTENT_CHANGE_EMAIL_VERIFIED",
}
ROUTE_PATHS = {
    "index.html",
    "picks.html",
    "picks/index.html",
    "results.html",
    "results/index.html",
    "about/index.html",
    "ncaaf/index.html",
    "ncaaf/results/index.html",
    "ncaaf/about/index.html",
    "mma/index.html",
    "mma/results/index.html",
    "mma/about/index.html",
    "nfl/index.html",
    "nfl/results/index.html",
    "nfl/about/index.html",
}


@dataclass(frozen=True)
class Request:
    sport: str
    request_id: str
    manifest: dict[str, Any]
    payload_root: Path | None
    slate_date: str | None = None
    product: str | None = None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(canonical_json(value))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_bytes(path: Path, body: bytes, mode: int = 0o640) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return value


def contained(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def safe_relative(raw: str) -> str:
    value = PurePosixPath(raw)
    if value.is_absolute() or not value.parts or any(part in {"", ".", ".."} for part in value.parts):
        raise RuntimeError(f"unsafe queued relative path: {raw}")
    return value.as_posix()


def run(command: list[str], *, cwd: Path, timeout: int = 180) -> str:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-2000:]
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(command)}: {detail}")
    # Porcelain status uses a meaningful leading column.  Preserve it while
    # removing only the terminal newline that is noise for scalar Git output.
    return completed.stdout.rstrip("\r\n")


def git(*arguments: str, cwd: Path = ROOT, timeout: int = 180) -> str:
    return run(["git", *arguments], cwd=cwd, timeout=timeout)


def receipt_path(request: Request) -> Path:
    return STATE_ROOT / "receipts" / request.sport.lower() / f"{request.request_id}.json"


def is_complete(request: Request) -> bool:
    path = receipt_path(request)
    if not path.is_file():
        return False
    status = str(load_json(path).get("status") or "")
    if request.sport == "NCAAF":
        return status in {
            "PUBLISHED_EMAIL_VERIFIED",
            "PUBLISHED_NO_CONTENT_CHANGE_EMAIL_VERIFIED",
        }
    return status in FINAL_RECEIPT_STATES


def validate_payload_set(request: Request) -> dict[str, str]:
    if request.payload_root is None or not request.payload_root.is_dir():
        raise RuntimeError(f"queued payload root missing for {request.request_id}")
    expected = request.manifest.get("source_hashes")
    if request.sport == "MMA":
        expected = {"data/mma_system_state.json": request.manifest.get("source_sha256")}
    if not isinstance(expected, dict) or not expected:
        raise RuntimeError(f"queued source hashes absent for {request.request_id}")
    normalized = {safe_relative(str(key)): str(value) for key, value in expected.items()}
    actual_paths = {
        path.relative_to(request.payload_root).as_posix(): path
        for path in request.payload_root.rglob("*")
        if path.is_file()
    }
    if set(actual_paths) != set(normalized):
        raise RuntimeError(
            f"queued payload membership mismatch for {request.request_id}: "
            f"expected={sorted(normalized)} actual={sorted(actual_paths)}"
        )
    for relative, expected_hash in normalized.items():
        if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
            raise RuntimeError(f"invalid queued SHA-256 for {relative}")
        if sha256_file(actual_paths[relative]) != expected_hash:
            raise RuntimeError(f"queued payload hash mismatch: {relative}")
        if request.sport == "NCAAF":
            allowed = (
                relative in {
                    "data/ncaaf_today.json",
                    "ncaaf/index.html",
                    "data/ncaaf_results_cumulative.json",
                    "data/ncaaf_results_summary.json",
                    "data/ncaaf_results_archive.json",
                }
                or bool(re.fullmatch(r"data/ncaaf/\d{4}-\d{2}-\d{2}/[A-Za-z0-9_./-]+", relative))
            )
        else:
            allowed = relative == "data/mma_system_state.json"
        if not allowed:
            raise RuntimeError(f"sport queue attempted an unowned site path: {relative}")
    return normalized


def discover_ncaaf(today_et: str, yesterday_et: str) -> list[Request]:
    requests: list[Request] = []
    if not NCAAF_QUEUE.is_dir():
        return requests
    for pointer_path in sorted(NCAAF_QUEUE.glob("????-??-??/*/current.json")):
        slate_date = pointer_path.parent.parent.name
        product = pointer_path.parent.name
        if product in {"T3", "T2"} and slate_date != today_et:
            continue
        if product == "RESULTS" and slate_date not in {today_et, yesterday_et}:
            continue
        pointer = load_json(pointer_path)
        if pointer.get("status") != "PASS" or pointer.get("publication_state") != "QUEUED_FOR_SHARED_PUBLISHER":
            raise RuntimeError(f"NCAAF queue pointer is not a successful handoff: {pointer_path}")
        request_path = Path(str(pointer.get("request_path") or ""))
        if not contained(request_path, NCAAF_QUEUE) or not request_path.is_file():
            raise RuntimeError(f"NCAAF queue request escaped its authority: {request_path}")
        if sha256_file(request_path) != pointer.get("request_sha256"):
            raise RuntimeError(f"NCAAF queue request hash mismatch: {request_path}")
        manifest = load_json(request_path)
        request_id = str(pointer.get("request_id") or "")
        if (
            manifest.get("sport") != "NCAAF"
            or manifest.get("request_id") != request_id
            or manifest.get("slate_date_et") != slate_date
            or manifest.get("product") != product
        ):
            raise RuntimeError(f"NCAAF queue identity mismatch: {request_path}")
        display_slate_date = str(manifest.get("display_slate_date_et") or "")
        if (
            manifest.get("count_scope") != "EXPLICIT_CANONICAL_AND_DISPLAY"
            or not display_slate_date
        ):
            raise RuntimeError(f"NCAAF queue omits explicit display/count scope: {request_path}")
        if product == "RESULTS":
            if (
                manifest.get("graded_slate_date_et") != slate_date
                or display_slate_date <= slate_date
                or not isinstance(manifest.get("season_year"), int)
            ):
                raise RuntimeError(f"NCAAF results queue crosses graded/display identity: {request_path}")
        elif display_slate_date != slate_date:
            raise RuntimeError(f"NCAAF live-stage display identity mismatch: {request_path}")
        request = Request("NCAAF", request_id, manifest, request_path.parent / "payload", slate_date, product)
        validate_payload_set(request)
        if not is_complete(request):
            requests.append(request)
    return requests


def discover_mma() -> list[Request]:
    pointer_path = MMA_QUEUE / "state/current.json"
    if not pointer_path.is_file():
        return []
    pointer = load_json(pointer_path)
    if pointer.get("status") != "PASS" or pointer.get("publication_state") != "QUEUED_FOR_SHARED_PUBLISHER":
        raise RuntimeError("MMA queue pointer is not a successful handoff")
    request_path = Path(str(pointer.get("request_path") or ""))
    if not contained(request_path, MMA_QUEUE) or not request_path.is_file():
        raise RuntimeError(f"MMA queue request escaped its authority: {request_path}")
    if sha256_file(request_path) != pointer.get("request_sha256"):
        raise RuntimeError("MMA queue request hash mismatch")
    manifest = load_json(request_path)
    request_id = str(pointer.get("request_id") or "")
    if manifest.get("sport") != "MMA" or manifest.get("request_id") != request_id:
        raise RuntimeError("MMA queue identity mismatch")
    request = Request("MMA", request_id, manifest, request_path.parent / "payload")
    validate_payload_set(request)
    return [] if is_complete(request) else [request]


def discover_nfl() -> list[Request]:
    requests: list[Request] = []
    if not NFL_QUEUE.is_dir():
        return requests
    for path in sorted(NFL_QUEUE.glob("*.json")):
        queue = load_json(path)
        if queue.get("schema") != "apex.nfl.publication_queue.v1" or queue.get("status") != "QUEUED":
            raise RuntimeError(f"invalid NFL queue object: {path}")
        issuance_path = Path(str(queue.get("issuance_path") or ""))
        if not contained(issuance_path, NFL_ISSUANCE) or not issuance_path.is_file():
            raise RuntimeError(f"NFL issuance escaped its authority: {issuance_path}")
        if sha256_file(issuance_path) != queue.get("issuance_sha256"):
            raise RuntimeError(f"NFL issuance hash mismatch: {issuance_path}")
        issuance = load_json(issuance_path)
        request_id = str(issuance.get("issuance_id") or path.stem)
        request = Request("NFL", request_id, {**queue, "issuance": issuance}, None)
        if not is_complete(request):
            requests.append(request)
    return requests


def discover() -> list[Request]:
    now_et = datetime.now(timezone.utc).astimezone(NY).date()
    requests = discover_ncaaf(now_et.isoformat(), (now_et - timedelta(days=1)).isoformat())
    requests.extend(discover_mma())
    requests.extend(discover_nfl())
    product_order = {"RESULTS": 0, "T3": 1, "T2": 2, None: 3}
    return sorted(
        requests,
        key=lambda item: (
            str(item.manifest.get("requested_at_utc") or ""),
            item.sport,
            item.slate_date or "",
            product_order[item.product],
            item.request_id,
        ),
    )


def ncaaf_delivery_manifest(request: Request, worktree: Path) -> None:
    if request.slate_date is None or request.product is None:
        raise RuntimeError("NCAAF publication identity is incomplete")
    source_hashes = validate_payload_set(request)
    date_root = f"data/ncaaf/{request.slate_date}/"
    ordinary: dict[str, str] = {}
    result_files: dict[str, str] = {}
    for relative, digest in source_hashes.items():
        if relative.startswith(date_root + "results/") or relative in {
            "data/ncaaf_results_cumulative.json",
            "data/ncaaf_results_summary.json",
            "data/ncaaf_results_archive.json",
        }:
            result_files[relative] = digest
        elif relative.startswith(date_root):
            name = relative.removeprefix(date_root)
            if "/" not in name and not name.endswith(".json"):
                ordinary[name] = digest
    token = request.slate_date.replace("-", "")
    season_year = int(
        request.manifest.get("season_year")
        if request.product == "RESULTS"
        else request.slate_date[:4]
    )
    names = {
        "T3": [f"T3_APEX_NCAAF_DATA_REPORT_{token}.pdf"],
        "T2": [f"NCAAF_T2_FULL_SLATE_{token}.pdf", f"NCAAF_T2_PICKS_CARD_{token}.png"],
        "RESULTS": [
            f"results/NCAAF_DETAILED_RESULTS_{token}.pdf",
            f"results/NCAAF_CUMULATIVE_RECORD_{season_year}.png",
            f"results/NCAAF_PRIOR_DAY_SLATE_{token}.png",
        ],
    }
    manifest: dict[str, Any] = {
        "schema_version": "apex.ncaaf.full_slate_delivery.v5.shared_publisher",
        "slate_date": request.slate_date,
        "graded_slate_date_et": request.manifest.get("graded_slate_date_et"),
        "season_year": request.manifest.get("season_year"),
        "display_slate_date_et": request.manifest["display_slate_date_et"],
        "count_scope": request.manifest["count_scope"],
        "graded_date": request.manifest.get("graded_date"),
        "display_date": request.manifest["display_date"],
        "delivery_product": request.product,
        "canonical_game_count": int(request.manifest["canonical_game_count"]),
        "display_game_count": int(request.manifest["display_game_count"]),
        "issued_game_count": int(request.manifest["issued_game_count"]),
        "official_position_count": int(request.manifest["official_position_count"]),
        "market_pending_game_count": int(request.manifest["market_pending_game_count"]),
        "internal_market_pending_game_count": int(
            request.manifest["internal_market_pending_game_count"]
        ),
        "canonical_public_payload_sha256": request.manifest["canonical_public_payload_sha256"],
        "sealed_day_payload_sha256": request.manifest["sealed_day_payload_sha256"],
        "queue_request_id": request.request_id,
        "files": ordinary,
        "results_files": result_files,
        "attachment_count": len(names[request.product]),
        "attachment_names": names[request.product],
    }
    if request.product == "T3":
        candidates = [
            relative for relative in source_hashes
            if relative.startswith(date_root) and relative.endswith(".json")
        ]
        if len(candidates) != 1:
            raise RuntimeError(f"expected one NCAAF T3 hydration receipt, found {candidates}")
        proof_relative = candidates[0]
        proof = load_json(worktree / proof_relative)
        manifest["t3_hydration_proof"] = {
            "status": proof.get("status"),
            "execution_mode": proof.get("execution_mode"),
            "all_three_post_commit_reopen": proof.get("all_three_post_commit_reopen"),
            "outcome_read_count": proof.get("outcome_read_count"),
            "path": proof_relative.removeprefix(date_root),
            "sha256": source_hashes[proof_relative],
        }
        t3_receipt_path = NCAAF_T3_ROOT / f"{request.slate_date}.json"
        if not t3_receipt_path.is_file():
            raise RuntimeError("NCAAF T3 timing receipt is absent")
        t3_receipt = load_json(t3_receipt_path)
        nominal_ms = int(t3_receipt.get("nominal_t3_utc_ms") or -1)
        actual_start_ms = int(proof.get("request_started_at_utc_ms") or -1)
        if (
            t3_receipt.get("status") != "PASS"
            or t3_receipt.get("slate_date_et") != request.slate_date
            or nominal_ms <= 0
            or actual_start_ms <= 0
        ):
            raise RuntimeError("NCAAF T3 timing receipt is invalid")
        manifest["t3_timing"] = {
            "execution_class": (
                "LATE_RECOVERY" if actual_start_ms > nominal_ms else "ON_TIME"
            ),
            "nominal_t3_utc_ms": nominal_ms,
            "actual_hydration_start_utc_ms": actual_start_ms,
            "actual_hydration_receipt_utc_ms": int(
                proof.get("captured_at_utc_ms") or -1
            ),
        }
    destination = worktree / date_root / "full_slate_delivery_manifest.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n")


def copy_queued_payload(request: Request, worktree: Path) -> None:
    hashes = validate_payload_set(request)
    assert request.payload_root is not None
    for relative in sorted(hashes):
        destination = worktree / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(request.payload_root / relative, destination)
        if sha256_file(destination) != hashes[relative]:
            raise RuntimeError(f"worktree copy read-back failed: {relative}")


def python_tool(worktree: Path, name: str, *arguments: str) -> str:
    return run([sys.executable, str(worktree / "bin" / name), *arguments], cwd=worktree)


def dirty_paths(worktree: Path) -> set[str]:
    output = git("status", "--porcelain", "--untracked-files=all", cwd=worktree)
    paths: set[str] = set()
    for line in output.splitlines():
        if len(line) < 4:
            continue
        value = line[3:]
        if " -> " in value:
            value = value.split(" -> ", 1)[1]
        paths.add(value)
    return paths


def allowed_site_change(relative: str) -> bool:
    return (
        relative in ROUTE_PATHS
        or relative == "data/ncaaf_today.json"
        or relative == "data/ncaaf_results_cumulative.json"
        or relative == "data/ncaaf_results_summary.json"
        or relative == "data/ncaaf_results_archive.json"
        or relative.startswith("data/ncaaf/")
        or relative in {
            "data/mma_system_state.json",
            "data/mma_today.json",
            "data/mma_results_summary.json",
            "data/mma_results_archive.json",
            "data/mma_ops_snapshot.json",
            "data/nfl_today.json",
            "data/nfl_results_summary.json",
            "data/nfl_results_archive.json",
            "data/nfl_system_state.json",
        }
    )


def build_request(request: Request, worktree: Path) -> dict[str, Any]:
    if request.sport in {"NCAAF", "MMA"}:
        copy_queued_payload(request, worktree)
    if request.sport == "NCAAF":
        ncaaf_delivery_manifest(request, worktree)
    elif request.sport == "MMA":
        python_tool(worktree, "build_mma_public_payload.py")
        python_tool(worktree, "build_mma_picks_page.py")
        python_tool(worktree, "build_mma_results_page.py")
        python_tool(worktree, "build_mma_about_page.py")
    elif request.sport == "NFL":
        python_tool(worktree, "build_nfl_public_payload.py")
    else:
        raise RuntimeError(f"unsupported sport publication request: {request.sport}")
    python_tool(worktree, "apply_shared_sport_selector.py", "--root", str(worktree))
    python_tool(worktree, "apply_cloudflare_web_analytics.py", "--root", str(worktree))
    python_tool(worktree, "apply_vercel_web_analytics.py", "--root", str(worktree))
    audit = python_tool(worktree, "audit_public_site.py", "--root", str(worktree))
    changed = dirty_paths(worktree)
    forbidden = sorted(path for path in changed if not allowed_site_change(path))
    if forbidden:
        raise RuntimeError(f"shared publisher produced unowned paths: {forbidden}")
    return {"changed_paths": sorted(changed), "audit_tail": audit[-1600:]}


def publish(request: Request, *, dry_run: bool) -> dict[str, Any]:
    origin = git("remote", "get-url", "origin")
    if CANONICAL_REMOTE not in origin:
        raise RuntimeError(f"noncanonical site origin: {origin}")
    if git("branch", "--show-current") != "main":
        raise RuntimeError("shared site checkout is not on main")
    if dirty_paths(ROOT):
        raise RuntimeError(f"shared site checkout is dirty: {sorted(dirty_paths(ROOT))}")
    git("fetch", "--quiet", "origin", "main")
    local_head = git("rev-parse", "HEAD")
    origin_head = git("rev-parse", "origin/main")
    if local_head != origin_head:
        git("merge", "--ff-only", "origin/main")
    STATE_ROOT.mkdir(parents=True, exist_ok=True, mode=0o750)
    worktree_parent = STATE_ROOT / "worktrees"
    worktree_parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    with tempfile.TemporaryDirectory(prefix="publish-", dir=worktree_parent) as temporary:
        worktree = Path(temporary) / "site"
        git("worktree", "add", "--detach", str(worktree), "origin/main")
        added = True
        try:
            build = build_request(request, worktree)
            changed = build["changed_paths"]
            if dry_run:
                return {
                    "status": "DRY_RUN_PASS",
                    "sport": request.sport,
                    "request_id": request.request_id,
                    **build,
                }
            if changed:
                git("add", "--", *changed, cwd=worktree)
                staged = set(git("diff", "--cached", "--name-only", cwd=worktree).splitlines())
                if staged != set(changed):
                    raise RuntimeError(f"staged site paths differ from validated changes: {sorted(staged)}")
                git(
                    "-c", "user.name=APEX Principal Engineer",
                    "-c", "user.email=ops@apexrigor.com",
                    "commit",
                    "-m",
                    f"Publish {request.sport} production state {request.request_id[:12]}",
                    cwd=worktree,
                )
                commit = git("rev-parse", "HEAD", cwd=worktree)
                git("push", "origin", "HEAD:main", cwd=worktree)
                publication_state = "PUBLISHED"
            else:
                commit = git("rev-parse", "origin/main", cwd=worktree)
                publication_state = "PUBLISHED_NO_CONTENT_CHANGE"
        finally:
            if added:
                git("worktree", "remove", "--force", str(worktree), timeout=60)
                git("worktree", "prune", timeout=60)
    git("fetch", "--quiet", "origin", "main")
    if git("rev-parse", "HEAD") != git("rev-parse", "origin/main"):
        git("merge", "--ff-only", "origin/main")
    return {
        "status": publication_state,
        "sport": request.sport,
        "request_id": request.request_id,
        "published_commit": commit,
        **build,
    }


def ncaaf_workflow_title(request: Request) -> str:
    return f"NCAA {request.product} {request.slate_date} {request.request_id}"


def matching_ncaaf_workflow_runs(request: Request) -> list[dict[str, Any]]:
    raw = run(
        [
            "gh", "run", "list", "--repo", "scole12/apexrigor",
            "--workflow", "ncaaf-full-slate-delivery.yml", "--event", "workflow_dispatch",
            "--limit", "100", "--json",
            "databaseId,displayTitle,status,conclusion,createdAt,updatedAt,url,headSha",
        ],
        cwd=ROOT,
    )
    rows = json.loads(raw or "[]")
    title = ncaaf_workflow_title(request)
    return [row for row in rows if str(row.get("displayTitle") or "") == title]


def wait_for_ncaaf_workflow(
    request: Request,
    run_id: int | None,
    *,
    excluded_run_ids: set[int] | None = None,
) -> dict[str, Any]:
    deadline = time.monotonic() + 360
    selected: dict[str, Any] | None = None
    excluded = excluded_run_ids or set()
    while time.monotonic() < deadline:
        matches = matching_ncaaf_workflow_runs(request)
        candidates = [
            row for row in matches
            if int(row["databaseId"]) not in excluded
            and (run_id is None or int(row["databaseId"]) == run_id)
        ]
        if len(candidates) > 1:
            raise RuntimeError(
                f"duplicate current NCAA email workflow attempts: "
                f"{[row.get('databaseId') for row in candidates]}"
            )
        if candidates:
            selected = candidates[0]
            run_id = int(selected["databaseId"])
            if selected.get("status") == "completed":
                if selected.get("conclusion") != "success":
                    raise RuntimeError(
                        f"NCAA email workflow {run_id} completed {selected.get('conclusion')}"
                    )
                return selected
        time.sleep(2)
    raise RuntimeError(
        f"NCAA email workflow did not complete before timeout: "
        f"request={request.request_id} run_id={run_id} last={selected}"
    )


def preserve_ncaaf_email_evidence(
    request: Request,
    workflow: dict[str, Any],
) -> dict[str, Any]:
    run_id = int(workflow["databaseId"])
    evidence_root = STATE_ROOT / "email_evidence" / "ncaaf" / request.request_id
    transaction_path = evidence_root / "transaction.json"
    message_path = evidence_root / "message.eml"
    if transaction_path.is_file() and message_path.is_file():
        transaction = load_json(transaction_path)
    else:
        download_root = STATE_ROOT / "downloads"
        download_root.mkdir(parents=True, exist_ok=True, mode=0o750)
        with tempfile.TemporaryDirectory(prefix="ncaaf-email-", dir=download_root) as temporary:
            temporary_path = Path(temporary)
            run(
                [
                    "gh", "run", "download", str(run_id), "--repo", "scole12/apexrigor",
                    "--dir", str(temporary_path),
                ],
                cwd=ROOT,
                timeout=180,
            )
            transactions = sorted(temporary_path.rglob("*_TRANSACTION.json"))
            messages = sorted(temporary_path.rglob("*_MESSAGE.eml"))
            if len(transactions) != 1 or len(messages) != 1:
                raise RuntimeError(
                    "NCAA workflow artifact did not contain exactly one transaction and message: "
                    f"transactions={len(transactions)} messages={len(messages)}"
                )
            transaction_bytes = transactions[0].read_bytes()
            message_bytes = messages[0].read_bytes()
            transaction = json.loads(transaction_bytes)
            atomic_bytes(transaction_path, transaction_bytes)
            atomic_bytes(message_path, message_bytes, 0o600)

    expected_message_id = (
        f"<ncaaf-{request.slate_date.replace('-', '')}-{request.product.lower()}-"
        f"{str(request.manifest['canonical_public_payload_sha256'])[:20]}@apexrigor.com>"
    )
    expected_attachment_count = {"T3": 1, "T2": 2, "RESULTS": 3}[request.product]
    recipient_rows = list(transaction.get("smtp_recipient_responses") or [])
    checks = {
        "request_id": transaction.get("request_id") == request.request_id,
        "slate_date": transaction.get("slate_date") == request.slate_date,
        "delivery_mode": transaction.get("delivery_mode") == "NORMAL",
        "message_id": transaction.get("message_id") == expected_message_id,
        "attachment_count": int(transaction.get("attachment_count") or -1)
        == expected_attachment_count,
        "recipient_set_nonempty": bool(transaction.get("envelope_recipients")),
        "all_recipients_accepted": bool(recipient_rows)
        and all(bool(row.get("accepted")) for row in recipient_rows),
        "smtp_data_accepted": int(transaction.get("smtp_data_response_code") or 0) == 250,
        "delivery_state": transaction.get("delivery_state") == "PROVIDER_ACCEPTED",
        "credentials_absent": transaction.get("credentials_recorded") is False,
    }
    if not all(checks.values()):
        raise RuntimeError(f"NCAA provider transaction verification failed: {checks}")
    return {
        "status": "PASS",
        "checks": checks,
        "message_id": transaction["message_id"],
        "provider_queue_id": transaction.get("provider_queue_id"),
        "provider_accepted_at": transaction.get("provider_accepted_at"),
        "recipient_count": len(transaction["envelope_recipients"]),
        "attachment_count": int(transaction["attachment_count"]),
        "transaction_path": str(transaction_path),
        "transaction_sha256": sha256_file(transaction_path),
        "message_path": str(message_path),
        "message_sha256": sha256_file(message_path),
    }


def dispatch_ncaaf_email(request: Request, receipt: dict[str, Any]) -> dict[str, Any]:
    if request.slate_date is None or request.product is None:
        raise RuntimeError("NCAAF email handoff identity is incomplete")
    state_path = receipt_path(request)
    prior = load_json(state_path) if state_path.is_file() else {}
    publication_status = str(
        prior.get("publication_status")
        or receipt.get("publication_status")
        or str(receipt["status"]).split("_EMAIL_", 1)[0]
    )
    saved_run_id = prior.get("email_workflow_run_id")
    matches = matching_ncaaf_workflow_runs(request)
    successful = [row for row in matches if row.get("conclusion") == "success"]
    active = [row for row in matches if row.get("status") != "completed"]
    if len(successful) > 1 or len(active) > 1:
        raise RuntimeError(
            f"duplicate deliverable NCAA email workflows for immutable request: "
            f"{[row.get('databaseId') for row in matches]}"
        )
    by_id = {int(row["databaseId"]): row for row in matches}
    if saved_run_id is not None:
        saved = by_id.get(int(saved_run_id))
        if saved is None:
            raise RuntimeError("NCAA persisted workflow identity is absent from GitHub read-back")
        if saved.get("status") == "completed" and saved.get("conclusion") != "success":
            # A completed failed attempt performed no verified external action.
            # Retry the email stage using the current canonical workflow source.
            saved_run_id = None
    if saved_run_id is None and successful:
        saved_run_id = int(successful[0]["databaseId"])
    if saved_run_id is None and active:
        saved_run_id = int(active[0]["databaseId"])
    prior_attempt_ids = sorted(by_id)
    intent = {
        **receipt,
        "publication_status": publication_status,
        "status": publication_status + "_EMAIL_DISPATCH_INTENT",
        "email_workflow": "ncaaf-full-slate-delivery.yml",
        "email_workflow_title": ncaaf_workflow_title(request),
        "email_workflow_run_id": saved_run_id,
        "email_dispatch_at_utc": prior.get("email_dispatch_at_utc")
        or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "duplicate_email_workflow_count": 0,
    }
    atomic_json(state_path, intent)
    if saved_run_id is None:
        run(
            [
                "gh", "workflow", "run", "ncaaf-full-slate-delivery.yml",
                "--repo", "scole12/apexrigor", "--ref", "main",
                "-f", f"product={request.product}",
                "-f", f"slate_date={request.slate_date}",
                "-f", "delivery_mode=NORMAL",
                "-f", f"request_id={request.request_id}",
            ],
            cwd=ROOT,
        )
    try:
        workflow = wait_for_ncaaf_workflow(
            request,
            int(saved_run_id) if saved_run_id is not None else None,
            excluded_run_ids=set(prior_attempt_ids) if saved_run_id is None else None,
        )
        evidence = preserve_ncaaf_email_evidence(request, workflow)
    except Exception as error:
        failed = {
            **intent,
            "status": publication_status + "_EMAIL_VERIFICATION_FAILED_REQUIRES_RETRY",
            "exact_error": f"{type(error).__name__}: {str(error)[:1600]}",
        }
        atomic_json(state_path, failed)
        raise
    complete = {
        **intent,
        "status": publication_status + "_EMAIL_VERIFIED",
        "email_dispatch_accepted": True,
        "email_workflow_run_id": int(workflow["databaseId"]),
        "email_workflow_url": workflow.get("url"),
        "email_workflow_conclusion": workflow.get("conclusion"),
        "email_workflow_attempt_ids": sorted(
            set(prior_attempt_ids) | {int(workflow["databaseId"])}
        ),
        "email_provider_evidence": evidence,
        "email_external_action_count": 1,
        "duplicate_email_workflow_count": 0,
        "verified_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    atomic_json(state_path, complete)
    return complete


def execute(*, dry_run: bool) -> dict[str, Any]:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        pending = discover()
        if not pending:
            return {"status": "NO_PENDING_REQUEST", "pending_count": 0}
        request = pending[0]
        result = publish(request, dry_run=dry_run)
        result["pending_count_before"] = len(pending)
        if dry_run:
            return result
        result["published_at_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        atomic_json(receipt_path(request), result)
        if request.sport == "NCAAF":
            result = dispatch_ncaaf_email(request, result)
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args()
    try:
        print(json.dumps(execute(dry_run=arguments.dry_run), indent=2, sort_keys=True))
        return 0
    except Exception as error:
        print(
            json.dumps(
                {
                    "status": "FAIL_CLOSED",
                    "error_type": type(error).__name__,
                    "exact_error": str(error)[:2000],
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
