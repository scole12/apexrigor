"""Fresh Claude Code review (#23, step 6): load the site tree under review.

APEX_REVIEW_ROOT may point at another apexrigor checkout; by default the tests
review the tree they are committed in. Nothing is written into that tree.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

_COUNTER = [0]


def review_root() -> Path:
    raw = os.environ.get("APEX_REVIEW_ROOT")
    return Path(raw) if raw else Path(__file__).resolve().parents[2]


def git(*args: str, cwd: Path) -> str:
    done = subprocess.run(["git", *args], cwd=str(cwd), check=True, text=True, capture_output=True)
    return done.stdout.strip()


def site_copy(destination: Path) -> Path:
    """Committed bytes of the reviewed tree (LF, no public/), as a fresh one-commit repo."""
    destination.mkdir(parents=True)
    archive = subprocess.run(
        ["git", "-c", "core.autocrlf=false", "archive", "HEAD"],
        cwd=str(review_root()), check=True, capture_output=True,
    )
    subprocess.run(["tar", "-x", "-C", str(destination)], input=archive.stdout, check=True)
    git("init", "-q", "-b", "main", cwd=destination)
    git("config", "user.name", "Job 1 fresh review", cwd=destination)
    git("config", "user.email", "job1-review@example.invalid", cwd=destination)
    git("config", "commit.gpgsign", "false", cwd=destination)
    git("add", "-A", cwd=destination)
    git("commit", "-q", "-m", "reviewed tree", cwd=destination)
    return destination


def load_publisher():
    path = review_root() / "bin" / "apex_shared_site_publisher.py"
    _COUNTER[0] += 1
    spec = importlib.util.spec_from_file_location(f"publisher_fresh_review_{_COUNTER[0]}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def vercel_build(site: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(site / "bin" / "build_vercel_output.py")],
        check=False, cwd=str(site), capture_output=True, text=True, timeout=900,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
