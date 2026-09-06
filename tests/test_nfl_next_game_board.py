from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("nfl_board", ROOT / "bin/build_nfl_public_board.py")
board = importlib.util.module_from_spec(spec)
spec.loader.exec_module(board)


def fixture():
    return {
        "generated_at_utc": "2026-09-06T18:00:00Z", "public_issuance": False,
        "scientific_release_state": "SCIENCE_BLOCKED_NO_QUALIFIED_CHAMPION", "position_count": 0,
        "slate": {"games": [{
            "game_id": "NFL_GAME_2026_01_NE_SEA", "away_team_id": "NFL_TEAM_NE", "home_team_id": "NFL_TEAM_SEA",
            "matchup": "New England Patriots at Seattle Seahawks", "season": 2026, "week": 1,
            "kickoff_utc": "2026-09-10T00:20:00Z", "status": "SCHEDULED", "positions": [],
        }]},
        "next_up": {"NEXT_T3": {"state": "SCHEDULED", "game_ids": ["NFL_GAME_2026_01_NE_SEA"], "at_utc": "2026-09-09T21:20:00Z"}},
    }


class NFLNextGameBoardTest(unittest.TestCase):
    def test_missing_odds_and_positions_still_show_kickoff_and_preparation(self):
        text = board.render_board(fixture())
        for value in ("NE @ SEA", "New England Patriots at Seattle Seahawks", "Wed, Sep 9 · 8:20 PM ET", "UNISSUED", "PREPARE", "SCIENCE_BLOCKED", "Wed, Sep 9 · 5:20 PM ET"):
            self.assertIn(value, text)
        self.assertNotIn("EMPTY BY SCIENTIFIC DESIGN", text)
        self.assertNotIn("APEX WIN PROBABILITY", text)

    def test_daily_slate_replaces_previous_game(self):
        today = fixture()
        today["slate"]["games"] = [{**today["slate"]["games"][0], "game_id": "NFL_GAME_2026_01_SF_LA", "away_team_id": "NFL_TEAM_SF", "home_team_id": "NFL_TEAM_LA", "matchup": "San Francisco 49ers at Los Angeles Rams", "kickoff_utc": "2026-09-11T00:35:00Z"}]
        text = board.render_board(today)
        self.assertIn("SF @ LAR", text)
        self.assertIn("Thu, Sep 10 · 8:35 PM ET", text)
        self.assertNotIn("NFL_GAME_2026_01_NE_SEA", text)
        self.assertNotIn("5:20 PM", text)  # Another game's stage must not appear.

    def test_multiple_games_remain_even_when_one_has_positions(self):
        today = fixture()
        second = deepcopy(today["slate"]["games"][0])
        second.update(game_id="NEXT_GAME", kickoff_utc="2026-09-11T00:35:00Z", positions=[{"position_id": "fixture"}])
        today["slate"]["games"].append(second)
        today.update(public_issuance=True, position_count=1)
        text = board.render_board(today)
        self.assertIn('data-game="NFL_GAME_2026_01_NE_SEA"', text)
        self.assertIn('data-game="NEXT_GAME"', text)
        self.assertIn('data-game-state="UNISSUED"', text)
        self.assertIn('data-game-state="ISSUED"', text)

    def test_team_text_is_escaped(self):
        today = fixture()
        today["slate"]["games"][0]["matchup"] = '<script>alert("x")</script>'
        text = board.render_board(today)
        self.assertNotIn('<script>alert', text)
        self.assertIn('&lt;script&gt;', text)

    def test_et_uses_daylight_and_standard_offsets(self):
        self.assertEqual(board.time_et("2026-09-10T00:20:00Z"), "Wed, Sep 9 · 8:20 PM ET")
        self.assertEqual(board.time_et("2027-01-11T01:20:00Z"), "Sun, Jan 10 · 8:20 PM ET")

    def test_refresh_rebuilds_both_static_routes_without_other_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'data').mkdir()
            (root / 'data/nfl_today.json').write_text(json.dumps(fixture()))
            routes = ['nfl/index.html', 'nfl/results/index.html']
            for route in routes:
                path = root / route
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('before<!-- NFL_BOARD_START -->old<!-- NFL_BOARD_END -->after')
            board.build(root)
            first = [(root / route).read_text() for route in routes]
            board.build(root)
            for route, previous in zip(routes, first):
                self.assertEqual((root / route).read_text(), previous)
                self.assertIn('NE @ SEA', previous)
                self.assertTrue(previous.startswith('before'))
                self.assertTrue(previous.endswith('after'))


if __name__ == '__main__':
    unittest.main()
