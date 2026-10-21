"""Shared fixtures for the job 1 (#23) shared-publisher tests.

Temporary directories, local Git remotes and mocked Vercel/GitHub only: nothing is pushed to
GitHub, deployed, emailed or written outside a temp directory.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path

if sys.platform == "win32":
    _fcntl = sys.modules.get("fcntl")
    if _fcntl is None or not callable(getattr(_fcntl, "flock", None)):
        _fcntl = types.ModuleType("fcntl")
        _fcntl.flock = lambda *args, **kwargs: None
        _fcntl.LOCK_EX = 2
        _fcntl.LOCK_UN = 8
        sys.modules["fcntl"] = _fcntl

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / "bin"
PUBLISHER = BIN / "apex_shared_site_publisher.py"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

_COUNTER = [0]


def load_publisher(path: Path = PUBLISHER):
    _COUNTER[0] += 1
    spec = importlib.util.spec_from_file_location(f"publisher_job1_{_COUNTER[0]}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def git(*args, cwd) -> str:
    result = subprocess.run(["git", *args], cwd=str(cwd), check=True, text=True, capture_output=True)
    return result.stdout.strip()


def init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    git("init", "-q", "-b", "main", cwd=path)
    git("config", "user.name", "Job 1 test", cwd=path)
    git("config", "user.email", "job1@example.invalid", cwd=path)
    git("config", "commit.gpgsign", "false", cwd=path)
    return path


def commit_all(repo: Path, message: str) -> str:
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", message, cwd=repo)
    return git("rev-parse", "HEAD", cwd=repo)


def site_copy(target: Path) -> Path:
    """A Git repository holding this checkout's committed site files (HEAD)."""
    target.mkdir(parents=True, exist_ok=True)
    archive = subprocess.run(["git", "archive", "HEAD"], cwd=str(ROOT), check=True, capture_output=True)
    subprocess.run(["tar", "-x", "-C", str(target)], input=archive.stdout, check=True)
    # The working-tree versions of the files under test (this branch's fix, uncommitted edits included).
    for relative in ("bin/apex_shared_site_publisher.py", "bin/site_route_owners.py"):
        if (ROOT / relative).is_file():
            (target / relative).parent.mkdir(parents=True, exist_ok=True)
            (target / relative).write_bytes((ROOT / relative).read_bytes())
    init_repo(target)
    commit_all(target, "fixture site")
    return target


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True))
    return path


def deployment(sha_value: str) -> dict:
    return {"readyState": "READY", "target": "production", "alias": ["apexrigor.com"],
            "url": "apexrigor-test.vercel.app", "meta": {"githubCommitSha": sha_value}}
