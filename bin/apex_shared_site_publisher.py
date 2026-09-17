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
from email import policy
from email.parser import BytesParser
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
NFL_ISSUANCE = Path("/var/opt/apex_nfl/issuance")
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
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
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
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
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
    if request.sport == 'NFL' and request.product == 'GRADER':
        receipt=load_json(path)
        if receipt.get('isolated_readback',{}).get('status')=='PASS':
            sys.path.insert(0,'/opt/apex_nfl/src')
            from apex_nfl.acceptance_boundary import context
            return context() is not None
        return status in FINAL_RECEIPT_STATES and receipt.get('live_readback',{}).get('status')=='PASS'
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
        if product == "RESULTS" and slate_date > today_et:
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
    from nfl_publication_acceptance import accepted_stage, accepted_issuance
    requests: list[Request] = []
    if not NFL_QUEUE.is_dir():
        return requests
    for path in sorted(NFL_QUEUE.glob("*.json")):
        try:
            queue = load_json(path)
            if queue.get('schema') == 'apex.nfl.grader_publication_queue.v1':
                request = Request('NFL', str(queue['request_id']), queue, None, queue['slate_date'], 'GRADER')
                if path.stem != request.request_id:raise RuntimeError('GRADER_QUEUE_FILENAME')
                if not is_complete(request):requests.append(request)
                continue
            if queue.get('schema') == 'apex.nfl.stage_publication_queue.v2':
                stage_path = Path(str(queue.get('stage_receipt_path') or ''))
                valid_root = any(contained(stage_path, root) for root in (
                    Path('/var/opt/apex_nfl/state/cohorts'), Path('/var/opt/apex_nfl/state/stage_events'),
                    Path('/var/opt/apex_nfl/state/season_refresh')))
                if (not valid_root or not stage_path.is_file()
                    or sha256_file(stage_path) != queue.get('stage_receipt_sha256')
                    or queue.get('status') != 'QUEUED' or queue.get('stage') not in {'T3', 'T2', 'GRADER', 'SCHEDULE_REFRESH'}):
                    raise RuntimeError('Invalid NFL stage publication binding')
                if queue.get('stage') == 'GRADER':
                    raise RuntimeError('LEGACY_GRADER_REQUEST_REQUIRES_CANONICAL_RESULT')
                if queue.get('stage') in {'T3', 'T2'}:
                    expected_id = hashlib.sha256(f"{queue['stage']}:{stage_path}".encode()).hexdigest()
                    if queue.get('request_id') != expected_id or not accepted_stage(stage_path):
                        continue
                request = Request('NFL', str(queue['request_id']), queue, None)
                if not is_complete(request):
                    requests.append(request)
                continue
            if queue.get("schema") != "apex.nfl.publication_queue.v1" or queue.get("status") != "QUEUED":
                raise RuntimeError(f"invalid NFL queue object: {path}")
            issuance_path = Path(str(queue.get("issuance_path") or ""))
            if not contained(issuance_path, NFL_ISSUANCE) or not issuance_path.is_file():
                raise RuntimeError(f"NFL issuance escaped its authority: {issuance_path}")
            if sha256_file(issuance_path) != queue.get("issuance_sha256"):
                raise RuntimeError(f"NFL issuance hash mismatch: {issuance_path}")
            issuance = load_json(issuance_path)
            if not accepted_issuance(issuance_path, issuance):
                continue
            request_id = str(issuance.get("issuance_id") or path.stem)
            request = Request("NFL", request_id, {**queue, "issuance": issuance}, None)
            if not is_complete(request):
                requests.append(request)
        except Exception as error:
            requests.append(Request('NFL', path.stem, {'discovery_error':str(error)}, None))
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
    if request.product == "RESULTS":
        # Email evidence is bound to the requested dated snapshot. Newer public
        # cumulative records may legitimately have advanced before this send.
        result_files = {name: digest for name, digest in result_files.items() if name.startswith(date_root + "results/")}
        result_files[results_cumulative_snapshot(request)] = source_hashes["data/ncaaf_results_cumulative.json"]
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
            f"results/APEX_TOTAL_RECORD_{token}.png",
            f"results/NCAAF_PRIOR_DAY_SLATE_{token}.png",
            f"results/NCAAF_DETAILED_RESULTS_{token}.pdf",
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
    if request.product == "RESULTS":
        manifest["results_cumulative_path"] = results_cumulative_snapshot(request)
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


def results_cumulative_snapshot(request: Request) -> str:
    if request.product != "RESULTS" or not request.slate_date:
        raise RuntimeError("NCAA result snapshot requires a dated results request")
    return f"data/ncaaf/{request.slate_date}/results/NCAAF_CUMULATIVE_RESULTS.json"


