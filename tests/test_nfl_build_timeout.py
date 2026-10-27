"""NFL build timeout is a per-request failure, and the sealed result is read once per build."""
import importlib.util
import subprocess
import sys
import types
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parents[1] / "bin"


def _load(name):
    sys.path.insert(0, str(BIN))
    spec = importlib.util.spec_from_file_location(name, BIN / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_nfl_build_timeout_is_request_scoped_not_global(monkeypatch):
    publisher = _load("apex_shared_site_publisher")
    assert publisher.NFL_BUILD_TIMEOUT == 900
    monkeypatch.setattr(publisher, "NFL_BUILD_TIMEOUT", 1)
    command = [sys.executable, "/x/bin/build_nfl_public_payload.py", "--output-root", "/x", "--board-only"]
    real_run = subprocess.run

    def slow(cmd, **kwargs):
        return real_run([sys.executable, "-c", "import time; time.sleep(30)"], **kwargs)

    monkeypatch.setattr(subprocess, "run", slow)
    with pytest.raises(publisher.NflBuildTimeout) as caught:
        publisher.run_nfl_build(command, cwd=Path("/tmp"))
    text = type(caught.value).__name__ + ":" + str(caught.value)
    assert "NFL_BUILD_TIMEOUT" in text and "--board-only" in text
    assert not publisher._is_global_fault(text)
    assert not publisher._is_wait_error(text)
    # A real subprocess timeout elsewhere (git/GitHub) still classifies as a global fault.
    assert publisher._is_global_fault("TimeoutExpired:Command 'git push' timed out after 180 seconds")


def test_results_payload_reads_sealed_result_once(monkeypatch):
    payload = _load("build_nfl_public_payload")
    reads = []
    row = {"result": "WIN", "log_loss": 0.5, "brier": 0.25}
    sealed = {"rows": [row], "coverage": {"2026-10-25": {"issued": 2}}, "pending": []}
    module = types.ModuleType("apex_nfl.sealed_results")
    module.ROOT = Path("/nonexistent")
    module.load = lambda path: {"path": "p", "sha256": "h"}
    module.read = lambda pointer=None: (reads.append(pointer), sealed)[1]
    products = types.ModuleType("apex_nfl.grader_products")
    products.summarize = lambda rows: {"season_record": {"W": 1, "L": 0, "PUSH": 0, "VOID": 0}}
    package = types.ModuleType("apex_nfl")
    monkeypatch.setitem(sys.modules, "apex_nfl", package)
    monkeypatch.setitem(sys.modules, "apex_nfl.sealed_results", module)
    monkeypatch.setitem(sys.modules, "apex_nfl.grader_products", products)
    results, archive = payload.build_results_payloads("READY", "2026-10-26T00:00:00Z", 2)
    assert len(reads) == 1
    assert results["record"] == {"wins": 1, "losses": 0, "pushes": 0, "voids": 0}
    assert results["graded_position_count"] == 1 and results["issued_position_count"] == 2
    assert archive["rows"] == [row] and archive["canonical_result"] == results["canonical_result"]
