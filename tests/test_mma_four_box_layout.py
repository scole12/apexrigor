"""Read-only browser regression for all issued MMA picks and four-box parity.
Run after the three MMA HTML builders. Never generates or changes a forecast.
"""
from __future__ import annotations
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import unittest
from urllib.parse import unquote,urlparse
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright=None
ROOT=Path(__file__).resolve().parents[1]

@unittest.skipIf(sync_playwright is None,'Playwright is required for browser layout tests')
class MmaFourBoxBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc=json.loads((ROOT/'data/mma_today.json').read_text())
        cls.positions=cls.doc.get('positions') or []
        if not cls.positions:raise unittest.SkipTest('No real issued card available for this read-only layout check')
        cls.before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'data').glob('mma*.json')}
        cls.pw=sync_playwright().start()
        cls.browser=cls.pw.chromium.launch(headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
    @classmethod
    def tearDownClass(cls):
        cls.browser.close();cls.pw.stop()
        after={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'data').glob('mma*.json')}
        assert cls.before==after,'MMA source data changed during browser test'
    def context(self,width):
        context=self.browser.new_context(viewport={'width':width,'height':1000},device_scale_factor=1)
        def serve(route):
            url=urlparse(route.request.url)
            if url.hostname!='mma-layout.test':route.abort();return
            path=ROOT/unquote(url.path).lstrip('/')
            if path.is_dir():path=path/'index.html'
            if not path.resolve().is_relative_to(ROOT) or not path.is_file():route.fulfill(status=404,body='Not found');return
            route.fulfill(status=200,content_type=mimetypes.guess_type(str(path))[0] or 'application/octet-stream',body=path.read_bytes())
        context.route('**/*',serve);self.addCleanup(context.close);return context
    def test_all_positions_four_boxes_all_viewports(self):
        for width in [1536,768,390,320]:
            with self.subTest(width=width):
                context=self.context(width);page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto('http://mma-layout.test/mma');page.wait_for_selector('[data-position-state="SEALED"]')
                self.assertEqual(page.locator('.mma-fight').count(),len(self.doc['card']))
                self.assertEqual(page.locator('.mma-pick-box').count(),len(self.positions)*4)
                self.assertEqual(page.locator('[data-position-state="RESEARCH"]').count(),0)
                self.assertFalse(page.locator('#forecast-copy').is_visible())
                self.assertFalse(page.locator('#issuance-details').get_attribute('open'))
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),width+1)
                for position in self.positions:
                    panel=page.locator('[data-position-bout="'+position['bout_id']+'"]')
                    self.assertEqual(panel.count(),1)
                    self.assertEqual(panel.locator('.mma-pick-box').count(),4)
                    self.assertEqual(panel.locator('[data-field="pick"] .mma-box-value').inner_text(),position['selection'])
                    price=('+' if position['price']>0 else '')+str(position['price'])
                    self.assertEqual(panel.locator('[data-field="price"] .mma-box-value').inner_text(),price)
                    self.assertEqual(panel.locator('[data-field="probability"] .mma-box-value').inner_text(),f"{position['probability']*100:.1f}%")
                    self.assertEqual(panel.locator('[data-field="rating"] .tier-badge').inner_text(),position['tier'])
                    expected=[x for x in position['rationale'].split('\n\n') if x.strip()]
                    self.assertEqual(panel.locator('.mma-rationale p').all_text_contents(),expected)
                    columns=panel.locator('.mma-pick-boxes').evaluate('(e)=>getComputedStyle(e).gridTemplateColumns.split(" ").length')
                    self.assertEqual(columns,4 if width>700 else 2)
                    self.assertTrue(panel.locator('.mma-pick-box').evaluate_all('(es)=>es.every(e=>getComputedStyle(e).borderTopStyle==="solid"&&parseFloat(getComputedStyle(e).borderTopWidth)>=1)'))
                self.assertEqual(errors,[])
                proof=os.environ.get('APEX_MMA_LAYOUT_PROOF_DIR')
                if proof:
                    folder=Path(proof);folder.mkdir(parents=True,exist_ok=True)
                    page.locator('.mma-fight').first.screenshot(path=str(folder/f'FIRST_FIGHT_{width}.png'))
                    if width==1536:page.locator('.mma-fight').last.screenshot(path=str(folder/'LAST_FIGHT_1536.png'))
                context.close()
    def test_results_matches_all_issued_positions(self):
        page=self.context(390).new_page();page.goto('http://mma-layout.test/mma/results');page.wait_for_selector('[data-position-state="SEALED"]')
        self.assertEqual(page.locator('.mma-pick-box').count(),4*len(self.positions))
        self.assertEqual(page.locator('#current-picks').inner_text(),str(len(self.positions)))
        self.assertNotIn('NO PICKS WERE ISSUED',page.locator('body').inner_text())
        self.assertEqual(page.locator('.mma-rationale-details').count(),len(self.positions))
        for p in self.positions:
            panel=page.locator('[data-position-bout="'+p['bout_id']+'"]')
            self.assertEqual(panel.locator('[data-field="pick"] .mma-box-value').inner_text(),p['selection'])
        self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),391)
    def test_about_reflects_current_issuance(self):
        page=self.context(390).new_page();page.goto('http://mma-layout.test/mma/about')
        page.wait_for_function('!document.getElementById("current-card").textContent.includes("Reading")')
        self.assertIn(str(len(self.positions))+' issued selections',page.locator('#current-card').inner_text())
        self.assertEqual(page.locator('#active-model').inner_text(),self.doc['active_model'])
        self.assertIn('not betting value',page.locator('body').inner_text().lower())
        self.assertNotIn('blocked by the absence of a licensed',page.locator('body').inner_text())
        self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),391)

if __name__=='__main__':unittest.main()