def publication_skip_paths(request: Request, worktree: Path) -> set[str]:
    """Backlog recovery must preserve a later issued card and newer results."""
    if request.sport != "NCAAF" or request.product != "RESULTS":
        return set()
    assert request.payload_root is not None
    skipped: set[str] = set()
    current_picks = worktree / "data/ncaaf_today.json"
    if current_picks.is_file():
        current_date = str((load_json(current_picks).get("slate") or {}).get("slate_date_et") or "")
        incoming_date = str(request.manifest.get("display_slate_date_et") or "")
        if not current_date or not incoming_date:
            raise RuntimeError("NCAA_RESULTS_DISPLAY_IDENTITY_ABSENT")
        if current_date >= incoming_date:
            skipped.update({"data/ncaaf_today.json", "ncaaf/index.html"})
    incoming = load_json(request.payload_root / "data/ncaaf_results_cumulative.json")
    current = worktree / "data/ncaaf_results_cumulative.json"
    if current.is_file():
        existing = load_json(current)
        def rank(payload):
            latest = str(payload.get("latest_graded_slate") or "")
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", latest):
                raise RuntimeError("NCAA_RESULTS_LATEST_IDENTITY_ABSENT")
            return int(payload["season_year"]), latest
        if rank(existing) > rank(incoming):
            skipped.update({"data/ncaaf_results_cumulative.json", "data/ncaaf_results_summary.json", "data/ncaaf_results_archive.json"})
        elif int(existing["season_year"]) == int(incoming["season_year"]):
            def positions(payload):
                rows = list(payload["positions"])
                values = {str(row.get("position_id") or row.get("canonical_t2_position_sha256") or ""): row for row in rows}
                if len(values) != len(rows) or any(not re.fullmatch(r"[a-f0-9]{64}", key) for key in values):
                    raise RuntimeError("NCAA_RESULTS_POSITION_IDENTITY_INVALID")
                return values
            old, new = positions(existing), positions(incoming)
            if not old.keys() <= new.keys():
                raise RuntimeError("NCAA_RESULTS_WOULD_DROP_PUBLISHED_POSITIONS")
            for key, row in old.items():
                if row.get("result") not in {None, "PENDING"} and row.get("result") != new[key].get("result"):
                    raise RuntimeError("NCAA_RESULTS_SETTLEMENT_CONFLICT:" + key)
    return skipped


def copy_queued_payload(request: Request, worktree: Path) -> None:
    hashes = validate_payload_set(request)
    assert request.payload_root is not None
    skipped = publication_skip_paths(request, worktree)
    for relative in sorted(hashes):
        if relative in skipped:
            continue
        destination = worktree / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(request.payload_root / relative, destination)
        if sha256_file(destination) != hashes[relative]:
            raise RuntimeError(f"worktree copy read-back failed: {relative}")
    if request.sport == "NCAAF" and request.product == "RESULTS":
        source = "data/ncaaf_results_cumulative.json"
        destination = worktree / results_cumulative_snapshot(request)
        destination.parent.mkdir(parents=True, exist_ok=True)
        body = (request.payload_root / source).read_bytes()
        if destination.exists() and destination.read_bytes() != body:
            raise RuntimeError("NCAA_RESULTS_DATED_SNAPSHOT_CONFLICT")
        destination.write_bytes(body)
        if sha256_file(destination) != hashes[source]:
            raise RuntimeError("NCAA_RESULTS_DATED_SNAPSHOT_HASH_MISMATCH")


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
            "data/apex_results_summary.json",
            "mma/results/render.js",
            "data/nfl_today.json",
            "data/nfl_results_summary.json",
            "data/nfl_results_archive.json",
            "data/nfl_system_state.json",
        }
    )


