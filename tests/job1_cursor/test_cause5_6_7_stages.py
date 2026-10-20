"""#23 causes 5, 6 and 7, plus the results-email interface pin (cause 1d, apex_ncaaf side).

Cause 5 (Oct 15): every T-2 card failed after an engine change left the champion binding
behind ("ATS champion implementation binding mismatch").
Cause 6 (Oct 19-20): SCHEDULE_CATALOG_REVERSE_PARITY_FAILED stopped every hourly rearm.
Cause 7 (Oct 20): T3_WINDOW_CLOSED at 16:41 although T-3 was sealed and only its delivery was
waiting on the shared publisher, and T-2 had not issued.
"""
import json
import shutil
import subprocess
import sys

import pytest

import support
from support import game, ms

GATE = support.REPO / "tools" / "ncaaf_deploy_gate.py"


# --- cause 5: deploy gate ---------------------------------------------------------------------
def copy_release(tmp_path):
    target = tmp_path / "release"
    for relative in ("RELEASE.json", "FILE_MANIFEST.sha256", "models", "runtime", "production", "evidence"):
        source = support.RELEASE / relative
        if source.is_dir():
            shutil.copytree(source, target / relative, ignore=shutil.ignore_patterns("__pycache__"))
        elif source.is_file():
            target.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target / relative)
    return target


def gate(release):
    return subprocess.run([sys.executable, str(GATE), "--release", str(release), "--allow-absent"],
                          capture_output=True, text=True)


def test_checked_in_release_passes_the_deploy_gate():
    run = gate(support.RELEASE)
    assert run.returncode == 0, run.stdout + run.stderr
    assert json.loads(run.stdout)["status"] == "PASS"


def test_engine_change_without_rebinding_is_refused(tmp_path):
    release = copy_release(tmp_path)
    controller = release / "runtime" / "apex_ncaaf_controller.py"
    controller.write_bytes(controller.read_bytes() + b"\n# unbound change\n")
    run = gate(release)
    report = json.loads(run.stdout)
    assert run.returncode == 1
    assert any(f.startswith("ATS_IMPLEMENTATION_BINDING_MISMATCH") for f in report["failures"])
    assert any(f.startswith("TOTALS_IMPLEMENTATION_BINDING_MISMATCH") for f in report["failures"])


def test_changed_runtime_file_outside_the_manifest_is_refused(tmp_path):
    release = copy_release(tmp_path)
    path = release / "runtime" / "ncaaf_roster_corrections.py"
    path.write_bytes(path.read_bytes() + b"\n")
    report = json.loads(gate(release).stdout)
    assert "FILE_MANIFEST_MISMATCH:runtime/ncaaf_roster_corrections.py" in report["failures"]


# --- stage runner fixtures --------------------------------------------------------------------
@pytest.fixture
def stage(tmp_path, monkeypatch):
    stages, fake = support.load_stages(tmp_path)
    alerts = []
    monkeypatch.setattr(stages, "alert", lambda code, detail: alerts.append((code, detail)))

    def at(moment_ms):
        monkeypatch.setenv("APEX_NCAAF_NOW_MS", str(moment_ms))
    return stages, fake, at, alerts


DAY = "2026-10-20"
KICK = ms(DAY, 19, 0)            # T-3 16:00, T-3 last attempt 16:35, T-2 17:00


def t3_event(fake):
    return next(e for e in fake.plan_for_slate(DAY)["events"] if e["event_type"] == "T3")


def run_t3(stages, fake, monkeypatch):
    calls = []
    monkeypatch.setattr(stages, "due_events", lambda stage: [t3_event(fake)])
    monkeypatch.setattr(stages, "execute_event", lambda event, stage, result, late=False: calls.append(late))
    return stages.run_stage("T3"), calls


# --- cause 7 ----------------------------------------------------------------------------------
def test_unsealed_t3_runs_late_until_t2_cutoff(stage, monkeypatch):
    stages, fake, at, _ = stage
    fake.schedules[DAY] = [game("g", KICK)]
    at(ms(DAY, 16, 41))
    result, calls = run_t3(stages, fake, monkeypatch)
    assert calls == [True] and result["window_mode"][DAY] == "LATE"
    marker = json.loads((stages.ROOT / f"t3_late_{DAY}.json").read_text())
    assert marker["late"] is True


def test_no_late_t3_after_t2_cutoff_or_once_t2_issued(stage, monkeypatch):
    stages, fake, at, _ = stage
    fake.schedules[DAY] = [game("g", KICK)]
    at(ms(DAY, 17, 1))
    with pytest.raises(stages.StageWindowClosed):
        run_t3(stages, fake, monkeypatch)
    at(ms(DAY, 16, 41))
    support.write_json(fake.ISSUANCE_ROOT / DAY / "slate.json", {"games": []})
    with pytest.raises(stages.StageWindowClosed):
        run_t3(stages, fake, monkeypatch)


