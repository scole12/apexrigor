"""Read-only four-market UI tests. No forecast, quote, grade or database writes."""
import copy,hashlib,json,mimetypes,os,unittest
from pathlib import Path
from urllib.parse import urlparse,unquote
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]

class MmaFourMarketPicksTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.today=json.loads((ROOT/'data/mma_today.json').read_text())
  cls.source=json.loads((ROOT/'data/mma_four_markets_20260905.json').read_text())
  cls.hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'data').glob('mma*.json')}
  cls.pw=sync_playwright().start();cls.browser=cls.pw.chromium.launch(headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
 @classmethod
 def tearDownClass(cls):
  cls.browser.close();cls.pw.stop()
  for name,digest in cls.hashes.items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest
 def page(self,width=1536,source=None,status=200):
  context=self.browser.new_context(viewport={'width':width,'height':1100});self.addCleanup(context.close)
  payload=self.source if source is None else source
  def serve(route):
   url=urlparse(route.request.url)
   if url.hostname!='mma-four.test':route.abort();return
   if url.path.endswith('/mma_four_markets_20260905.json'):route.fulfill(status=status,content_type='application/json',body=json.dumps(payload));return
   path=ROOT/unquote(url.path).lstrip('/')
   if path.is_dir():path=path/'index.html'
   if not path.resolve().is_relative_to(ROOT) or not path.is_file():route.fulfill(status=404,body='Not found');return
   route.fulfill(status=200,content_type=mimetypes.guess_type(str(path))[0] or 'application/octet-stream',body=path.read_bytes())
  context.route('**/*',serve);page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto('http://mma-four.test/mma');page.wait_for_selector('#games[data-render-complete="true"]')
  self.assertEqual(errors,[]);return page
 def test_all_four_markets_every_fight_desktop_mobile(self):
  for width in [1536,768,390,320]:
   with self.subTest(width=width):
    page=self.page(width);self.assertEqual(page.locator('.mma-fight').count(),14)
    self.assertEqual(page.locator('.mma-market-panel').count(),56)
    self.assertEqual(page.locator('[data-prop-state="RESEARCH_UNISSUED"]').count(),56)
    self.assertEqual(page.locator('#prelims,#maincard,#t3time,#t2time,.banner').count(),0)
    self.assertIn('AFTER CARD START',page.locator('#compact-issuance').inner_text())
    self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),width+1)
    self.assertEqual(page.locator('.mma-market-panel .tier-badge').count(),0)
    for b in self.source['bouts']:
     sections=page.locator('[data-prop-bout="'+b['bout_id']+'"]');self.assertEqual(sections.count(),4)
     self.assertEqual(sections.evaluate_all('(es)=>es.map(e=>e.dataset.marketFamily)'),['METHOD','COMBINED_METHOD','TOTAL_ROUNDS','GOES_DISTANCE'])
     for family,key in [('METHOD','method'),('COMBINED_METHOD','combined_method')]:
      panel=page.locator('[data-prop-bout="'+b['bout_id']+'"][data-market-family="'+family+'"]')
      self.assertTrue(panel.is_visible());self.assertEqual(panel.locator('tbody tr').count(),6)
      for f in b['fighters']:
       for q in f[key]:
        row=panel.locator('[data-market-selection="'+q['selection']+'"]')
        self.assertEqual(row.locator('[data-probability]').inner_text(),f"{q['research_probability']*100:.1f}%")
        self.assertEqual(row.locator('[data-quote-status]').inner_text(),'—')
     total=page.locator('[data-prop-bout="'+b['bout_id']+'"][data-market-family="TOTAL_ROUNDS"]')
     self.assertIn('Actual FanDuel rounds line: not captured',total.inner_text())
     self.assertIn('NOT VERIFIED FANDUEL LINES',total.inner_text().upper())
     self.assertEqual(total.locator('tbody tr').count(),b['scheduled_rounds'])
     for g in b['total_rounds']['research_grid']:
      row=total.locator('[data-reference-line="'+str(g['line'])+'"]')
      self.assertEqual(row.locator('[data-probability]').all_text_contents(),[f"{g[k]['research_probability']*100:.1f}%" for k in ['over','under']])
     distance=page.locator('[data-prop-bout="'+b['bout_id']+'"][data-market-family="GOES_DISTANCE"]')
     self.assertEqual(distance.locator('[data-probability]').all_text_contents(),[f"{b['goes_distance'][k]['research_probability']*100:.1f}%" for k in ['yes','no']])
    self.assertEqual(page.locator('.mma-winner-history').count(),14)
    self.assertEqual(page.locator('.mma-winner-history[open]').count(),0)
    folder=os.environ.get('APEX_MMA_MARKET_PROOF_DIR')
    if folder and width in [1536,390]:
     Path(folder).mkdir(parents=True,exist_ok=True)
     page.locator('.mma-fight').first.screenshot(path=str(Path(folder)/f'FOUR_MARKETS_FIRST_FIGHT_{width}.png'))
    page.context.close()
 def test_original_winner_record_is_available_unchanged(self):
  page=self.page(390)
  for p in self.today['positions']:
   panel=page.locator('[data-position-bout="'+p['bout_id']+'"]');details=panel.locator('..')
   self.assertEqual(details.get_attribute('class'),'mma-winner-history')
   details.locator('summary').click()
   self.assertEqual(panel.locator('[data-field="pick"] .mma-box-value').inner_text(),p['selection'])
   self.assertEqual(panel.locator('[data-field="probability"] .mma-box-value').inner_text(),f"{p['probability']*100:.1f}%")
   self.assertEqual(panel.locator('[data-field="rating"] .tier-badge').inner_text(),p['tier'])
   self.assertEqual(panel.locator('.mma-rationale p').all_text_contents(),[x for x in p['rationale'].split('\n\n') if x.strip()])
   details.locator('summary').click()
 def test_missing_source_retains_all_sections_without_fake_estimates(self):
  page=self.page(390,status=404)
  self.assertEqual(page.locator('[data-prop-state="UNAVAILABLE"]').count(),56)
  self.assertEqual(page.locator('.mma-market-panel [data-probability]').count(),0)
  self.assertEqual(page.locator('.mma-winner-history').count(),14)
 def test_invalid_snapshots_are_rejected(self):
  page=self.page();cases={}
  for name in ['date','issuance','duplicate','probability','price','commercial','family','offered_line','current_outcomes','combined','distance','model']:
   d=copy.deepcopy(self.source)
   if name=='date':d['event_date']='2026-09-12'
   elif name=='issuance':d['original_issuance_id']='other'
   elif name=='duplicate':d['bouts'][1]=copy.deepcopy(d['bouts'][0])
   elif name=='probability':d['bouts'][0]['fighters'][0]['method'][0]['research_probability']=1.4
   elif name=='price':d['bouts'][0]['fighters'][0]['method'][0]['fanduel_price']=200
   elif name=='commercial':d['bouts'][0]['bet_ready']=True
   elif name=='family':d['bouts'][0]['families_evaluated'].remove('COMBINED_METHOD')
   elif name=='offered_line':d['bouts'][0]['total_rounds']['research_grid'][0]['fanduel_offering_verified']=True
   elif name=='current_outcomes':d['training']['outcomes_from_current_card_read']=1
   elif name=='combined':d['bouts'][0]['fighters'][0]['combined_method'][0]['research_probability']+=.01
   elif name=='distance':d['bouts'][0]['goes_distance']['yes']['research_probability']+=.01
   elif name=='model':d['model_sha256']='unidentified'
   cases[name]=d
  for name,d in cases.items():
   with self.subTest(name=name):
    self.assertTrue(page.evaluate('([d,t])=>{try{window.ApexMmaMarkets.validate(d,t);return false}catch(e){return true}}',[d,self.today]))
 def test_wrong_event_does_not_show_old_research(self):
  d=copy.deepcopy(self.source);d['event_date']='2026-09-12';page=self.page(source=d)
  self.assertEqual(page.locator('[data-prop-state="UNAVAILABLE"]').count(),56)
  self.assertEqual(page.locator('.mma-market-panel [data-probability]').count(),0)
 def test_html_in_selection_is_escaped(self):
  d=copy.deepcopy(self.source);d['bouts'][0]['fighters'][0]['method'][0]['selection']='<img src=x onerror="window.bad=1">';page=self.page(source=d)
  self.assertIsNone(page.evaluate('window.bad'));self.assertEqual(page.locator('.mma-market-panel img').count(),0)
if __name__=='__main__':unittest.main()
