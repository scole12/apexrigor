"""#23 chain replay: T-3, T-2 and the grader on each failing game day, under systemd's retry rules.

Each day replays its recorded failure signature (journal, Oct 6-20) through the real stage runner
(apex_ncaaf_stages) with a pinned clock and Restart=on-failure semantics: an attempt that raises
is retried after RestartSec, exit 78 (StageWindowClosed) ends the unit. Engines, providers, the
shared publisher and email are stand-ins; the decisions under test are the runner's windows,
retries and late paths, plus the real hydration helpers named per day.
Kickoff times are representative of each day's first game, not exact.
"""
import json

import pytest

import support
from support import game, grader_event, ms

T3_RESTART_MS = 5 * 60000
GRADER_RESTART_MS = 15 * 60000


class Unit:
    """Restart=on-failure until success or exit 78, like the apex-ncaaf-* services."""

    def __init__(self, stages, monkeypatch):
        self.stages, self.monkeypatch = stages, monkeypatch

    def run(self, stage, start_ms, restart_ms, limit_ms):
        moment = start_ms
        attempts = []
        while moment <= limit_ms:
            self.monkeypatch.setenv("APEX_NCAAF_NOW_MS", str(moment))
            try:
                self.stages.run_stage(stage)
                attempts.append((moment, "PASS"))
                return attempts
            except self.stages.StageWindowClosed as exc:
                attempts.append((moment, "EXIT_78:" + str(exc)))
                return attempts
            except Exception as exc:  # noqa: BLE001 - Restart=on-failure
                attempts.append((moment, type(exc).__name__ + ":" + str(exc)[:80]))
            moment += restart_ms
        return attempts


DAYS = {
    # day: (first kickoff ET hour, minute, injected faults)
    "2026-10-06": (19, 30, {"score_conflict", "late_finals"}),
    "2026-10-09": (19, 0, {"stale_roster_correction", "player_budget", "late_finals"}),
    "2026-10-10": (12, 0, {"stale_roster_correction", "delivery_wait"}),
    "2026-10-13": (19, 30, {"player_budget"}),
    "2026-10-15": (19, 30, {"engine_rebind", "late_finals"}),
    "2026-10-17": (12, 0, {"non_card_file", "late_finals"}),
    "2026-10-18": (12, 0, {"non_card_file"}),
    "2026-10-20": (19, 0, {"delivery_wait", "parity"}),
}


@pytest.mark.parametrize("day", sorted(DAYS))
def test_t3_t2_grader_chain_completes(day, tmp_path, monkeypatch):
    hour, minute, faults = DAYS[day]
    stages, fake = support.load_stages(tmp_path)
    monkeypatch.setattr(stages, "alert", lambda code, detail: None)
    kick = ms(day, hour, minute)
    fake.schedules[day] = [game("g1", kick), game("g2", kick + 3 * 3600000)]
    t3 = fake.T3_ROOT / f"{day}.json"
    issuance = fake.ISSUANCE_ROOT / day / "slate.json"
    state = {"t3_attempts": 0, "delivered": set()}

    def execute_event(event, stage, result, late=False):
        if stage == "T3":
            if not t3.is_file():
                state["t3_attempts"] += 1
                hydrate_t3(day, faults, state, tmp_path, monkeypatch)
                support.write_json(t3, {"status": "PASS", "slate_date_et": day})
            if "delivery_wait" in faults and stages.now_ms() < event["event_utc_ms"] + 45 * 60000:
                # Oct 10/20: sealed, but the shared publisher receipt is not there yet.
                raise RuntimeError("RESULTS_SHARED_CONFIRMATION:WAITING_FOR_SHARED_PUBLISHER_RECEIPT")
            state["delivered"].add("T3")
        else:
            if "engine_rebind" in faults:
                gate_passes(tmp_path)
            assert t3.is_file(), "T-2 needs the sealed T-3"
            support.write_json(issuance, {"slate_date_et": day, "games": [
                {"game_id": "g1", "card": {"game_id": "g1", "issuance_id": "i1", "kickoff_utc_ms": kick,
                                           "positions": [{"market_type": "ATS"}, {"market_type": "TOTALS"}]}}]})
            state["delivered"].add("T2")

    def due(stage):
        if stage == "GRADER":
            return [] if day in fake.complete else [grader_event(day)]
        return [e for e in fake.plan_for_slate(day)["events"] if e["event_type"] == stage
                and stages.now_ms() >= e["event_utc_ms"] and stage not in state["delivered"]]

    monkeypatch.setattr(stages, "execute_event", execute_event)
    monkeypatch.setattr(stages, "due_events", due)
    unit = Unit(stages, monkeypatch)

    if "parity" in faults:
        check_rearm_holds_catalog(stages, fake, monkeypatch, tmp_path, ms(day, 10, 5))

    t3_runs = unit.run("T3", kick - 3 * 3600000, T3_RESTART_MS, kick)
    assert t3_runs[-1][1] == "PASS", t3_runs
    t2_runs = unit.run("T2", kick - 2 * 3600000, T3_RESTART_MS, kick)
    assert t2_runs[-1][1] == "PASS", t2_runs
    assert {"T3", "T2"} <= state["delivered"]

    final_at = kick + 3 * 3600000 + 4 * 3600000 + (9 * 3600000 if "late_finals" in faults else 0)  # past the old 11:00 close

    def advance_grader(event):
        fake.graded.append(event["slate_date_et"])
        cards = load_cards(fake, day, faults)
        if stages.now_ms() >= final_at and cards:
            fake.complete.add(day)
        else:
            fake.grader_states[day] = {"slate_date_et": day, "GRADES_COMPLETE": False, "pending_grade_count": 1}
        return {"status": "ADVANCED"}
    fake.advance_grader = advance_grader
    morning = (support.datetime.fromisoformat(day).date() + support.timedelta(days=1)).isoformat()
    grader_runs = unit.run("GRADER", ms(morning, 7), GRADER_RESTART_MS, ms(morning, 23, 59))
    assert grader_runs[-1][1] == "PASS", grader_runs
    assert day in fake.complete


