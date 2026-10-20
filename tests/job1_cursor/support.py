"""Shared fixtures for the job 1 (#23) regression tests.

Everything runs on temporary roots with fixed clocks: no production state, no network,
no email. The stage runner is loaded with an in-memory stand-in for apex_ncaaf_gameday,
because the real one needs the droplet's authorities and frozen champion files.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
RELEASE = REPO / "releases" / "apex-ncaaf-20260919-location-policy-v30"
RUNTIME = RELEASE / "runtime"
PRODUCTION = RELEASE / "production"
OPERATIONS = REPO / "operations"
NY = ZoneInfo("America/New_York")

os.environ.setdefault("APEX_NCAAF_NOTIFY_DISABLE", "1")
os.environ["APEX_NCAAF_RUNTIME_DIR"] = str(RUNTIME)
os.environ["APEX_NCAAF_OPT_ROOT"] = str(RELEASE)
for path in (str(OPERATIONS), str(RUNTIME), str(PRODUCTION)):
    if path not in sys.path:
        sys.path.insert(0, path)


def ms(day: str, hour: int, minute: int = 0) -> int:
    """Epoch ms for an America/New_York wall-clock time."""
    moment = datetime.fromisoformat(day).replace(hour=hour, minute=minute, tzinfo=NY)
    return int(moment.timestamp() * 1000)


def utc_ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def write_json(path: Path, value) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True))
    return path


class FakeGameday(types.ModuleType):
    """The attributes of apex_ncaaf_gameday that the stage runner reads."""

    T2_PREPARATION_WINDOW_MS = 3 * 60000

    def __init__(self, root: Path):
        super().__init__("apex_ncaaf_gameday")
        self.NY = NY
        self.STATE = root / "production"
        self.T3_ROOT = self.STATE / "t3"
        self.ISSUANCE_ROOT = self.STATE / "issuance"
        self.GRADER_STATE_ROOT = self.STATE / "grader_completion_state"
        self.PLAN_ROOT = self.STATE / "event_plans"
        self.EVENT_ROOT = self.STATE / "event_receipts"
        self.TEAM = root / "TEAM_LINEUP.db"
        self.FULL_SLATE_OPERATOR = root / "full_slate_operator.py"
        self.RELEASE_FULL_SLATE = root / "release_full_slate.py"
        self.schedules: dict[str, list[dict]] = {}
        self.grader_states: dict[str, dict] = {}
        self.complete: set[str] = set()
        self.graded: list[str] = []
        self.grader_events: list[dict] = []

    # time
    def utc_ms(self, moment):
        return utc_ms(moment)

    def nominal_event_utc_ms(self, event):
        return int(event.get("nominal_event_utc_ms") or event["event_utc_ms"])

    # schedule and plan (first kickoff K: T-3 at K-3h, T-2 at K-2h, grader 07:00 next day)
    def slate_schedule_rows_any_status(self, day):
        return list(self.schedules.get(day, []))

    def slate_schedule_rows(self, day):
        return list(self.schedules.get(day, []))

    def plan_for_slate(self, day):
        rows = self.schedules.get(day, [])
        events = []
        if rows:
            kick = min(int(r["kickoff_utc_ms"]) for r in rows)
            for stage, offset in (("T3", 3), ("T2", 2)):
                events.append({"event_type": stage, "event_utc_ms": kick - offset * 3600000,
                               "slate_date_et": day, "kickoff_utc_ms": kick,
                               "timing_anchor_kickoff_utc_ms": kick, "game_id": None})
        return {"slate_date_et": day, "game_count": len(rows), "t3_event_count": int(bool(rows)),
                "t2_event_count": int(bool(rows)), "grader_event_count": int(bool(rows)),
                "unresolved_kickoff_game_count": 0, "events": events}

    def event_receipt_path(self, event):
        return self.EVENT_ROOT / event["slate_date_et"] / f"{event['event_type']}_{event['event_utc_ms']}.json"

    # grader
    def prior_incomplete_grader_events(self, moment):
        return list(self.grader_events)

    def load_grader_state(self, day, root=None):
        return dict(self.grader_states.get(day, {"slate_date_et": day}))

    def grader_complete(self, day, root=None):
        return day in self.complete

    def advance_grader(self, event):
        self.graded.append(event["slate_date_et"])
        return {"slate_date_et": event["slate_date_et"], "status": "ADVANCED"}

    def t2_issuance_absent(self, day):
        return not (self.ISSUANCE_ROOT / day / "slate.json").is_file()

    def record_grader_terminal_failure(self, day, failure, root=None):
        return {"slate_date_et": day, "terminal_failure": failure}

    # storage
    def atomic_status(self, path, value):
        write_json(Path(path), value)


def grader_event(day: str) -> dict:
    nominal = ms((datetime.fromisoformat(day).date() + timedelta(days=1)).isoformat(), 7)
    return {"event_type": "GRADER", "event_utc_ms": nominal, "nominal_event_utc_ms": nominal,
            "slate_date_et": day, "game_id": None, "idempotency_key": day + "|GRADER"}


def game(game_id: str, kickoff_ms: int, **extra) -> dict:
    return {"game_id": game_id, "kickoff_utc_ms": kickoff_ms, "home_team_id": game_id + "-H",
            "away_team_id": game_id + "-A", "season": 2026, "game_status": "SCHEDULED", **extra}


_COUNTER = [0]


def load_stages(root: Path, fake: FakeGameday | None = None):
    """apex_ncaaf_stages from this checkout, bound to a FakeGameday under ``root``."""
    fake = fake or FakeGameday(root)
    previous = sys.modules.get("apex_ncaaf_gameday")
    sys.modules["apex_ncaaf_gameday"] = fake
    try:
        _COUNTER[0] += 1
        spec = importlib.util.spec_from_file_location(f"apex_ncaaf_stages_job1_{_COUNTER[0]}",
                                                      OPERATIONS / "apex_ncaaf_stages.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if previous is None:
            sys.modules.pop("apex_ncaaf_gameday", None)
        else:
            sys.modules["apex_ncaaf_gameday"] = previous
    # The runner rebinds slate_schedule_rows to the living sqlite view; use the fixture rows.
    fake.slate_schedule_rows = types.MethodType(FakeGameday.slate_schedule_rows, fake)
    module.ROOT = root / "independent_scheduler"
    module.rollover_display = lambda: {"status": "SKIPPED_IN_TEST"}
    return module, fake


def pin(stages, moment_ms: int):
    """Fix the stage runner's clock."""
    os.environ["APEX_NCAAF_NOW_MS"] = str(int(moment_ms))
