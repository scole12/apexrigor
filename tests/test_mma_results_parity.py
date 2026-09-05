"""MMA Results parity and outcome accounting; fixture grades never leave the browser."""
import copy, hashlib, json, mimetypes, os, unittest
from pathlib import Path
from urllib.parse import urlparse, unquote
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
class MmaResultsParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.today=json.loads((ROOT/'data/mma_today.json').read_text())
        if len(cls.today.get('positions',[]))<4:raise unittest.SkipTest('Requires at least four real issued positions for the layout fixture')
        cls.summary=json.loads((ROOT/'data/mma_results_summary.json').read_text())
        cls.archive=json.loads((ROOT/'data/mma_results_archive.json').read_text())
        cls.before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'mma/index.html',*(ROOT/'data').glob('mma*.json')]}
        cls.pw=sync_playwright().start()
        cls.browser=cls.pw.chromium.launch(headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
    @classmethod
    def tearDownClass(cls):
        cls.browser.close();cls.pw.stop()
        assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in cls.before.items())
    def page(self,width=1536,summary=None):
        context=self.browser.new_context(viewport={'width':width,'height':1100});self.addCleanup(context.close)
        def serve(route):
            u=urlparse(route.request.url);path=ROOT/unquote(u.path).lstrip('/')
            if u.hostname!='mma-results.test':route.abort();return
            if u.path=='/data/mma_results_summary.json' and summary is not None:route.fulfill(status=200,content_type='application/json',body=json.dumps(summary));return
            if u.path=='/data/mma_results_archive.json' and summary is not None:route.fulfill(status=200,content_type='application/json',body=json.dumps({'events':[]}));return
            if path.is_dir():path=path/'index.html'
            if not path.resolve().is_relative_to(ROOT) or not path.is_file():route.fulfill(status=404,body='Missing');return
            route.fulfill(status=200,content_type=mimetypes.guess_type(str(path))[0] or 'application/octet-stream',body=path.read_bytes())
        context.route('**/*',serve);page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('http://mma-results.test/mma/results');page.wait_for_function("document.getElementById('results-meta').textContent!=='LOADING RESULTS'")
        self.assertEqual(errors,[]);return page
    def project(self,page,summary=None,archive=None,today=None):
        return page.evaluate('([t,s,a])=>window.ApexMmaResults.ledger(t,s,a,window.ApexMmaDisplay.checkIssued)',[today or self.today,summary or self.summary,archive or self.archive])
    def grade(self,index,result,**extra):
        p=self.today['positions'][index]
        return {'issuance_id':self.today['issuance_id'],'bout_id':p['bout_id'],'market':p['market'],'selection':p['selection'],'result':result,**extra}
    def test_real_results_desktop_mobile_and_exact_issued_values(self):
        for width in [1536,768,390,320]:
            with self.subTest(width=width):
                page=self.page(width);self.assertTrue(page.locator('#results-root').is_visible())
                headings=page.locator('.section-head .title').all_text_contents()
                for heading in ['SEASON RECORD','AS-ISSUED TIER PERFORMANCE','DAILY ARCHIVE','LATEST EVENT']:self.assertIn(heading,headings)
                self.assertEqual(page.locator('.position-ledger tbody tr').count(),len(self.today['positions']))
                self.assertEqual(page.locator('.mma-pick-box,.mma-fight,#prelims,#maincard,#t3time,#t2time').count(),0)
                projected=self.project(page)
                stats=page.evaluate('(rows)=>{const R=window.ApexMmaResults,r=R.record(rows);return {record:R.recordText(r),rate:R.winRate(r),pending:r.PENDING}}',projected['positions'])
                self.assertEqual(page.locator('#season-record').inner_text(),stats['record'])
                self.assertEqual(page.locator('#season-win-rate').inner_text(),stats['rate'])
                self.assertEqual(page.locator('#pending-count').inner_text(),str(stats['pending']))
                for p in self.today['positions']:
                    row=page.locator('.position-ledger [data-position-bout="'+p['bout_id']+'"]')
                    self.assertEqual(row.locator('[data-field="pick"]').inner_text(),p['selection'])
                    self.assertEqual(row.locator('[data-field="price"]').inner_text(),('+' if p['price']>0 else '')+str(p['price']))
                    self.assertEqual(row.locator('[data-field="probability"]').inner_text(),f"{p['probability']*100:.1f}%")
                    self.assertEqual(row.locator('[data-field="rating"]').inner_text(),p['tier'])
                    expected=next(x['result'] for x in projected['positions'] if x['bout_id']==p['bout_id'] and x['issuance_id']==self.today['issuance_id'])
                    self.assertEqual(row.get_attribute('data-result'),expected)
                    if width<=700:
                        self.assertIn('Issued pick',row.locator('[data-field=pick]').evaluate('(e)=>getComputedStyle(e,"::before").content'))
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),width+1)
                proof=os.environ.get('APEX_MMA_RESULTS_PROOF_DIR')
                if proof and width in [1536,390]:
                    folder=Path(proof);folder.mkdir(parents=True,exist_ok=True)
                    page.locator('main').screenshot(path=str(folder/f'RESULTS_{width}.png'))
    def test_only_recorded_outcomes_count(self):
        summary=copy.deepcopy(self.summary);summary['latest_event_results']=[self.grade(0,'W'),self.grade(1,'L'),self.grade(2,'P'),self.grade(3,'VOID')]
        page=self.page(summary=summary)
        self.assertEqual(page.locator('#season-record').inner_text(),'1-1-1P-1V')
        self.assertEqual(page.locator('#season-win-rate').inner_text(),'50.0%')
        self.assertEqual(page.locator('#pending-count').inner_text(),str(len(self.today['positions'])-4))
    def test_duplicate_equal_grade_does_not_double_count(self):
        summary=copy.deepcopy(self.summary);summary['latest_event_results']=[self.grade(0,'W'),self.grade(0,'W')]
        page=self.page(summary=summary);self.assertEqual(page.locator('#season-record').inner_text(),'1-0')
    def test_conflicting_grades_fail_closed(self):
        summary=copy.deepcopy(self.summary);summary['latest_event_results']=[self.grade(0,'W'),self.grade(0,'L')]
        page=self.page(summary=summary);self.assertTrue(page.locator('#results-error').is_visible());self.assertFalse(page.locator('#results-root').is_visible())
    def test_foreign_issuance_is_not_graded(self):
        summary=copy.deepcopy(self.summary);summary['latest_event_results']=[self.grade(0,'W',issuance_id='SYNTHETIC-OTHER-ISSUANCE')]
        page=self.page(summary=summary);self.assertEqual(page.locator('#season-record').inner_text(),'0-0');self.assertTrue(page.locator('#coverage-warning').is_visible())
    def test_unknown_bout_does_not_create_a_result(self):
        summary=copy.deepcopy(self.summary);summary['latest_event_results']=[self.grade(0,'W',bout_id='SYNTHETIC-UNKNOWN-BOUT')]
        page=self.page(summary=summary);self.assertEqual(page.locator('#season-record').inner_text(),'0-0')
    def test_unsettled_result_is_not_loss(self):
        summary=copy.deepcopy(self.summary);summary['latest_event_results']=[self.grade(0,'IN_PROGRESS')]
        page=self.page(summary=summary);self.assertEqual(page.locator('#season-record').inner_text(),'0-0');self.assertEqual(page.locator('#season-win-rate').inner_text(),'—')
    def test_same_issuance_archive_is_not_duplicated(self):
        page=self.page();archive={'events':[copy.deepcopy(self.today)]}
        result=self.project(page,archive=archive);self.assertEqual(len(result['positions']),len(self.today['positions']))
    def test_research_is_excluded_from_results(self):
        page=self.page();archive={'events':[{'official_issuance':False,'status':'UNVALIDATED_RESEARCH_NOT_OFFICIAL_ISSUANCE','positions':[{'result':'W'}]}]}
        result=self.project(page,archive=archive);self.assertEqual(len(result['positions']),len(self.today['positions']));self.assertTrue(all(p['result']=='PENDING' for p in result['positions']))
    def test_missing_archive_is_disclosed(self):
        summary=copy.deepcopy(self.summary);summary['issued_event_count']=99
        page=self.page(summary=summary);self.assertIn('Earlier issued event details',page.locator('#coverage-warning').inner_text())
    def test_record_counts_and_denominator(self):
        page=self.page();r=page.evaluate("()=>{const R=window.ApexMmaResults,r=R.record([{result:'W'},{result:'W'},{result:'L'},{result:'P'},{result:'VOID'},{result:'PENDING'}]);return {r,text:R.recordText(r),rate:R.winRate(r)}}")
        self.assertEqual(r['r'],{'W':2,'L':1,'P':1,'VOID':1,'PENDING':1});self.assertEqual(r['rate'],'66.7%')
    def test_tier_labels_and_pending_counts_are_as_issued(self):
        page=self.page()
        for tier in ['WEAK','MODERATE','STRONG','ELITE']:
            row=page.locator('#tier-performance [data-apex-tier="'+tier+'"]')
            expected=sum(p['tier']==tier for p in self.today['positions'])
            self.assertEqual(row.locator('td').nth(3).inner_text(),str(expected))
    def test_grade_markup_is_escaped(self):
        summary=copy.deepcopy(self.summary);summary['latest_event_results']=[self.grade(0,'<script>bad()</script>')]
        page=self.page(summary=summary);self.assertEqual(page.locator('.result-mark--PENDING').count(),len(self.today['positions']))
if __name__=='__main__':unittest.main()