def hydrate_t3(day, faults, state, tmp_path, monkeypatch):
    """The real hydration helpers for the day's recorded fault."""
    if "stale_roster_correction" in faults:
        import ncaaf_roster_corrections
        ncaaf_roster_corrections.verify_applied(
            [{"provider_native_player_id": "5212990", "attested_team_label": "Georgia State"}],
            {}, {"g1-H": "Home", "g1-A": "Away"})
    if "score_conflict" in faults:
        from test_cause3_4_8_hydration import ROWS, hist_db
        import ncaaf_current_stats_sync as base
        assert set(base.completed_schedule(hist_db(ROWS), 2026, [])) == {"401868001"}
    if "player_budget" in faults and state["t3_attempts"] == 1:
        # First attempt runs out of budget; its fetched weeks are kept and the retry resumes.
        raise RuntimeError("PLAYER_ENDPOINT_SOURCE_DEADLINE_BUDGET_EXHAUSTED")


def gate_passes(tmp_path):
    import subprocess
    import sys
    run = subprocess.run([sys.executable, str(support.REPO / "tools/ncaaf_deploy_gate.py"), "--allow-absent"],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stdout


def load_cards(fake, day, faults):
    import ncaaf_issuance_schema
    if "non_card_file" in faults:
        support.write_json(fake.ISSUANCE_ROOT / day / "public_rating_reference_v3.json", {"policy": "V3"})
        support.write_json(fake.ISSUANCE_ROOT / day / "rating_reference_v4.json", {"policy": "V4"})
    return ncaaf_issuance_schema.load_issuance_cards(day, fake.ISSUANCE_ROOT)


def check_rearm_holds_catalog(stages, fake, monkeypatch, tmp_path, moment):
    import sys
    monkeypatch.setenv("APEX_NCAAF_NOW_MS", str(moment))
    receipt = support.write_json(tmp_path / "parity.json", {"unproven_extra_current_ids": []})
    living = type(sys)("ncaaf_t3_living_write")

    def refresh(season_year):
        raise RuntimeError("SCHEDULE_CATALOG_REVERSE_PARITY_FAILED:" + str(receipt))
    living.refresh_schedule_catalog = refresh
    monkeypatch.setitem(sys.modules, "ncaaf_t3_living_write", living)
    for name, value in {"rearm_conflict": lambda moment_ms=None: None, "confirm_results_deliveries": lambda: [],
                        "sweep_before_t3": lambda started: None, "prefetch_market_history": lambda: [],
                        "refill_before_t3": lambda started: None, "living_rows": lambda d: [],
                        "plan_horizon": lambda: {"status": "PASS", "failures": [], "plans": [], "generated_at_utc": "x"},
                        "calendar_lines": lambda plans, stage: ["2099-01-01 00:00:00 America/New_York"],
                        "systemctl": lambda *a: ""}.items():
        monkeypatch.setattr(stages, name, value)
    monkeypatch.setattr(stages, "UNIT_ROOT", tmp_path)
    stages.rearm(refresh=True)
    assert json.loads((stages.ROOT / "schedule_refresh.json").read_text())["status"] == "HELD_LAST_GOOD_CATALOG"
