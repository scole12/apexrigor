"""#23 cause 2: the grader waits for finals; its window is measured from the slate's last final.

Oct 7/9/16/18: the 07:00 grader found late games or stats not final (GRADER_INCOMPLETE) and its
retries then hit GRADER_WINDOW_CLOSED at 11:00 (or that day's T-3). Oct 18: KeyError 'game_id'
from a non-card file in issuance/<date>.
"""
import json
import sys

import pytest

import support
from support import game, grader_event, ms


@pytest.fixture
def stage(tmp_path, monkeypatch):
    stages, fake = support.load_stages(tmp_path)
    monkeypatch.setattr(stages, "alert", lambda code, detail: None)

    def at(moment_ms):
        monkeypatch.setenv("APEX_NCAAF_NOW_MS", str(moment_ms))
    return stages, fake, at


def test_grader_window_runs_from_last_final_not_11am(stage):
    stages, fake, at = stage
    # Oct 8 slate (graded on Oct 9): last kickoff 22:30 ET, so its last final is about 02:30 Oct 9.
    fake.schedules["2026-10-08"] = [game("a", ms("2026-10-08", 19, 0)), game("b", ms("2026-10-08", 22, 30))]
    event = grader_event("2026-10-08")
    at(ms("2026-10-09", 11, 30))          # after the old 11:00 close
    assert stages.require_open_window(event, "GRADER") == "ON_TIME"
    at(ms("2026-10-10", 1, 30))           # still inside 24 h after the last final
    assert stages.require_open_window(event, "GRADER") == "ON_TIME"
    at(ms("2026-10-10", 2, 0))            # past last-final + 24 h minus one attempt
    with pytest.raises(stages.StageWindowClosed):
        stages.require_open_window(event, "GRADER")


def test_stale_closed_slate_does_not_stop_the_current_one_and_not_final_is_retried(stage):
    stages, fake, at = stage
    fake.schedules["2026-10-14"] = [game("old", ms("2026-10-14", 19, 30))]     # window closed Oct 15 23:30
    fake.schedules["2026-10-16"] = [game("late", ms("2026-10-16", 22, 30))]
    fake.grader_events += [grader_event("2026-10-14"), grader_event("2026-10-16")]
    fake.grader_states["2026-10-16"] = {"slate_date_et": "2026-10-16", "GRADES_COMPLETE": False, "pending_grade_count": 2}
    at(ms("2026-10-17", 7, 5))
    with pytest.raises(stages.GraderNotReady) as caught:
        stages.run_stage("GRADER")
    assert fake.graded == ["2026-10-16"]
    assert "GRADER_INCOMPLETE:2026-10-16:WAITING_FOR_FINALS:2" in str(caught.value)
    assert "GRADER_WINDOW_CLOSED:2026-10-14" in str(caught.value)
    # Once the current slate is complete, the stale one is the only outcome: exit 78.
    fake.complete.add("2026-10-16")
    with pytest.raises(stages.StageWindowClosed):
        stages.run_stage("GRADER")


def test_not_ready_exits_75_so_systemd_retries(stage, monkeypatch, capsys):
    stages, fake, at = stage
    fake.schedules["2026-10-06"] = [game("x", ms("2026-10-06", 21, 0))]
    fake.grader_events.append(grader_event("2026-10-06"))
    at(ms("2026-10-07", 7, 0))
    monkeypatch.setattr(sys, "argv", ["apex_ncaaf_stages.py", "GRADER"])
    with pytest.raises(SystemExit) as caught:
        stages.main()
    assert caught.value.code == stages.EXIT_RETRY_LATER == 75
    assert caught.value.code != stages.EXIT_WINDOW_CLOSED


