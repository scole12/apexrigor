const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../nba/results/render.js'), 'utf8');
const fixture = {sport:'NBA', slates:[{slate_date:'2026-10-20', week_start:'2026-10-19', positions:
  ['W','L','P','W','L','W'].map((result,i)=>({position_id:`FIXTURE_${i}`, game_id:`NBA_FIXTURE_G0${Math.floor(i/2)+1}`,
    matchup:['Fixture Away A @ Fixture Home A','Fixture Away B @ Fixture Home B','Fixture Away C @ Fixture Home C'][Math.floor(i/2)],
    market:i%2?'TOTALS':'ATS', selection:i%2?'Over 220.5':'Fixture Away +3.5',
    tier:['Weak','Moderate','Strong','Elite','Weak','Moderate'][i],result}))}]};
async function render(archive, code=source, sport='nba') {
  const root={dataset:{},innerHTML:''};
  vm.runInNewContext(code, {document:{getElementById:()=>root},fetch:async url=>{
    assert.equal(url,`/data/${sport}_results_archive.json`);
    return {ok:true,json:async()=>archive};
  },console:{error:()=>{}},Intl,Date,Map,Set});
  await new Promise(resolve=>setImmediate(resolve));
  return root;
}
(async()=>{
  let root=await render({sport:'NBA',slates:[]});
  assert.equal(root.dataset.status,'UNISSUED');
  assert.match(root.innerHTML,/data-apex-season-record="0-0"/);
  assert.match(root.innerHTML,/data-apex-season-win-rate="—"/);
  assert.match(root.innerHTML,/UNISSUED — No NBA picks have been issued\./);
  const nhl=await render({sport:'NHL',status:'UNISSUED',issuances:[],grades:[]},fs.readFileSync(path.join(__dirname,'../nhl/results/render.js'),'utf8'),'nhl');
  const normalized=nhl.innerHTML.replaceAll('NHL','NBA').replaceAll('Totals O/U','TOTALS').replaceAll('TOTALS O/U','TOTALS').replaceAll('Underdog +1.5','ATS').replaceAll('UNDERDOG +1.5','ATS').replaceAll('data-apex-underdog-record','data-apex-ats-record');
  assert.equal(root.innerHTML,normalized,'Empty results must use identical NHL components/classes/wording, with NBA market names');
  assert.deepEqual(fs.readFileSync(path.join(__dirname,'../nba/results/results.css')),fs.readFileSync(path.join(__dirname,'../nhl/results/results.css')));
  root=await render(fixture);
  assert.equal(root.dataset.status,'ISSUED');
  assert.equal(new Set(fixture.slates[0].positions.map(p=>p.game_id)).size,3);
  for(const marker of ['data-apex-season-record="3-2-1P"','data-apex-season-win-rate="60.0%"','data-apex-ats-record="1-1-1P"','data-apex-totals-record="2-1"','6 NBA POSITIONS TRACKED','6 POSITIONS','AS-ISSUED TIER PERFORMANCE','DAILY ARCHIVE','SLATE DETAIL — 2026-10-20']) assert.ok(root.innerHTML.includes(marker),marker);
  assert.equal((root.innerHTML.match(/<table class="results">/g)||[]).length,5);
  assert.equal((root.innerHTML.match(/<td class="mono">NBA_FIXTURE_G/g)||[]).length,6);
  assert.ok(!/units|stake|moneyline|Not yet available/.test(root.innerHTML));
  // Retain pending/void facts while only W and L enter win rate.
  const pending={sport:'NBA',slates:[{slate_date:'2026-10-21',positions:fixture.slates[0].positions.map((p,i)=>({...p,result:[null,'V','W','L','P',null][i]}))}]};
  root=await render(pending);
  assert.match(root.innerHTML,/data-apex-season-record="1-1-1P"/);
  assert.match(root.innerHTML,/data-apex-season-win-rate="50.0%"/);
  assert.match(root.innerHTML,/>PENDING<\/td>/);
  assert.match(root.innerHTML,/>V<\/td>/);
  const onlyPending=structuredClone(pending);onlyPending.slates[0].positions.forEach(p=>p.result=null);
  root=await render(onlyPending);assert.ok(!root.innerHTML.includes('SLATE DETAIL — 2026-10-21'));
  for(const mutation of [a=>a.sport='NHL',a=>a.slates[0].positions[0].sport='NHL',a=>a.slates[0].positions[0].market='MONEYLINE',a=>a.slates[0].positions[0].engine='baseline:fixture',a=>a.slates[0].positions[0].engine_version='baseline:fixture',a=>a.slates[0].positions[0].result='bad',a=>a.slates[0].positions.push(a.slates[0].positions[0])]) {
    const bad=structuredClone(fixture);mutation(bad);assert.equal((await render(bad)).dataset.status,'UNAVAILABLE');
  }
  const escaped=structuredClone(fixture);escaped.slates[0].positions[0].selection='<script>alert(1)</script>';
  assert.ok((await render(escaped)).innerHTML.includes('&lt;script&gt;'));
  if(process.argv[2]==='--fixture') fs.writeFileSync(process.argv[3],JSON.stringify(fixture,null,2));
  console.log('PASS: NHL empty markup/CSS parity; 3 games / 6 grades; W-L-P and 60.0%; market/tier/daily/detail tables; pending/void; sport/baseline/invalid rejection; escaping.');
})().catch(error=>{console.error(error);process.exitCode=1;});
