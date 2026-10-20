"""#23 causes 3, 4 and 8: T-3 hydration keeps the slate when one team, week or game has a fault.

Cause 3 (Oct 9-10): ROSTER_IDENTITY_CORRECTION_ATTESTED_TEAM_ABSENT for corrections whose
attested team (Georgia State, Grambling) was not on the slate.
Cause 4 (Oct 9, 13): PLAYER_ENDPOINT_SOURCE_DEADLINE_BUDGET_EXHAUSTED threw away every week
already fetched; each retry started over.
Cause 8 (Oct 6): CANONICAL_SCHEDULE_OUTCOME_SCORE_CONFLICT for one game.
"""
import hashlib
import json
import sqlite3
import time

import pytest

import support  # noqa: F401  (sets the runtime path and env)

import ncaaf_roster_corrections as corrections


def applied(native, attested):
    return {"provider_native_player_id": native, "attested_team_label": attested,
            "rejected_team_label": "Alabama"}


SLATE = {"t-ala": "Alabama", "t-aub": "Auburn"}


def test_correction_for_team_not_on_slate_is_a_noop():
    # Before #23 this raised ROSTER_IDENTITY_CORRECTION_ATTESTED_TEAM_ABSENT and failed T-3.
    corrections.verify_applied([applied("5212990", "Georgia State"), applied("5151696", "Grambling")], {}, SLATE)
    unverified = []
    corrections.verify_applied([applied("5212990", "Georgia State")], {}, SLATE, unverified=unverified)
    assert unverified == []


def test_correction_for_team_on_slate_still_fails_closed():
    with pytest.raises(RuntimeError, match="ATTESTED_TEAM_ABSENT:7:Auburn"):
        corrections.verify_applied([applied("7", "Auburn")], {}, SLATE)
    corrections.verify_applied([applied("7", "Auburn")], {"7": {("t-aub", "Auburn")}}, SLATE)


# --- cause 4 ----------------------------------------------------------------------------------
@pytest.fixture
def player_sync(tmp_path, monkeypatch):
    monkeypatch.setenv("APEX_NCAAF_VAR_ROOT", str(tmp_path / "var"))
    import ncaaf_current_stats_sync as base
    import ncaaf_current_player_sync as players
    monkeypatch.setattr(base.w, "VAR", tmp_path / "var")
    monkeypatch.setattr(base.w, "RAW_ROOT", tmp_path / "var/raw/cfbd/living")
    calls = []
    clock = {"ms": 1_792_000_000_000}

    def cfbd_get(endpoint, params, return_evidence=True):
        calls.append((params["seasonType"], params["week"]))
        body = json.dumps([{"week": params["week"]}]).encode()
        raw = base.w.RAW_ROOT / (hashlib.sha256(body).hexdigest() + ".json")
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_bytes(body)
        clock["ms"] += 1000
        return body, json.loads(body), {"status": "PASS", "endpoint": endpoint, "request_params": dict(params),
                                        "response_completed_at_utc_ms": clock["ms"],
                                        "raw_object": {"path": str(raw), "sha256": hashlib.sha256(body).hexdigest()}}
    monkeypatch.setattr(base.w, "_cfbd_get", cfbd_get)
    return players, calls, clock


def schedule(weeks, knowable):
    return {f"n{w}": {"season_type": "regular", "week": w, "game_id": f"g{w}",
                      "outcome_knowable_at_utc_ms": knowable} for w in weeks}


def test_budget_stop_keeps_fetched_weeks_and_retry_resumes(player_sync, monkeypatch):
    players, calls, clock = player_sync
    games = schedule([5, 6, 7], knowable=1_791_000_000_000)
    real_time = time.time
    budget = {"left": 2}

    def deadline_time():
        # Two weeks fit in the first attempt's budget, then the budget runs out.
        budget["left"] -= 1
        return (real_time() if budget["left"] >= 0 else real_time() + 10_000)
    monkeypatch.setattr(players.time, "time", deadline_time)
    deadline = int(real_time() * 1000) + 600_000
    with pytest.raises(RuntimeError, match="PLAYER_ENDPOINT_SOURCE_DEADLINE_BUDGET_EXHAUSTED"):
        players._capture_required_player_endpoint("ppa/players/games", 2026, games, deadline, "2026-10-13")
    first = list(calls)
    assert first and len(first) < 3
    monkeypatch.setattr(players.time, "time", real_time)
    observations = players._capture_required_player_endpoint("ppa/players/games", 2026, games, deadline, "2026-10-13")
    assert [o["request_params"]["week"] for o in observations] == [5, 6, 7]
    assert calls[len(first):] == [("regular", w) for w in (5, 6, 7) if ("regular", w) not in first]
    assert sum(bool(o.get("reused_from_earlier_attempt")) for o in observations) == len(first)