def test_grader_steps_aside_while_todays_t3_window_is_open(stage):
    stages, fake, at = stage
    fake.schedules["2026-10-17"] = [game("late", ms("2026-10-17", 23, 0))]
    fake.schedules["2026-10-18"] = [game("noon", ms("2026-10-18", 12, 0))]   # T-3 09:00-10:00
    fake.grader_events.append(grader_event("2026-10-17"))
    at(ms("2026-10-18", 9, 10))
    with pytest.raises(stages.GraderNotReady) as caught:
        stages.run_stage("GRADER")
    assert "DEFERRED_STAGE_WINDOW_OPEN:T3" in str(caught.value)
    assert fake.graded == []
    at(ms("2026-10-18", 12, 50))          # T-3 and T-2 windows (through kickoff + 45 min) are over
    fake.complete.add("2026-10-17")
    assert stages.run_stage("GRADER")["status"] == "PASS"
    assert fake.graded == ["2026-10-17"]


# --- Oct 18 KeyError 'game_id' --------------------------------------------------------------
import ncaaf_issuance_schema as schema  # noqa: E402


def card(game_id, kickoff, **extra):
    value = {"game_id": game_id, "issuance_id": "iss-" + str(game_id), "kickoff_utc_ms": kickoff,
             "positions": [{"market_type": "ATS"}]}
    value.update(extra)
    return {k: v for k, v in value.items() if v is not None}


def test_non_card_files_in_issuance_dir_are_skipped_by_schema(tmp_path):
    day = tmp_path / "2026-10-17"
    support.write_json(day / "slate.json", {"slate_date_et": "2026-10-17", "games": [
        {"game_id": "g1", "card": card("g1", 2)}, {"game_id": "g2", "card": None}]})
    # The Oct 17 rating files and a sidecar name nobody listed yet.
    support.write_json(day / "public_rating_reference_v3.json", {"policy": "V3", "thresholds": [1, 2, 3]})
    support.write_json(day / "public_rating_revision.json", {"sha256": "0" * 64})
    support.write_json(day / "rating_reference_v4.json", {"policy": "V4"})
    support.write_json(day / "g3.json", card("g3", 1))
    cards = schema.load_issuance_cards("2026-10-17", tmp_path)
    assert [c["game_id"] for c in cards] == ["g3", "g1"]


def test_slate_row_card_without_game_id_takes_the_row_id(tmp_path):
    support.write_json(tmp_path / "2026-10-15" / "slate.json", {"slate_date_et": "2026-10-15", "games": [
        {"game_id": "row-id", "card": card(None, 5)}]})
    cards = schema.load_issuance_cards("2026-10-15", tmp_path)
    assert cards[0]["game_id"] == "row-id"


def test_card_missing_game_id_is_a_named_schema_error_not_keyerror(tmp_path):
    support.write_json(tmp_path / "2026-10-17" / "bad.json", card(None, 5))
    with pytest.raises(schema.IssuanceCardSchemaError) as caught:
        schema.load_issuance_cards("2026-10-17", tmp_path)
    assert "bad.json" in str(caught.value) and "game_id" in str(caught.value)
    assert not isinstance(caught.value, KeyError)


def test_real_oct15_recovery_slate_loads(tmp_path):
    import shutil
    source = support.REPO / "tests/fixtures/n14_owner_recovery/issuance/2026-10-15"
    shutil.copytree(source, tmp_path / "2026-10-15")
    cards = schema.load_issuance_cards("2026-10-15", tmp_path)
    slate = json.loads((source / "slate.json").read_text())
    expected = {str(g["game_id"]) for g in slate["games"] if g.get("card")}
    assert {c["game_id"] for c in cards} == expected and expected


def test_grade_products_uses_the_same_loader(tmp_path, monkeypatch):
    import build_grade_products
    support.write_json(tmp_path / "2026-10-17" / "rating_reference_v4.json", {"policy": "V4"})
    support.write_json(tmp_path / "2026-10-17" / "g1.json", card("g1", 1))
    assert [c["game_id"] for c in build_grade_products.issuance_cards_at_root("2026-10-17", tmp_path)] == ["g1"]