def build_request(request: Request, worktree: Path) -> dict[str, Any]:
    if request.manifest.get('discovery_error'):
        raise RuntimeError(request.manifest['discovery_error'])
    if request.sport == 'NFL' and request.product == 'GRADER':
        return build_nfl_grader(request, worktree)
    if request.sport in {"NCAAF", "MMA"}:
        copy_queued_payload(request, worktree)
    if request.sport == "NCAAF":
        ncaaf_delivery_manifest(request, worktree)
    elif request.sport == "MMA":
        python_tool(worktree, "build_mma_public_payload.py")
        python_tool(worktree, "build_total_apex_results.py")
        python_tool(worktree, "build_mma_picks_page.py")
        python_tool(worktree, "build_mma_results_page.py")
        python_tool(worktree, "build_mma_about_page.py")
    elif request.sport == "NFL":
        # Execute the reviewed admission gate from this publication worktree.
        run([sys.executable, str(worktree / "bin/build_nfl_public_payload.py"),
             "--output-root", str(worktree)], cwd=worktree)
    else:
        raise RuntimeError(f"unsupported sport publication request: {request.sport}")
    if request.sport == 'NFL':
        # FAIL_CLOSED_NO_PICKS_TEASER — ban prior-day results strip on /nfl picks.
        for rel in ("nfl/index.html", "public/nfl/index.html"):
            picks = worktree / rel
            if not picks.is_file():
                continue
            html = picks.read_text()
            if "NFL_LATEST_RESULTS" in html or "nfl-ledger-note" in html:
                raise RuntimeError(f"NFL picks teaser banned but present in {picks}")
            before = html.split("<!-- NFL_BOARD_START -->", 1)[0] if "<!-- NFL_BOARD_START -->" in html else html
            if "graded picks" in before or ("View results" in before and "results:" in before):
                raise RuntimeError(f"NFL picks prior-day teaser banned but present in {picks}")
        changed = dirty_paths(worktree)
        if any(not (p.startswith('data/nfl_') or p.startswith('nfl/')) for p in changed):
            raise RuntimeError('NFL publication attempted a non-NFL path')
        surfaces = ('data/nfl_today.json', 'data/nfl_system_state.json', 'data/nfl_results_archive.json', 'data/nfl_results_summary.json', 'nfl/index.html')
        return {'changed_paths': sorted(changed), 'audit_tail': 'NFL authority-bound builder completed',
                'nfl_surface_hashes': {name: sha256_file(worktree / name) for name in surfaces}}
    if request.sport == "NCAAF" and request.product == "RESULTS":
        # Results recovery owns NCAA output paths. Shared navigation/analytics
        # rewrites are unrelated and can modify currently issued picks pages.
        # The canonical Vercel build also regenerates other sport pages.
        # Validate the full deployable output in a disposable copy so those
        # generated changes never enter this NCAA source publication commit.
        with tempfile.TemporaryDirectory(prefix="ncaaf-build-check-", dir=worktree.parent) as temporary:
            validation = Path(temporary) / "site"
            shutil.copytree(worktree, validation, ignore=shutil.ignore_patterns(".git", "public", "__pycache__"))
            audit = python_tool(validation, "build_vercel_output.py")
        changed = dirty_paths(worktree)
        if any(not (name.startswith("data/ncaaf/") or name.startswith("data/ncaaf_") or name == "ncaaf/index.html") for name in changed):
            raise RuntimeError("NCAA results publication attempted an unrelated path")
        return {"changed_paths": sorted(changed), "audit_tail": audit[-1600:]}
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
    if request.sport=='NFL' and not dry_run:
        return publish_nfl_durable(request)
    intent=STATE_ROOT/'publication_intents'/request.sport.lower()/(request.request_id+'.json')
    if request.sport=='NFL' and not dry_run and intent.exists():
        prior=load_json(intent)
        if prior.get('request_id')!=request.request_id or (request.product=='GRADER' and prior.get('canonical_result')!=request.manifest['canonical_result']):raise RuntimeError('PUBLICATION_INTENT_DRIFT')
        return prior
    origin = git("remote", "get-url", "origin")
    if CANONICAL_REMOTE not in origin:
        raise RuntimeError(f"noncanonical site origin: {origin}")
    if git("branch", "--show-current") != "main":
        raise RuntimeError("shared site checkout is not on main")
    root_dirty = bool(dirty_paths(ROOT))
    # Build from fetched origin/main in an isolated worktree. Preserve local work.
    git("fetch", "--quiet", "origin", "main")
    local_head = git("rev-parse", "HEAD")
    origin_head = git("rev-parse", "origin/main")
    if local_head != origin_head and not root_dirty:
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
    if not dirty_paths(ROOT) and git("rev-parse", "HEAD") != git("rev-parse", "origin/main"):
        git("merge", "--ff-only", "origin/main")
    result={"status":publication_state,"sport":request.sport,"request_id":request.request_id,
            "published_commit":commit,**build}
    if request.sport=='NFL':atomic_json(intent,result)
    return result


def nfl_boundary(label, artifact=None):
    sys.path.insert(0,'/opt/apex_nfl/src')
    from apex_nfl.acceptance_boundary import stage
    stage(label,artifact)


def publish_nfl_durable(request):
    """Keep the exact request worktree and commit across each durable boundary."""
    if not re.fullmatch('[a-f0-9]{64}', request.request_id):
        raise RuntimeError('NFL_REQUEST_ID')
    intent=STATE_ROOT/'publication_intents/nfl'/(request.request_id+'.json')
    worktree=STATE_ROOT/'worktrees'/('nfl-'+request.request_id)
    worktree.parent.mkdir(parents=True,exist_ok=True)
    origin=git('remote','get-url','origin')
    sys.path.insert(0,'/opt/apex_nfl/src')
    from apex_nfl.acceptance_boundary import context
    isolated=context()
    if isolated:
        if origin!='file:///var/opt/apex_site_publisher/isolated-origin.git':
            raise RuntimeError('ISOLATED_PUBLICATION_EXTERNAL_REMOTE_REFUSED')
    elif CANONICAL_REMOTE not in origin:
        raise RuntimeError('NONCANONICAL_REMOTE')
    if git('branch','--show-current')!='main':raise RuntimeError('NONCANONICAL_BRANCH')
    if intent.exists():
        state=load_json(intent)
        if state['request_id']!=request.request_id or state['request_sha256']!=hashlib.sha256(canonical_json(request.manifest)).hexdigest():
            raise RuntimeError('PUBLICATION_INTENT_DRIFT')
    else:
        git('fetch','--quiet','origin','main')
        state={'request_id':request.request_id,'request_sha256':hashlib.sha256(canonical_json(request.manifest)).hexdigest(),
               'phase':'STARTED','base_commit':git('rev-parse','origin/main'),'worktree':str(worktree)}
        atomic_json(intent,state);nfl_boundary('PUBLISH_REQUEST_INTENT',intent)
    if state['phase']=='STARTED':
        if not worktree.exists():git('worktree','add','--detach',str(worktree),state['base_commit'])
        if git('rev-parse','HEAD',cwd=worktree)!=state['base_commit']:
            raise RuntimeError('UNEXPECTED_UNCOMMITTED_PUBLICATION')
        build=build_request(request,worktree)
        changed=build['changed_paths']
        if changed:git('add','--',*changed,cwd=worktree)
        if set(git('diff','--cached','--name-only',cwd=worktree).splitlines())!=set(changed):
            raise RuntimeError('PUBLICATION_STAGE_DRIFT')
        state.update(phase='BUILT',build=build,tree=git('write-tree',cwd=worktree),
                     commit_time=datetime.now(timezone.utc).isoformat())
        atomic_json(intent,state);nfl_boundary('PUBLISH_BUILD_DURABLE',intent)
    if state['phase']=='BUILT':
        if state['build']['changed_paths']:
            # commit-tree is deterministic, including a persisted timestamp, after a crash.
            env={**os.environ,'GIT_AUTHOR_NAME':'APEX Principal Engineer','GIT_AUTHOR_EMAIL':'ops@apexrigor.com',
                 'GIT_COMMITTER_NAME':'APEX Principal Engineer','GIT_COMMITTER_EMAIL':'ops@apexrigor.com',
                 'GIT_AUTHOR_DATE':state['commit_time'],'GIT_COMMITTER_DATE':state['commit_time']}
            commit=subprocess.check_output(['git','commit-tree',state['tree'],'-p',state['base_commit'],'-m',
                'Publish NFL production state '+request.request_id[:12]],cwd=worktree,env=env,text=True).strip()
            git('update-ref','refs/apex-publications/'+request.request_id,commit)
            nfl_boundary('PUBLISH_COMMIT_OBJECT_DURABLE')
        else:commit=state['base_commit']
        state.update(phase='COMMITTED',published_commit=commit)
        atomic_json(intent,state);nfl_boundary('PUBLISH_COMMIT_INTENT',intent)
    if state['phase']=='COMMITTED':
        git('fetch','--quiet','origin','main')
        ancestor=subprocess.run(['git','merge-base','--is-ancestor',state['published_commit'],'origin/main'],cwd=ROOT).returncode
        if ancestor:
            if git('rev-parse','origin/main')!=state['base_commit']:
                raise RuntimeError('PUBLICATION_ORIGIN_ADVANCED_RECONCILIATION_REQUIRED')
            git('push','origin',state['published_commit']+':refs/heads/main')
        nfl_boundary('PUBLISH_REMOTE_PUSH_DURABLE')
        state['phase']='PUSHED';atomic_json(intent,state);nfl_boundary('PUBLISH_PUSH_INTENT',intent)
    if state['phase']!='PUSHED':raise RuntimeError('PUBLICATION_UNKNOWN_PHASE')
    return {'status':'PUBLISHED' if state['build']['changed_paths'] else 'PUBLISHED_NO_CONTENT_CHANGE',
            'sport':'NFL','request_id':request.request_id,'published_commit':state['published_commit'],**state['build']}


