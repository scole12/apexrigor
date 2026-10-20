"""Public-only fixtures; no outcomes or engine/database access."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'bin'))
spec = importlib.util.spec_from_file_location('nba_builder', ROOT / 'bin/build_nba_public_payload.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


TIER_BANDS = dict(version=2, fitted_on=['2022-23', '2023-24'], date='2026-10-20',
                  cutoffs=[0.5065608111643407, 0.5354196603716558, 0.589047001464929],
                  tiers=['WEAK', 'MODERATE', 'STRONG', 'ELITE'])


class NBAWebsite(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / 'nhl', self.root / 'nhl')
        (self.root / 'data').mkdir()
        for name in ('today', 'results_archive', 'results_summary'):
            shutil.copyfile(ROOT / f'data/nba_{name}.json', self.root / f'data/nba_{name}.json')
        builder.ROOT = self.root

    def page(self, section=''):
        return (self.root / 'nba' / section / 'index.html').read_text(encoding='utf-8')

    def test_unissued(self):
        builder.build()
        self.assertIn('TUESDAY, OCTOBER 20, 2026 · 3 GAMES · 0 POSITIONS · ATS · TOTALS', self.page())
        self.assertIn('AWAITING 9:00 AM RELEASE', self.page())
        self.assertIn('9:00 AM ET release', self.page('about'))
        self.assertEqual(self.page().count('<article class="game-module"'), 3)
        for label in ('G01', 'G02', 'G03', 'Boston Celtics @ Detroit Pistons', '3:00 PM ET', '7:00 PM ET', '9:30 PM ET', 'SCHEDULE UPDATED'):
            self.assertIn(label, self.page())
        for forbidden in ('Common release', 'FIRST tip', 'planned games', 'T-6', 'T09:00'):
            self.assertNotIn(forbidden, self.page())
        self.assertIn('0 POSITIONS', self.page())
        self.assertIn('id="results-root"', self.page('results'))
        self.assertIn('/nba/results/render.js', self.page('results'))
        self.assertNotIn('0.0%', self.page('results'))
        self.assertNotIn('2.0', self.page('about'))

    def test_future_release_and_counts(self):
        path = self.root / 'data/nba_today.json'
        today = json.loads(path.read_text())
        today.update(slate_date='2027-01-15', release_at='2027-01-15T13:30:00-05:00',
                     scheduled_games=1, games=[dict(game_id='FUTURE', away='Away', home='Home',
                     tip='2027-01-16T00:30:00+00:00', season_type='regular')])
        path.write_text(json.dumps(today))
        builder.build()
        for text in ('FRIDAY, JANUARY 15, 2027', '1 GAMES', '0 POSITIONS', '7:30 PM ET', "TODAY'S CARD", 'AWAITING 1:30 PM RELEASE'):
            self.assertIn(text, self.page())
        self.assertNotIn('3 GAMES', self.page())
        self.assertIn('1:30 PM ET release', self.page('about'))
        self.assertEqual(builder.release_time(today['games']).isoformat(), today['release_at'])

    def test_reader_sealed_facts_and_baseline_boundary(self):
        from unittest.mock import MagicMock, patch
        from datetime import date, datetime, timezone
        row = dict(prediction_id='SEALED', game_id=1, market='spread', side='b',
                   p=.43, line=-3.5, price_a=-110, price_b=-115,
                   away='Away', home='Home', engine='accepted:fixture', engine_version='v1',
                   issued_at=datetime(2026,10,19,tzinfo=timezone.utc),
                   game_date=date(2026,10,19), outcome='push')
        conn = MagicMock()
        conn.__enter__.return_value = conn
        conn.execute.side_effect = [MagicMock(), MagicMock(fetchall=lambda: []),
                                   MagicMock(fetchall=lambda: [row]),
                                   MagicMock(fetchall=lambda: [])]
        bands = self.root / 'tier_bands.json'
        bands.write_text(json.dumps(TIER_BANDS))
        with patch('psycopg.connect', return_value=conn) as connect, patch.object(builder, 'reader_url', return_value='READER_FIXTURE'):
            builder.refresh(date(2026,10,20), bands)
        self.assertIn('default_transaction_read_only=on', connect.call_args.kwargs['options'])
        sql = str(conn.execute.call_args_list)
        for marker in ('read only', 'core.games', 'core.teams', 'ops.predictions', 'ops.grades',
                       'n.supersedes=gr.grade_id', "p.engine not like", "p.engine_version not like", 'baseline:'):
            self.assertIn(marker, sql)
        archive = json.loads((self.root/'data/nba_results_archive.json').read_text())
        position = archive['slates'][0]['positions'][0]
        self.assertEqual((position['result'], position['price'], position['probability'], position['line']), ('P', -115, .43, -3.5))
        # side b at p = .43: win probability .57, STRONG from the tier bands file
        self.assertEqual((position['tier'], position['tier_version'], round(position['win_probability'], 9)), ('Strong', 2, .57))
        self.assertEqual(json.loads((self.root/'data/nba_today.json').read_text())['positions'], [])
        for field in ('engine', 'engine_version'):
            with self.assertRaisesRegex(ValueError, 'baseline'):
                builder.public_position(dict(row, **{field:'baseline:fixture'}))
        path = self.root/'data/nba_today.json'
        today = json.loads(path.read_text())
        today.update(status='ISSUED', positions=[dict(position, engine='baseline:fixture')])
        path.write_text(json.dumps(today))
        with self.assertRaisesRegex(ValueError, 'baseline'):
            builder.build()

    def test_probability_endpoints_and_precision(self):
        path = self.root / 'data/nba_today.json'
        today = json.loads(path.read_text())
        for probability, expected in ((0, '0%'), (1, '100%'), (.5, '50%'), (.54321987, '54.321987%')):
            today.update(status='ISSUED', games=[], positions=[dict(position_id='SYNTHETIC', game_id='SYNTHETIC', market='ATS', role='Favorite', tier='Strong', probability=probability)])
            path.write_text(json.dumps(today))
            builder.build()
            self.assertIn('Probability: ' + expected, self.page())
            self.assertIn('Favorite', self.page())
            self.assertIn('Strong', self.page())

    def test_original_fields_and_pending(self):
        position = dict(position_id='FIXTURE_ONLY', game_id='FIXTURE_GAME', market='ATS', selection='Away', role='Underdog', prediction=101.123, probability=.54321, line=3.5, price=-112, tier='Weak', rationale='<original & rationale>', result=None)
        today = json.loads((self.root / 'data/nba_today.json').read_text())
        today.update(status='ISSUED', games=[], positions=[position, dict(position, position_id='TOTAL', market='TOTALS', role='Over', selection='Over', tier='Elite')])
        (self.root / 'data/nba_today.json').write_text(json.dumps(today))
        archive = {'sport':'NBA', 'slates':[{'slate_date':'2026-10-20', 'week_start':'2026-10-19', 'positions':[position, dict(position,position_id='W',result='W'),dict(position,position_id='L',result='L'),dict(position,position_id='P',result='P')]}]}
        (self.root / 'data/nba_results_archive.json').write_text(json.dumps(archive))
        builder.build()
        for value in ('101.123', '54.321%', '-112', 'Weak', '&lt;original &amp; rationale&gt;', 'Underdog'):
            self.assertIn(value, self.page())
        # Record/grade/pending behavior is exercised by nba_results_scope.test.cjs.
        self.assertIn('id="results-root"', self.page('results'))
        self.assertIn('Not yet available', self.page())
        self.assertEqual(self.page().count('<article class="game-module"'), 1)
        self.assertEqual(self.page().count('<section class="market-panel"'), 2)
        self.assertIn('Elite', self.page())
        self.assertIn('Over', self.page())


if __name__ == '__main__':
    unittest.main()


class NBAReleaseLabel(unittest.TestCase):
    """The page after the release: the ET release stamp, baseline-only slates and engine picks with tiers."""

    def setUp(self):
        NBAWebsite.setUp(self)

    page = NBAWebsite.page

    def released(self, positions=()):
        path = self.root / 'data/nba_today.json'
        today = json.loads(path.read_text())
        today.update(released_at='2026-10-20T13:00:00+00:00', schedule_updated_at='2026-10-20T15:47:00+00:00',
                     sealed_games=['146451', '146452'],
                     status='ISSUED' if positions else 'UNISSUED', positions=list(positions))
        path.write_text(json.dumps(today))
        builder.build()
        return self.page()

    def test_released_baseline_only_slate_shows_zero_positions_and_says_why(self):
        page = self.released()
        self.assertIn('UPDATED OCT 20, 9:00 AM ET · SLATE RELEASED · NO ENGINE PICK PUBLISHED', page)
        self.assertIn('0 POSITIONS', page)
        self.assertNotIn('AWAITING', page)
        self.assertNotIn('11:47', page)  # the clock of the build is not shown
        self.assertEqual(page.count('RELEASED — NO ENGINE PICK PUBLISHED'), 3)
        self.assertEqual(page.count('release sealed this game with baseline picks only. Baseline picks are not published on this page'), 2)
        self.assertEqual(page.count('The 9:00 AM release sealed no pick for this game'), 1)

    def test_before_the_release_the_schedule_time_is_shown_in_et_with_its_date(self):
        builder.build()
        self.assertIn('SCHEDULE UPDATED OCT 19, 1:01 PM ET', self.page())
        self.assertIn('AWAITING 9:00 AM RELEASE', self.page())

    def test_engine_picks_show_win_pct_and_the_tier_of_the_bands_file(self):
        rows = [dict(prediction_id=f'E{i}', game_id=146451, market=m, side=side, p=p, line=1.5, price_a=-110,
                     price_b=-110, away='Boston Celtics', home='Detroit Pistons', engine='opus:shrink_c3',
                     engine_version='v1', issued_at=__import__('datetime').datetime(2026, 10, 20, 13), outcome=None)
                for i, (m, side, p) in enumerate((('spread', 'a', .5040), ('total', 'b', 1 - .5363)))]
        positions = [builder.public_position(r, TIER_BANDS) for r in rows]
        self.assertEqual([p['tier'] for p in positions], ['Weak', 'Strong'])
        page = self.released(positions)
        self.assertIn('UPDATED OCT 20, 9:00 AM ET · SLATE RELEASED</p>', page)
        self.assertIn('2 POSITIONS', page)
        for text in ('Win %: 50.4', 'Win %: 53.6', '>Weak<', '>Strong<'):
            self.assertIn(text, page)
        self.assertEqual(builder.tier_of(TIER_BANDS, TIER_BANDS['cutoffs'][0]), 'Moderate')
        self.assertEqual(builder.tier_of(TIER_BANDS, TIER_BANDS['cutoffs'][2]), 'Elite')

    def test_a_pick_already_on_the_site_keeps_its_first_published_tier(self):
        from unittest.mock import MagicMock, patch
        from datetime import date, datetime, timezone
        row = dict(prediction_id='KEEP', game_id=1, market='spread', side='a', p=.60, line=-3.5, price_a=-110,
                   price_b=-110, away='Away', home='Home', engine='opus:shrink_c3', engine_version='v1',
                   issued_at=datetime(2026, 10, 19, 13, tzinfo=timezone.utc), game_date=date(2026, 10, 19), outcome=None)
        archive = dict(sport='NBA', slates=[dict(slate_date='2026-10-19', week_start='2026-10-19',
                       positions=[dict(position_id='KEEP', tier='Moderate', tier_version=1)])])
        (self.root / 'data/nba_results_archive.json').write_text(json.dumps(archive))
        bands = self.root / 'tier_bands.json'
        bands.write_text(json.dumps(TIER_BANDS))
        conn = MagicMock()
        conn.__enter__.return_value = conn
        conn.execute.side_effect = [MagicMock(), MagicMock(fetchall=lambda: []), MagicMock(fetchall=lambda: [row]),
                                    MagicMock(fetchall=lambda: [])]
        with patch('psycopg.connect', return_value=conn), patch.object(builder, 'reader_url', return_value='R'):
            builder.refresh(date(2026, 10, 20), bands)
        kept = json.loads((self.root / 'data/nba_results_archive.json').read_text())['slates'][0]['positions'][0]
        self.assertEqual((kept['tier'], kept['tier_version']), ('Moderate', 1))  # the file would say Elite, v2
