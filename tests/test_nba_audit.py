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

if __name__=='__main__': unittest.main()