def ncaaf_workflow_title(request: Request) -> str:
    return f"NCAA {request.product} {request.slate_date} {request.request_id}"


def matching_ncaaf_workflow_runs(request: Request) -> list[dict[str, Any]]:
    # The old latest-100 query could forget an earlier attempt. Restrict a fully
    # paginated history to the immutable request's creation window instead.
    created = datetime.fromisoformat(str(request.manifest.get("requested_at_utc") or "").replace("Z", "+00:00"))
    if created.tzinfo is None:
        raise RuntimeError("NCAA_EMAIL_HISTORY_SCOPE_MISSING")
    since = min(str(request.slate_date), (created.astimezone(timezone.utc) - timedelta(days=1)).date().isoformat())
    endpoint = (
        "repos/scole12/apexrigor/actions/workflows/ncaaf-full-slate-delivery.yml/runs"
        "?event=workflow_dispatch&per_page=100&created=>=" + since
    )
    raw = run(["gh", "api", "--paginate", endpoint], cwd=ROOT)
    # Older installed gh versions emit concatenated page objects and do not
    # support --slurp. Decode every page without upgrading the live CLI.
    pages = []
    remaining = raw.lstrip()
    decoder = json.JSONDecoder()
    while remaining:
        page, end = decoder.raw_decode(remaining)
        if not isinstance(page, dict):
            raise RuntimeError("NCAA_EMAIL_HISTORY_INCOMPLETE")
        pages.append(page)
        remaining = remaining[end:].lstrip()
    if not pages:
        raise RuntimeError("NCAA_EMAIL_HISTORY_INCOMPLETE")
    rows = {}
    expected = 0
    for page in pages:
        expected = max(expected, int(page["total_count"]))
        for row in page["workflow_runs"]:
            rows[int(row["id"])] = row
    if len(rows) < expected:
        raise RuntimeError("NCAA_EMAIL_HISTORY_INCOMPLETE")
    prior_delivery = request.manifest.get("prior_email_delivery") or {}
    expected_id = str(prior_delivery.get("request_id") or request.request_id)
    title = f"NCAA {request.product} {request.slate_date} {expected_id}"
    prefix = f"NCAA {request.product} {request.slate_date} "
    # Recovery and normal requests can have different content identities for
    # the same obligation. An earlier transaction must never be forgotten.
    if any(str(row.get("display_title") or "").startswith(prefix)
           and row.get("display_title") != title for row in rows.values()):
        raise RuntimeError("NCAA_EMAIL_RECONCILIATION_REQUIRED: another request exists for this stage/date")
    return [
        {"databaseId": row["id"], "displayTitle": row["display_title"],
         "status": row["status"], "conclusion": row["conclusion"],
         "createdAt": row.get("created_at"), "updatedAt": row.get("updated_at"),
         "url": row["html_url"], "headSha": row["head_sha"],
         "attempt": row.get("run_attempt")}
        for row in rows.values() if row.get("display_title") == title
    ]


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
    adoption = request.manifest.get("prior_email_delivery") or {}
    original_request = str(adoption.get("request_id") or request.request_id)
    if not re.fullmatch(r"[a-f0-9]{64}", original_request):
        raise RuntimeError("NCAA_PRIOR_EMAIL_IDENTITY_INVALID")
    evidence_root = STATE_ROOT / "email_evidence" / "ncaaf" / original_request
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
    expected_mode = "NORMAL"
    if adoption:
        if request.product != "RESULTS" or adoption.get("delivery_mode") != "RECOVERY":
            raise RuntimeError("NCAA_PRIOR_EMAIL_SCOPE_INVALID")
        if int(adoption.get("workflow_run_id") or 0) != run_id:
            raise RuntimeError("NCAA_PRIOR_EMAIL_RUN_MISMATCH")
        expected_mode = "RECOVERY"
        expected_message_id = f"<ncaaf-{request.slate_date.replace('-', '')}-results-recovery-{run_id}@apexrigor.com>"
        if (sha256_file(transaction_path) != adoption.get("transaction_sha256")
                or sha256_file(message_path) != adoption.get("message_sha256")):
            raise RuntimeError("NCAA_PRIOR_EMAIL_PHYSICAL_PROOF_CHANGED")
    expected_attachment_count = {"T3": 1, "T2": 2, "RESULTS": 3}[request.product]
    recipient_rows = list(transaction.get("smtp_recipient_responses") or [])
    message_bytes = message_path.read_bytes()
    message = BytesParser(policy=policy.default).parsebytes(message_bytes)
    token = str(request.slate_date).replace("-", "")
    required = {
        "T3": [f"T3_APEX_NCAAF_DATA_REPORT_{token}.pdf"],
        "T2": [f"NCAAF_T2_FULL_SLATE_{token}.pdf", f"NCAAF_T2_PICKS_CARD_{token}.png"],
        "RESULTS": [f"results/APEX_TOTAL_RECORD_{token}.png",
                    f"results/NCAAF_PRIOR_DAY_SLATE_{token}.png",
                    f"results/NCAAF_DETAILED_RESULTS_{token}.pdf"],
    }[str(request.product)]
    source_hashes = request.manifest.get("source_hashes") or {}
    expected_files = {Path(name).name: source_hashes.get(f"data/ncaaf/{request.slate_date}/{name}") for name in required}
    parts = list(message.iter_attachments())
    physical_files = {part.get_filename(): hashlib.sha256(part.get_payload(decode=True) or b"").hexdigest() for part in parts}
    recorded = list(transaction.get("attachments") or [])
    recorded_files = {item.get("filename"): item.get("sha256") for item in recorded}
    checks = {
        "request_id": transaction.get("request_id") == original_request,
        "single_workflow_attempt": workflow.get("attempt") == 1,
        "mime_hash": hashlib.sha256(message_bytes).hexdigest() == transaction.get("mime_sha256"),
        "mime_message_id": str(message.get("Message-ID") or "") == expected_message_id,
        "source_attachment_binding": all(expected_files.values()) and physical_files == expected_files == recorded_files,
        "attachment_membership": len(parts) == len(recorded) == len(expected_files) == expected_attachment_count,
        "slate_date": transaction.get("slate_date") == request.slate_date,
        "delivery_mode": transaction.get("delivery_mode") == expected_mode,
        "message_id": transaction.get("message_id") == expected_message_id,
        "attachment_count": int(transaction.get("attachment_count") or -1)
        == expected_attachment_count,
        "recipient_set_nonempty": bool(transaction.get("envelope_recipients")),
        "all_recipients_accepted": bool(recipient_rows)
        and all(bool(row.get("accepted")) and int(row.get("code") or 0) in (250,251) for row in recipient_rows),
        "smtp_data_accepted": int(transaction.get("smtp_data_response_code") or 0) == 250,
        "delivery_state": transaction.get("delivery_state") == "PROVIDER_ACCEPTED",
        "credentials_absent": transaction.get("credentials_recorded") is False,
    }
    if adoption:
        expected_cumulative = source_hashes.get("data/ncaaf_results_cumulative.json")
        checks["prior_results_snapshot_binding"] = bool(expected_cumulative) and (
            adoption.get("canonical_results_sha256") == expected_cumulative
            == str(message.get("X-APEX-NCAA-Public-Payload-SHA256") or "").strip()
        )
        checks["prior_delivery_mode_header"] = str(message.get("X-APEX-NCAA-Delivery-Mode") or "") == "RECOVERY"
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
        "original_request_id": original_request,
        "delivery_mode": expected_mode,
        "adopted_without_resend": bool(adoption),
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
    # Any earlier attempt may have reached SMTP DATA, regardless of its final
    # GitHub conclusion. Reconcile that identity; never infer that failure means
    # no message was accepted.
    by_id = {int(row["databaseId"]): row for row in matches}
    if len(by_id) != len(matches) or len(by_id) > 1:
        raise RuntimeError("NCAA_EMAIL_RECONCILIATION_REQUIRED: multiple workflow attempts")
    if saved_run_id is not None and int(saved_run_id) not in by_id:
        raise RuntimeError("NCAA_EMAIL_RECONCILIATION_REQUIRED: persisted workflow absent from read-back")
    if saved_run_id is None and matches:
        saved_run_id = int(matches[0]["databaseId"])
    if request.manifest.get("prior_email_delivery") and saved_run_id is None:
        raise RuntimeError("NCAA_PRIOR_EMAIL_NOT_FOUND: no new send is permitted")
    if saved_run_id is None and prior.get("email_dispatch_at_utc"):
        raise RuntimeError("NCAA_EMAIL_RECONCILIATION_REQUIRED: earlier dispatch outcome is unknown")
    prior_attempt_ids = sorted(by_id)
    intent = {
        **prior,
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
        known = by_id.get(int(saved_run_id)) if saved_run_id is not None else None
        if known is not None and known.get("status") == "completed":
            # Provider-accepted evidence can survive a failed subsequent action.
            # Missing evidence leaves the outcome unknown and blocks resending.
            workflow = known
        else:
            workflow = wait_for_ncaaf_workflow(
                request,
                int(saved_run_id) if saved_run_id is not None else None,
                excluded_run_ids=set(prior_attempt_ids) if saved_run_id is None else None,
            )
        evidence = preserve_ncaaf_email_evidence(request, workflow)
    except Exception as error:
        failed = {
            **intent,
            "status": publication_status + "_EMAIL_RECONCILIATION_REQUIRED",
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


def prepare_due_ncaaf_records() -> list[dict[str, Any]]:
    """Prepare shared output without writing any sport's authority or queue."""
    state = NCAAF_QUEUE.parent
    outcomes = []
    for path in sorted((state / 'grader_completion_state').glob('????-??-??.json')):
        record = load_json(path)
        # Preserve explicit historical dispositions; these are not pending
        # requests under the newer shared-handoff schema.
        if record.get('historical_migration') == 'OWNER_LOCKED_COMPLETE_NO_RECOMPUTE_NO_REDELIVERY':
            continue
        if (record.get('completion_disposition') == 'NOT_APPLICABLE_NO_SEALED_ISSUANCE'
                and record.get('grade_count') == 0 and record.get('final_grade_count') == 0):
            continue
        if not record.get('PRODUCTS_COMPLETE') or record.get('RESULTS_SHARED_HANDOFF_COMPLETE'):
            continue
        try:
            output = run([sys.executable, str(ROOT / 'bin/apex_prepare_ncaaf_record.py'),
                          '--date', path.stem, '--state', str(state),
                          '--site-data', str(ROOT / 'data'),
                          '--output-root', str(STATE_ROOT / 'derived_results/ncaaf')],
                         cwd=ROOT, timeout=90)
            outcome = json.loads(output)
            if outcome.get('status') not in {'GENERATED_VERIFIED_ARTIFACT', 'REUSED_VERIFIED_ARTIFACT'}:
                raise RuntimeError('NCAA shared record producer did not verify its artifact')
        except Exception as error:
            outcome = {'status': 'BLOCKED', 'slate_date': path.stem,
                       'error': type(error).__name__ + ':' + str(error)[-1400:]}
        outcomes.append(outcome)
    atomic_json(STATE_ROOT / 'derived_results/ncaaf/preparation_status.json', {
        'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'outcomes': outcomes,
        'status': 'BLOCKED' if any(r['status'] == 'BLOCKED' for r in outcomes) else 'PASS'})
    return outcomes


def execute(*, dry_run: bool, sport: str | None = None) -> dict[str, Any]:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open('a+') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        results=[]
        try:
            prepared=prepare_due_ncaaf_records() if not dry_run and sport is None else []
        except Exception as error:
            prepared=[{'status':'PREPARATION_FAILED','error':str(error)}]
        pending=discover_nfl() if sport=='NFL' else discover_isolated()
        for request in pending:
            try:
                result=publish(request,dry_run=dry_run)
                if not dry_run:
                    result['published_at_utc']=datetime.now(timezone.utc).isoformat()
                    if request.sport=='NFL':
                        result=verify_nfl_publication(request,result)
                    if request.sport=='NCAAF':
                        result=dispatch_ncaaf_email(request,result)
                    else:
                        atomic_json(receipt_path(request),result)
                        if request.sport=='NFL':nfl_boundary('PUBLISH_RECEIPT_DURABLE',receipt_path(request))
                results.append(result)
            except Exception as error:
                failure={'status':'REQUEST_FAILED','sport':request.sport,'request_id':request.request_id,
                         'error':type(error).__name__+':'+str(error),'at':datetime.now(timezone.utc).isoformat()}
                if not dry_run:
                    failure_root=STATE_ROOT/'failures'/request.sport.lower()/request.request_id
                    failure_root.mkdir(parents=True,exist_ok=True)
                    atomic_json(failure_root/(str(time.time_ns())+'.json'),failure)
                results.append(failure)
        return {'status':'PASS' if results and all(r['status']!='REQUEST_FAILED' for r in results) else
                'PARTIAL_FAILURE' if results else 'NO_PENDING_REQUEST','requests':results,'shared_results_preparation':prepared}


def discover_isolated():
    now=datetime.now(NY).date()
    requests=[]
    for sport,fn in [('NCAAF',lambda:discover_ncaaf(now.isoformat(),(now-timedelta(days=1)).isoformat())),
                     ('MMA',discover_mma),('NFL',discover_nfl)]:
        try:requests.extend(fn())
        except Exception as error:
            requests.append(Request(sport,'discovery',{'discovery_error':str(error)},None))
    return requests


def build_nfl_grader(request, worktree):
    sys.path.insert(0,'/opt/apex_nfl/src')
    from apex_nfl.sealed_results import read, canonical
    from apex_nfl.grader_products import summarize
    queue=request.manifest;pointer=queue['canonical_result'];payload=read(pointer)
    expected=hashlib.sha256(canonical({'stage':'GRADER','slate_date':queue['slate_date'],'canonical_result':pointer})).hexdigest()
    if request.request_id!=expected or queue.get('status')!='QUEUED':raise RuntimeError('GRADER_REQUEST_BINDING')
    products=queue['products']
    if products.get('canonical_result')!=pointer:raise RuntimeError('GRADER_PRODUCT_BINDING')
    for field in ('pdf','png1','png2','cumulative_json'):
        path=Path(products[field])
        if not contained(path,Path('/var/opt/apex_nfl/grades/products')) or sha256_file(path)!=products[field+'_sha256']:
            raise RuntimeError('GRADER_PRODUCT_HASH:'+field)
    # Advance the NFL schedule in the same publication as the accepted grader.
    # Board-only output preserves the detailed results surface and sealed rows.
    run([sys.executable, str(worktree / 'bin/build_nfl_public_payload.py'),
         '--output-root', str(worktree), '--board-only'], cwd=worktree)
    rows=payload['rows'];cumulative=summarize(rows);cumulative['canonical_result']=pointer
    previous=worktree/'data/nfl_results_archive.json'
    if previous.exists():
        old=load_json(previous)
        old_rows=old.get('rows',[])
        if not old_rows:
            old_rows=[dict(r,issuance_id=g.get('issuance_id'),sport='NFL') for g in old.get('grades',[]) for r in g.get('settlements',[])]
        incoming={(r['sport'],r['issuance_id'],r['position_id']):r for r in rows}
        for row in old_rows:
            key=(row.get('sport','NFL'),row.get('issuance_id'),row['position_id'])
            if key not in incoming or incoming[key]['result']!=row['result']:
                raise RuntimeError('NFL_RESULT_REGRESSION_OR_CONFLICT')

    issued=sum(c['issued'] for c in payload['coverage'].values())
    record=cumulative['season_record']
    summary={'schema_version':'APEX_NFL_RESULTS_SUMMARY_V1','sport':'NFL','canonical_result':pointer,
             'coverage':payload['coverage'],'graded_position_count':len(rows),'issued_position_count':issued,
             'ungraded_position_count':issued-len(rows),'record':{'wins':record['W'],'losses':record['L'],'pushes':record['PUSH'],'voids':record['VOID']}}
    archive={'schema_version':'APEX_NFL_RESULTS_ARCHIVE_V2','sport':'NFL','canonical_result':pointer,
             'rows':rows,'coverage':payload['coverage'],'pending':payload['pending'],'cumulative':cumulative}
    for name,value in [('nfl_results_summary.json',summary),('nfl_results_archive.json',archive)]:
        atomic_json(worktree/'data'/name,value)
    # Install only the NFL renderer in this same publisher-owned source commit.
    renderer='nfl/results/render.js'
    shutil.copy2(ROOT/renderer,worktree/renderer)
    changed=dirty_paths(worktree)
    surfaces={'data/nfl_results_summary.json','data/nfl_results_archive.json',renderer,
              'data/nfl_today.json','data/nfl_system_state.json','nfl/index.html'}
    if not changed<=surfaces:raise RuntimeError('GRADER_UNOWNED_SITE_WRITE')
    return {'changed_paths':sorted(changed),'canonical_result':pointer,
            'nfl_surface_hashes':{name:sha256_file(worktree/name) for name in surfaces},'audit_tail':'canonical sealed result rows only'}


def verify_nfl_publication(request, result):
    import urllib.request
    sys.path.insert(0,'/opt/apex_nfl/src')
    from apex_nfl.acceptance_boundary import context
    isolated=context()
    if isolated:
        # A real local Git origin and HTTP service exercise isolated publication.
        # No Vercel/production deployment or live-domain PASS is invented here.
        worktree=STATE_ROOT/'worktrees'/('nfl-'+request.request_id)
        rows=[]
        for name,expected in result['nfl_surface_hashes'].items():
            with urllib.request.urlopen('http://127.0.0.1:18913/'+worktree.name+'/'+name,timeout=20) as response:
                actual=hashlib.sha256(response.read()).hexdigest()
                if response.status!=200 or actual!=expected:raise RuntimeError('ISOLATED_HTTP_BYTES_CHANGED')
                rows.append({'path':name,'sha256':actual,'http_status':200})
        result['isolated_readback']={'status':'PASS','surfaces':rows,'external_publications':0,'actual_git_commit':result['published_commit']}
        nfl_boundary('PUBLISH_ISOLATED_HTTP_VERIFIED')
        return result
    # GitHub deployment evidence must name this exact source commit and a successful production deployment.
    raw=git_deployment(result['published_commit'], result['nfl_surface_hashes'], request.request_id)
    surfaces=[]
    for name,expected in result['nfl_surface_hashes'].items():
        url='https://apexrigor.com/'+('nfl/' if name=='nfl/index.html' else name)
        with urllib.request.urlopen(urllib.request.Request(url,headers={'Cache-Control':'no-cache'}),timeout=20) as response:
            actual=hashlib.sha256(response.read()).hexdigest()
            if response.status!=200 or actual!=expected:raise RuntimeError('LIVE_BYTES_PENDING:'+name)
            surfaces.append({'url':url,'sha256':actual,'http_status':200})
    result['deployment']=raw
    # Re-resolve the canonical alias after HTTP reads to reject an in-flight deployment switch.
    current=vercel_deployment()
    if current.get('id')!=raw['id'] or current.get('meta',{}).get('githubCommitSha')!=raw['sha']:
        raise RuntimeError('PRODUCTION_ALIAS_CHANGED_DURING_READBACK')
    result['live_readback']={'status':'PASS','published_commit':result['published_commit'],
                             'deployed_commit':raw['sha'],'deployment_id':raw['id'],'surfaces':surfaces}
    nfl_boundary('PUBLISH_PRODUCTION_LIVE_VERIFIED')
    return result


def vercel_deployment():
    import urllib.request
    credentials=load_json(Path('/root/.local/share/com.vercel.cli/auth.json'))
    token=credentials.get('token') or credentials.get('accessToken')
    if not token:raise RuntimeError('EXISTING_VERCEL_READ_CREDENTIAL_UNAVAILABLE')
    url='https://api.vercel.com/v13/deployments/apexrigor.com?teamId=team_ZbMl7Z31fLqnzoCYHAY2a1rk&withGitRepoInfo=true'
    with urllib.request.urlopen(urllib.request.Request(url,headers={'Authorization':'Bearer '+token}),timeout=30) as response:
        return json.load(response)


def deployment_proof(d, commit, surface_hashes=None, request_id=None, *, repo=None):
    """An alias may advance for another sport only with unchanged request-bound NFL bytes."""
    import re
    repo=ROOT if repo is None else Path(repo)
    meta=d.get('meta',{});deployed=meta.get('githubCommitSha')
    if (d.get('readyState')!='READY' or d.get('target')!='production' or
        d.get('projectId')!='prj_eZTtqClkwx7IcE7NhVAK6UFmBnnB' or
        'apexrigor.com' not in d.get('alias',[]) or
        meta.get('githubCommitOrg')!='scole12' or meta.get('githubCommitRepo')!='apexrigor' or
        meta.get('githubCommitRef')!='main' or not re.fullmatch(r'[0-9a-f]{40}',str(commit)) or
        not re.fullmatch(r'[0-9a-f]{40}',str(deployed))):
        raise RuntimeError('CANONICAL_PRODUCTION_DEPLOYMENT_REQUIRED:'+str(commit))
    if deployed!=commit and (not surface_hashes or not request_id):
        raise RuntimeError('DESCENDANT_REQUIRES_REQUEST_BOUND_SURFACES')
    ancestry=subprocess.run(['git','merge-base','--is-ancestor',commit,deployed],cwd=repo,
                            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
    if ancestry.returncode!=0:raise RuntimeError('DEPLOYMENT_NOT_REQUEST_DESCENDANT')
    verified={}
    for name,expected in sorted((surface_hashes or {}).items()):
        if safe_relative(name)!=name or not (name.startswith('data/nfl_') or name.startswith('nfl/')):
            raise RuntimeError('INVALID_NFL_SURFACE:'+name)
        if not re.fullmatch(r'[0-9a-f]{64}',str(expected)):raise RuntimeError('INVALID_SURFACE_HASH')
        hashes={}
        for role,ref in [('request',commit),('deployment',deployed)]:
            raw=subprocess.check_output(['git','show',ref+':'+name],cwd=repo,timeout=30)
            hashes[role]=hashlib.sha256(raw).hexdigest()
        # SOFT_ROLLING_RESULTS: do not block T2/T3 email on rolling results drift.
        if name in ('data/nfl_results_summary.json', 'data/nfl_results_archive.json'):
            verified[name]={'expected_sha256':expected,'request_sha256':hashes['request'],
                            'deployment_sha256':hashes['deployment'],'gate':'SOFT_ROLLING_RESULTS'}
            continue
        if hashes['request']!=expected or hashes['deployment']!=expected:
            raise RuntimeError('REQUEST_BOUND_NFL_SURFACE_CHANGED:'+name)
        verified[name]={'expected_sha256':expected,'request_sha256':hashes['request'],
                        'deployment_sha256':hashes['deployment']}
    return {'id':d['id'],'project_id':d['projectId'],'sha':deployed,'request_commit':commit,
            'request_id':request_id,'target':'production','ready_state':'READY',
            'alias':'apexrigor.com','url':d['url'],
            'binding':'EXACT_COMMIT' if deployed==commit else 'VERIFIED_DESCENDANT_UNCHANGED_NFL',
            'ancestry':{'ancestor':commit,'descendant':deployed,'merge_base_is_ancestor_exit':0},
            'request_bound_surfaces':verified}


def git_deployment(commit, surface_hashes=None, request_id=None):
    if request_id:
        intent=load_json(STATE_ROOT/'publication_intents/nfl'/(safe_relative(request_id)+'.json'))
        if (intent.get('phase')!='PUSHED' or intent.get('request_id')!=request_id or
            intent.get('published_commit')!=commit or
            intent.get('build',{}).get('nfl_surface_hashes')!=surface_hashes):
            raise RuntimeError('DURABLE_NFL_REQUEST_COMMIT_SURFACE_BINDING')
    return deployment_proof(vercel_deployment(),commit,surface_hashes,request_id)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--sport", choices=("NFL",))
    arguments = parser.parse_args()
    try:
        print(json.dumps(execute(dry_run=arguments.dry_run, sport=arguments.sport), indent=2, sort_keys=True))
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
