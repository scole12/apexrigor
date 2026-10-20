"""Built-output audit acceptance and narrow NBA contamination guard."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'bin'))
from _apex_site_record import record_strip
import build_nba_public_payload as builder

class NBAAudit(unittest.TestCase):
    def test_built_positive_and_tampered_negative(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'public'
            shutil.copytree(ROOT/'public',root)
            shutil.copyfile(ROOT/'vercel.json',Path(temp)/'vercel.json')
            def audit():
                return subprocess.run([sys.executable,str(ROOT/'bin/audit_public_site.py'),'--root',str(root)],capture_output=True,text=True)
            result=audit()
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            today_path = root/'data/nba_today.json'
            today = json.loads(today_path.read_text())
            for game in today['games']:
                game['tip'] = '2026-10-20T23:30:00+00:00'
            today['release_at'] = '2026-10-20T13:30:00-04:00'
            today_path.write_text(json.dumps(today))
            with patch.object(builder, 'ROOT', root):
                builder.build()
            result = audit()
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            about_path = root/'nba/about/index.html'
            about = about_path.read_text(encoding='utf-8')
            self.assertIn('1:30 PM ET release', about)
            about_path.write_text(about.replace('1:30 PM ET release', '9:00 AM ET release'), encoding='utf-8')
            result = audit()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('computed release time', result.stdout)
            about_path.write_text(about, encoding='utf-8')
            # a released, baseline-only slate: 0 positions, every game says no engine pick is published
            today['released_at'] = '2026-10-20T17:30:00+00:00'
            today['sealed_games'] = [g['game_id'] for g in today['games']]
            today_path.write_text(json.dumps(today))
            with patch.object(builder, 'ROOT', root):
                builder.build()
            result = audit()
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            picks_path = root/'nba/index.html'
            picks = picks_path.read_text(encoding='utf-8')
            picks_path.write_text(picks.replace(' · NO ENGINE PICK PUBLISHED</p>', '</p>'), encoding='utf-8')
            result = audit()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('NBA released state mismatch', result.stdout)
            picks_path.write_text(picks, encoding='utf-8')
            strip=record_strip(json.loads((root/'data/apex_results_summary.json').read_text()))
            for route in ('nba/index.html','nba/results/index.html','nba/about/index.html','nhl/index.html'):
                self.assertIn(strip,(root/route).read_text(encoding='utf-8'))
            for route,old,new,expected in (
                ('nba/index.html',"TODAY'S CARD",'REMOVED','/nba missing'),
                ('nba/about/index.html','sealed NBA picks and their grades','REMOVED','/nba/about missing'),
                ('nba/results/index.html','id="results-root"','REMOVED','/nba/results missing'),
                ('nhl/index.html','</main>','NBA</main>','unlaunched sport leaked'),
                ('nhl/index.html','</main>','<a href="/nba">NBA</a></main>','unlaunched sport leaked'),
                ('nba/index.html','href="/nba/results"','href="/wrong"','missing NBA navigation'),
            ):
                path=root/route; original=path.read_bytes()
                try:
                    text=original.decode('utf-8'); self.assertIn(old,text)
                    path.write_text(text.replace(old,new),encoding='utf-8')
                    result=audit()
                    self.assertNotEqual(result.returncode,0,result.stdout)
                    self.assertIn(expected,result.stdout)
                finally:
                    path.write_bytes(original)



class NBARationale(unittest.TestCase):
    def row(self,market,side,**kw):
        import datetime
        base=dict(prediction_id=1,game_id=146452,market=market,side=side,p=0.5375,line=-4.5,price_a=-115,price_b=-105,
                  away='Philadelphia 76ers',home='New York Knicks',engine='opus:shrink_c3',engine_version='ats_shrink_c3.v2',
                  issued_at=datetime.datetime(2026,10,20,13,5,tzinfo=datetime.timezone.utc),outcome=None)
        base.update(kw)
        return base

    def test_a_stored_rationale_is_kept_and_a_missing_one_is_built_from_stored_fields(self):
        kept=builder.public_position(self.row('spread','a',rationale='Stored text.'))
        self.assertEqual(kept['rationale'],'Stored text.')
        built=builder.public_position(self.row('spread','a'))
        self.assertIn('53.8% chance to cover', built['rationale'])
        self.assertIn('The published market is ATS', built['rationale'])
        self.assertNotIn('opus:shrink_c3', built['rationale'])
        self.assertNotIn('coef', built['rationale'].lower())
        self.assertNotIn('rest', built['rationale'].lower())
        self.assertNotIn('travel', built['rationale'].lower())
        total=builder.public_position(self.row('total','a',engine='c6:d4_ratings_lag1',engine_version='totals_d4_ratings_lag1.v2'))
        self.assertIn('53.8% chance on the total', total['rationale'])
        self.assertNotIn('totals_d4_ratings_lag1', total['rationale'])
        self.assertNotIn('None', total['rationale'])
        self.assertNotIn('rest', total['rationale'].lower())
        self.assertNotIn('travel', total['rationale'].lower())

    def test_an_away_spread_pick_shows_its_own_win_chance_and_its_own_line(self):
        away=builder.public_position(self.row('spread','b',p=0.474,line=-1.5,price_a=-110,price_b=-110))
        self.assertAlmostEqual(away['probability'],0.526)
        self.assertEqual(away['probability_side'],'away')
        self.assertEqual(away['line'],1.5)
        home=builder.public_position(self.row('spread','a',p=0.5375,line=-4.5))
        self.assertAlmostEqual(home['probability'],0.5375)
        self.assertEqual((home['probability_side'],home['line']),('home',-4.5))
        under=builder.public_position(self.row('total','b',p=0.45,line=220.5))
        self.assertAlmostEqual(under['probability'],0.55)
        self.assertEqual((under['probability_side'],under['line']),('Under',220.5))

    def test_a_t6_rationale_is_plain_english_and_names_the_players(self):
        import nba_t6_rationale as t6
        players = [
            dict(player_id=1, team_id=9, team='Detroit Pistons', name='Cade Cunningham', is_home=True,
                 p_mp=34, oepm=2.8, depm=0.9, epm=3.7, status=None, min_recent5=30, games_season=0,
                 ast36=6.0, reb36=4.0, blk36=0.4, fg3a_rate=0.3),
            dict(player_id=2, team_id=2, team='Boston Celtics', name='Jayson Tatum', is_home=False,
                 p_mp=33, oepm=3.4, depm=1.0, epm=4.5, status='Out', min_recent5=32, games_season=0,
                 ast36=4.0, reb36=7.0, blk36=0.6, fg3a_rate=0.4),
        ]
        row = self.row('spread', 'a', line=1.5, p=0.5006, price_a=-114, price_b=-106,
                       home_team_id=9, away_team_id=2,
                       t6=dict(players=players, teams={}, prediction=None))
        public = builder.public_position(dict(row, t6=None))
        public['tier'] = 'Weak'
        text = t6.spread_rationale(row, public)
        self.assertTrue(6 <= t6.sentence_count(text) <= 8)
        self.assertIn('Cade Cunningham', text)
        self.assertIn('Jayson Tatum', text)
        self.assertIn('50.1% chance to cover', text)
        self.assertIn('The tier is Weak', text)
        self.assertIn('Before T-6', text)
        low = text.lower()
        for banned in ('coef', 'q_b0', 'sigma', 'intercept', 'phi', 'rest', 'travel', 'opus:', 'champion'):
            self.assertNotIn(banned, low)

if __name__=='__main__': unittest.main()
