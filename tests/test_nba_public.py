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
        self.assertIn('2026-10-20', self.page())
        self.assertIn('09:00 Eastern', self.page())
        self.assertIn('0 issued positions', self.page())
        self.assertIn('Not yet available', self.page('results'))
        self.assertNotIn('0.0%', self.page('results'))
        self.assertNotIn('2.0', self.page('about'))

    def test_future_release_and_counts(self):
        path = self.root / 'data/nba_today.json'
        today = json.loads(path.read_text())
        today.update(slate_date='2027-01-15', release_at='2027-01-15T18:30:00+00:00', scheduled_games=7, planned_positions=14, first_tip='2027-01-16T00:30:00+00:00')
        path.write_text(json.dumps(today))
        builder.build()
        for text in ('2027-01-15 13:30 Eastern', '7 planned games', '14 planned positions', "TODAY'S CARD", 'AWAITING T-6'):
            self.assertIn(text, self.page())
        self.assertNotIn('09:00', self.page())
        self.assertNotIn('three games', self.page())

    def test_probability_endpoints_and_precision(self):
        path = self.root / 'data/nba_today.json'
        today = json.loads(path.read_text())
        for probability, expected in ((0, '0%'), (1, '100%'), (.5, '50%'), (.54321987, '54.321987%')):
            today.update(status='ISSUED', positions=[dict(position_id='SYNTHETIC', game_id='SYNTHETIC', market='ATS', role='Favorite', tier='Strong', probability=probability)])
            path.write_text(json.dumps(today))
            builder.build()
            self.assertIn('Probability: ' + expected, self.page())
            self.assertIn('Favorite', self.page())
            self.assertIn('Strong', self.page())

    def test_original_fields_and_pending(self):
        position = dict(position_id='FIXTURE_ONLY', game_id='FIXTURE_GAME', market='ATS', selection='Away', role='Underdog', prediction=101.123, probability=.54321, line=3.5, price=-112, tier='Weak', rationale='<original & rationale>', result=None)
        today = json.loads((self.root / 'data/nba_today.json').read_text())
        today.update(status='ISSUED', positions=[position, dict(position, position_id='TOTAL', market='TOTALS', role='Over', selection='Over', tier='Elite')])
        (self.root / 'data/nba_today.json').write_text(json.dumps(today))
        archive = {'sport':'NBA', 'slates':[{'slate_date':'2026-10-20', 'week_start':'2026-10-19', 'positions':[position, dict(position,position_id='W',result='W'),dict(position,position_id='L',result='L'),dict(position,position_id='P',result='P')]}]}
        (self.root / 'data/nba_results_archive.json').write_text(json.dumps(archive))
        builder.build()
        for value in ('101.123', '54.321%', '-112', 'Weak', '&lt;original &amp; rationale&gt;', 'Underdog'):
            self.assertIn(value, self.page())
        for value in ('1-1-1P · 50.0%', '4 positions tracked · 1 pending', 'Daily 2026-10-20', 'Week 2026-10-19'):
            self.assertIn(value, self.page('results'))
        self.assertIn('Not yet available', self.page())
        self.assertEqual(self.page().count('<article class="game-module"'), 1)
        self.assertEqual(self.page().count('<section class="market-panel"'), 2)
        self.assertIn('Elite', self.page())
        self.assertIn('Over', self.page())


if __name__ == '__main__':
    unittest.main()
