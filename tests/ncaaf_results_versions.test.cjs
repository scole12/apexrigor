const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(__dirname + '/../ncaaf/results/render.js', 'utf8');
const base = {game_id:'game000001', slate_date:'2026-10-17', market:'ATS', matchup:'A at B', pick:'A +3', as_issued_tier:'WEAK', tier:'ELITE', tier_policy_sha256:'v3hash', rating_version:'SLATE-QUARTILES-V3', result:'W', daily_record_eligible:true};
async function render(positions) {
  const root = {};
  const record = {W:2,L:1,PUSH:1};
  vm.runInNewContext(source, {document:{getElementById:()=>root}, fetch:async()=>({ok:true,json:async()=>({positions, season_record:record, ats_record:record, totals_record:record})}), console});
  await new Promise(resolve=>setImmediate(resolve));
  return root.innerHTML;
}
test('separates versions, keeps original tier and uses revised public tier', async()=>{
  const html=await render([base,{...base,game_id:'game000002',tier:'MODERATE',as_issued_tier:'MODERATE',tier_policy_sha256:'oldhash',rating_version:'ENGINE-V2',result:'L'}]);
  assert.match(html,/SLATE-QUARTILES-V3/); assert.match(html,/ENGINE-V2/);
  const v3=html.slice(html.indexOf('SLATE-QUARTILES-V3'),html.indexOf('ENGINE-V2'));
  assert.match(v3,/Elite<\/td><td class="mono">1-0-0P/);
  assert.match(html,/>ELITE<\/td><td class="mono">WEAK<\/td><td class="mono">SLATE-QUARTILES-V3/);
});
test('preserves push, excludes post-kickoff records from tier results, retains archive rows', async()=>{
  const html=await render([{...base,result:'PUSH'},{...base,result:'EXCLUDED_POST_KICKOFF',daily_record_eligible:false}]);
  assert.match(html,/Elite<\/td><td class="mono">0-0-1P/);
  assert.match(html,/EXCLUDED_POST_KICKOFF/); assert.match(html,/2 POSITIONS/);
  assert.match(html,/data-apex-season-record="2-1-1P"/);
});
test('never infers rating identity from a date, including future rows', async()=>{
  const html=await render([{...base,tier_policy_sha256:null,slate_date:'2099-01-01'}]);
  assert.match(html,/Historical ratings — definition not recorded/);
  assert.doesNotMatch(html,/SLATE-QUARTILES-V3/);
});
test('escapes source labels and keeps all four tiers even with zero observations', async()=>{
  const html=await render([{...base,rating_version:'<script>bad</script>'}]);
  assert.match(html,/&lt;script&gt;bad&lt;\/script&gt;/); assert.doesNotMatch(html,/<script>bad/);
  for (const tier of ['Weak','Moderate','Strong','Elite']) assert.match(html,new RegExp('>'+tier+'<'));
});

test('shows pending tier population before results arrive', async()=>{
  const html=await render([{...base,result:'PENDING'}]);
  assert.match(html,/Elite<\/td><td class="mono">0-0-0P<\/td><td class="mono">—<\/td><td class="mono">1<\/td>/);
});