def test_week_with_a_game_final_after_the_capture_is_fetched_again(player_sync):
    players, calls, clock = player_sync
    deadline = int(time.time() * 1000) + 600_000
    players._capture_required_player_endpoint("ppa/players/games", 2026, schedule([5], 1_791_000_000_000), deadline, "2026-10-13")
    later = schedule([5], clock["ms"] + 3_600_000)   # a game in week 5 became final after that capture
    players._capture_required_player_endpoint("ppa/players/games", 2026, later, deadline, "2026-10-13")
    assert calls == [("regular", 5), ("regular", 5)]


def test_pre_t3_sweep_starts_up_to_six_hours_early(tmp_path, monkeypatch):
    stages, fake = support.load_stages(tmp_path)
    kick = support.ms("2026-10-17", 15, 30)
    fake.schedules["2026-10-17"] = [support.game("g", kick)]
    now = kick - 3 * 3600000 - 5 * 3600000      # five hours before T-3
    monkeypatch.setenv("APEX_NCAAF_NOW_MS", str(now))
    ran = []
    monkeypatch.setattr(stages, "run_current_stats_for_t3", lambda event, sweep, budget_ms: ran.append(event) or {"status": "PASS"})
    result = stages.sweep_before_t3(now)
    assert ran and result["status"] == "PASS"


# --- cause 8 ----------------------------------------------------------------------------------
def hist_db(rows):
    con = sqlite3.connect(":memory:")
    con.execute("""CREATE TABLE game_schedule_versions (game_id TEXT, apex_captured_at_utc_ms INT,
        became_knowable_at_utc_ms INT, record_status TEXT, season INT, game_status TEXT, source_native_id TEXT,
        payload_json TEXT, missing_flag INT, value_state TEXT, kickoff_utc_ms INT, season_type TEXT, week INT,
        home_team_id TEXT, away_team_id TEXT)""")
    con.execute("""CREATE TABLE official_outcome_versions (game_id TEXT, apex_captured_at_utc_ms INT,
        became_knowable_at_utc_ms INT, record_status TEXT, outcome_status TEXT, home_final_points INT,
        away_final_points INT, missing_flag INT, value_state TEXT, record_content_sha256 TEXT)""")
    for gid, native, source_points, final_points in rows:
        payload = {"id": int(native), "homePoints": source_points[0], "awayPoints": source_points[1]}
        con.execute("INSERT INTO game_schedule_versions VALUES (?,1,1,'ACTIVE',2026,'FINAL',?,?,0,'OBSERVED',1000,'regular',6,'h','a')",
                    (gid, "cfbd-game:" + native, json.dumps(payload)))
        con.execute("INSERT INTO official_outcome_versions VALUES (?,1,1,'ACTIVE','OFFICIAL',?,?,0,'OBSERVED','x')",
                    (gid, final_points[0], final_points[1]))
    return con


ROWS = [("g-ok", "401868001", (21, 14), (21, 14)), ("g-bad", "401868094", (28, 10), (27, 10))]


def test_score_conflict_quarantines_only_that_game_in_stats_sync():
    import ncaaf_current_stats_sync as base
    conflicts = []
    result = base.completed_schedule(hist_db(ROWS), 2026, conflicts)
    assert set(result) == {"401868001"}
    assert [c["provider_game_id"] for c in conflicts] == ["401868094"]
    assert "SCORE_CONFLICT" in conflicts[0]["reason"]


def test_score_conflict_quarantines_only_that_game_in_player_sync():
    import ncaaf_current_player_sync as players
    conflicts = []
    result = players.ppa_completed_schedule(hist_db(ROWS), 2026, 10**13, conflicts)
    assert set(result) == {"401868001"}
    assert [c["provider_game_id"] for c in conflicts] == ["401868094"]
