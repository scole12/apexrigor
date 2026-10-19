"""Built-output audit acceptance and narrow NBA contamination guard."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'bin'))
from _apex_site_record import record_strip

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
            strip=record_strip(json.loads((root/'data/apex_results_summary.json').read_text()))
            for route in ('nba/index.html','nba/results/index.html','nba/about/index.html','nhl/index.html'):
                self.assertIn(strip,(root/route).read_text(encoding='utf-8'))
            for route,old,new,expected in (
                ('nba/index.html',"TODAY'S CARD",'REMOVED','/nba missing'),
                ('nba/about/index.html','residual MAE','REMOVED','/nba/about missing'),
                ('nba/results/index.html','as issued','REMOVED','/nba/results missing'),
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