def test_sealed_t3_delivery_continues_after_its_window(stage, monkeypatch):
    stages, fake, at, _ = stage
    fake.schedules[DAY] = [game("g", KICK)]
    support.write_json(fake.T3_ROOT / f"{DAY}.json", {"status": "PASS"})
    support.write_json(fake.ISSUANCE_ROOT / DAY / "slate.json", {"games": []})   # even after T-2
    at(ms(DAY, 18, 0))
    result, calls = run_t3(stages, fake, monkeypatch)
    assert calls == [False] and result["window_mode"][DAY] == "DELIVERY_ONLY"


# --- cause 6 ----------------------------------------------------------------------------------
def test_reverse_parity_failure_holds_last_good_catalog_and_rearm_continues(stage, monkeypatch, tmp_path):
    stages, fake, at, alerts = stage
    fake.schedules["2026-10-21"] = [game("cfbd-uuid-1", ms("2026-10-21", 19, 0))]
    at(ms(DAY, 13, 5))
    receipt = support.write_json(tmp_path / "parity.json", {"unproven_extra_current_ids": [
        {"provider_native_event_id": "401999001", "game_ids": ["cfbd-uuid-1"], "kickoff_utc_ms": [1]}]})
    living = type(sys)("ncaaf_t3_living_write")

    def refresh(season_year):
        raise RuntimeError("SCHEDULE_CATALOG_REVERSE_PARITY_FAILED:" + str(receipt))
    living.refresh_schedule_catalog = refresh
    monkeypatch.setitem(sys.modules, "ncaaf_t3_living_write", living)
    outcome_sync = type(sys)("ncaaf_completed_outcome_sync")
    outcome_sync.sync_missing_final_outcomes = lambda refreshed: pytest.fail("needs a PASS refresh")
    monkeypatch.setitem(sys.modules, "ncaaf_completed_outcome_sync", outcome_sync)
    monkeypatch.setattr(stages, "living_rows", lambda day: fake.schedules.get(day, []))
    monkeypatch.setattr(stages, "rearm_conflict", lambda moment_ms=None: None)
    monkeypatch.setattr(stages, "confirm_results_deliveries", lambda: [])
    monkeypatch.setattr(stages, "sweep_before_t3", lambda started: None)
    monkeypatch.setattr(stages, "prefetch_market_history", lambda: [])
    monkeypatch.setattr(stages, "refill_before_t3", lambda started: None)
    plan = {"status": "PASS", "failures": [], "plans": [], "generated_at_utc": "x"}
    monkeypatch.setattr(stages, "plan_horizon", lambda: dict(plan))
    monkeypatch.setattr(stages, "calendar_lines", lambda plans, stage: ["2026-10-21 16:00:00 America/New_York"])
    monkeypatch.setattr(stages, "systemctl", lambda *a: "")
    unit_root = tmp_path / "units"
    unit_root.mkdir()
    monkeypatch.setattr(stages, "UNIT_ROOT", unit_root)
    stages.rearm(refresh=True)
    held = json.loads((stages.ROOT / "schedule_refresh.json").read_text())
    assert held["status"] == "HELD_LAST_GOOD_CATALOG"
    assert held["affected_upcoming_game_ids"] == ["cfbd-uuid-1"]
    assert held["catalog_write_count"] == 0
    assert json.loads((stages.ROOT / "completed_outcome_sync.json").read_text())["status"] == "SKIPPED_SCHEDULE_CATALOG_HELD"
    assert [code for code, _ in alerts].count("SCHEDULE_CATALOG_PARITY_HOLD") == 1
    assert json.loads((stages.ROOT / "rearm_receipt.json").read_text())["status"] == "PASS"


def test_other_refresh_failures_still_fail_the_rearm(stage, monkeypatch):
    stages, fake, at, _ = stage
    at(ms(DAY, 13, 5))
    living = type(sys)("ncaaf_t3_living_write")
    living.refresh_schedule_catalog = lambda season_year: (_ for _ in ()).throw(RuntimeError("CFBD_SCHEDULE_SOURCE_REJECTED:regular:/x"))
    monkeypatch.setitem(sys.modules, "ncaaf_t3_living_write", living)
    monkeypatch.setattr(stages, "rearm_conflict", lambda moment_ms=None: None)
    with pytest.raises(RuntimeError, match="CFBD_SCHEDULE_SOURCE_REJECTED"):
        stages.rearm(refresh=True)


# --- cause 1d (apex_ncaaf side) ----------------------------------------------------------------
def test_results_email_declares_the_publisher_interface():
    import ncaaf_results_email as email
    assert email.INTERFACE_VERSION == "apex.ncaaf.results_email.v2"
    assert callable(email.delivery_lock) and callable(email.confirmed_email)
