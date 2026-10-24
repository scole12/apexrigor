"""Read-only browser check of the MMA 'max winner' picks layout. Never changes data."""
import json,mimetypes,os,unittest
from pathlib import Path
from urllib.parse import unquote,urlparse
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright=None
ROOT=Path(__file__).resolve().parents[1]
TIERS=['ELITE','STRONG','MODERATE','WEAK']

@unittest.skipIf(sync_playwright is None,'playwright not installed')
class MmaMaxWinnerLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc=json.loads((ROOT/'data/mma_today.json').read_text())
        cls.positions=cls.doc.get('positions') or []
        if not cls.positions:raise unittest.SkipTest('No issued card to check')
        cls.pw=sync_playwright().start();cls.browser=cls.pw.chromium.launch(headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
    @classmethod
    def tearDownClass(cls):
        cls.browser.close();cls.pw.stop()
    def page(self,width):
        ctx=self.browser.new_context(viewport={'width':width,'height':900});self.addCleanup(ctx.close)
        def serve(route):
            url=urlparse(route.request.url)
            if url.hostname!='mma-max.test':route.abort();return
            path=ROOT/unquote(url.path).lstrip('/')
            if path.is_dir():path=path/'index.html'
            if not path.resolve().is_relative_to(ROOT) or not path.is_file():route.fulfill(status=404,body='Not found');return
            route.fulfill(status=200,content_type=mimetypes.guess_type(str(path))[0] or 'application/octet-stream',body=path.read_bytes())
        ctx.route('**/*',serve);page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('http://mma-max.test/mma');page.wait_for_selector('#games[data-render-complete="true"]')
        self.assertEqual(errors,[]);return page
    def test_best_plays_tiers_sorted_and_compact(self):
        for width in [390,320,1280]:
            with self.subTest(width=width):
                page=self.page(width)
                best=[p for p in self.positions if p['tier'] in ('ELITE','STRONG')]
                self.assertEqual(page.locator('[data-section="best-plays"] .mma-pick').count(),len(best))
                self.assertEqual(page.locator('.mma-tier .mma-pick').count(),len(self.positions))
                groups=page.locator('[data-tier-group]').evaluate_all('(es)=>es.map(e=>e.dataset.tierGroup)')
                self.assertEqual(groups,[t for t in TIERS if any(p['tier']==t for p in self.positions)])
                for t in groups:
                    probs=page.locator(f'[data-tier-group="{t}"] .mma-pick [data-field="probability"]').all_inner_texts()
                    expected=[f"{p['probability']*100:.1f}%" for p in sorted([p for p in self.positions if p['tier']==t],key=lambda p:-p['probability'])]
                    self.assertEqual(probs,expected)
                self.assertEqual(page.locator('.mma-market-slot,.mma-market-breakdown').count(),0)
                self.assertEqual(page.locator('details.mma-why[open]').count(),0)
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),width+1)
                proof=os.environ.get('APEX_MMA_MAX_PROOF_DIR')
                if proof and width==390:
                    Path(proof).mkdir(parents=True,exist_ok=True);page.screenshot(path=str(Path(proof)/'MMA_MAX_WINNER_390.png'),full_page=True)

if __name__=='__main__':unittest.main()
