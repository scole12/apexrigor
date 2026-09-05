"""Display the four actual MMA market families from the saved, unmodified run.
This renderer never runs inference, creates odds, assigns tiers or issues bets.
"""
FOUR_MARKET_STYLE = '''
<style id="mma-four-market-style">
.mma-four-market-page .mma-market-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px;margin:0 0 18px}
.mma-four-market-page .mma-market-panel{min-width:0;border:1px solid #626262;background:#0d0d0d;padding:20px 18px;overflow-wrap:anywhere}
.mma-four-market-page .mma-market-heading{display:flex;align-items:baseline;gap:10px;margin:0 0 13px}
.mma-four-market-page .mma-market-number{font-size:12px;color:#aaa;flex:none}
.mma-four-market-page .mma-market-title{font-size:16px;line-height:1.4;font-weight:600;margin:0;color:#f6f6f6}
.mma-four-market-page .mma-prop-state{display:block;font-size:11px;line-height:1.65;letter-spacing:.07em;text-transform:uppercase;color:#ccc;margin-bottom:14px}
.mma-four-market-page .mma-fighter-market{margin:16px 0 0}
.mma-four-market-page .mma-fighter-market h4{font-size:14px;line-height:1.4;margin:0 0 8px;color:#f2f2f2}
.mma-four-market-page .mma-prop-table{width:100%;table-layout:fixed;border-collapse:collapse;font-size:12px;line-height:1.55}
.mma-four-market-page .mma-prop-table th{font-size:10px;letter-spacing:.04em;font-weight:400;color:#bbb;text-align:left;padding:8px 4px;border-bottom:1px solid #414141}
.mma-four-market-page .mma-prop-table td{padding:9px 4px;vertical-align:top;border-bottom:1px solid #292929;color:#e7e7e7;overflow-wrap:anywhere}
.mma-four-market-page .mma-prop-table th:first-child{width:58%}
.mma-four-market-page .mma-prop-table th:nth-child(2){width:23%}
.mma-four-market-page .mma-prop-table th:nth-child(3){width:19%}
.mma-four-market-page .mma-prop-table .mma-number{white-space:nowrap;font-variant-numeric:tabular-nums}
.mma-four-market-page .mma-market-note{font-size:12px;line-height:1.65;color:#c4c4c4;margin:14px 0 0}
.mma-four-market-page .mma-line-missing{font-size:14px;line-height:1.55;margin:14px 0;color:#f0f0f0}
.mma-four-market-page .mma-reference-label{font-size:10px;line-height:1.65;letter-spacing:.05em;text-transform:uppercase;color:#ccc;margin:15px 0 5px}
.mma-four-market-page .mma-winner-history{border-top:1px solid #454545;padding:15px 0 0;margin-top:20px}
.mma-four-market-page .mma-winner-history summary{cursor:pointer;font-size:12px;line-height:1.65;color:#c8c8c8}
.mma-four-market-page .mma-winner-history[open]>.mma-position{margin-top:18px}
@media(max-width:760px){.mma-four-market-page .mma-market-grid{grid-template-columns:1fr;gap:14px}.mma-four-market-page .mma-market-panel{padding:18px 13px}.mma-four-market-page .mma-market-title{font-size:15px}}
</style>
'''
FOUR_MARKET_SCRIPT = r'''
<script>
window.ApexMmaMarkets=(()=>{
 const FAMILIES=['METHOD','COMBINED_METHOD','TOTAL_ROUNDS','GOES_DISTANCE'];
 const TITLES=['Fighter method of victory','Double Chance — combined methods','Total rounds','Fight goes the distance'];
 const M=window.ApexMmaDisplay,esc=M.esc;
 const probability=v=>Number.isFinite(v)&&v>=0&&v<=1;
 const percent=v=>probability(v)?(100*v).toFixed(1)+'%':'Not available';
 const close=(a,b)=>Math.abs(a-b)<1e-8;
 function require(ok,message){if(!ok)throw new Error(message)}
 function outcome(q){
  require(q&&typeof q.selection==='string'&&q.selection.trim()&&probability(q.research_probability),'Incomplete market outcome');
  require(q.bet_ready===false&&q.expected_value===null,'Research outcome cannot imply an issued or profitable wager');
  require(q.fanduel_price===null&&q.quote_status==='NO_VERIFIED_FANDUEL_QUOTE','Unexpected quote contract; do not relabel a price');
 }
 function validate(d,t){
  require(d&&d.schema==='APEX_MMA_FOUR_MARKET_ANALYSIS_V1','Unsupported four-market document');
  require(d.event_date===t.event?.event_date,'Wrong event date');
  require(d.original_issuance_id===t.issuance_id&&Boolean(t.issuance_id),'Wrong source issuance');
  require(d.run_status==='RESEARCH_PROJECTIONS_COMPLETE_BETTING_ISSUANCE_BLOCKED'&&d.confirmed_betting_positions===0,'Unsupported market release state');
  require(/^[0-9a-f]{64}$/.test(d.model_sha256||'')&&/^[0-9a-f]{64}$/.test(d.source_t3_sha256||''),'Missing model or input identity');
  require(d.training?.outcomes_from_current_card_read===0,'Current-card outcomes are not permitted');
  require(Number.isFinite(Date.parse(d.completed_at_utc)),'Missing research generation time');
  require(Array.isArray(d.bouts)&&d.bouts.length===t.card.length&&d.bout_count===d.bouts.length,'Incomplete all-bout coverage');
  require(d.unique_bout_family_sections===d.bouts.length*4,'Incomplete four-family coverage');
  const issued=new Map((t.positions||[]).map(p=>[p.bout_id,p]));
  require(issued.size===d.bouts.length,'Issuance membership mismatch');
  const seen=new Set();
  for(const b of d.bouts){
   require(issued.has(b.bout_id)&&!seen.has(b.bout_id),'Duplicate or foreign bout');seen.add(b.bout_id);
   require(FAMILIES.every(x=>b.families_evaluated?.includes(x)),'Missing market family');
   require(b.bet_ready===false&&b.model_status==='EXPERIMENTAL_NOT_COMMERCIAL_RELEASE','Unverified commercial market state');
   require(b.timing_label==='POST_CARD_START_RESEARCH_REPLAY_NOT_LIVE_IN_FIGHT_FORECAST','Unsupported research timing');
   require([3,5].includes(b.scheduled_rounds),'Unsupported scheduled-round count');
   require(Array.isArray(b.fighters)&&b.fighters.length===2&&new Set(b.fighters.map(x=>x.slot)).size===2,'Incomplete fighter pair');
   let jointSum=0;
   for(const f of b.fighters){
    require(['A','B'].includes(f.slot)&&typeof f.fighter==='string'&&f.fighter,'Invalid fighter identity');
    require(f.method?.length===3&&f.combined_method?.length===3,'Missing method outcomes');
    f.method.forEach(outcome);f.combined_method.forEach(outcome);
    const p=f.method.map(x=>x.research_probability),c=f.combined_method.map(x=>x.research_probability);
    require(close(c[0],p[0]+p[1])&&close(c[1],p[0]+p[2])&&close(c[2],p[1]+p[2]),'Combined methods do not reconcile');
    jointSum+=p.reduce((a,v)=>a+v,0);
   }
   require(close(jointSum,1),'Method probabilities do not reconcile');
   outcome(b.goes_distance?.yes);outcome(b.goes_distance?.no);
   require(close(b.goes_distance.yes.research_probability+b.goes_distance.no.research_probability,1),'Distance probabilities do not reconcile');
   require(Array.isArray(b.total_rounds?.verified_fanduel_lines)&&b.total_rounds.verified_fanduel_lines.length===0,'Unsupported verified-line contract');
   const grid=b.total_rounds?.research_grid;require(Array.isArray(grid)&&grid.length===b.scheduled_rounds,'Incomplete reference thresholds');
   let prior=1;
   for(const [i,g] of grid.entries()){
    require(g.line===i+.5&&g.fanduel_offering_verified===false&&g.basis==='MODEL_REFERENCE_THRESHOLD_NOT_VERIFIED_SPORTSBOOK_LINE','Unverified threshold presented as sportsbook line');
    outcome(g.over);outcome(g.under);
    require(close(g.over.research_probability+g.under.research_probability,1)&&g.over.research_probability<=prior+1e-8,'Incoherent totals probabilities');prior=g.over.research_probability;
   }
  }
  return d;
 }
 function table(rows,shorten){
  return '<table class="mma-prop-table"><thead><tr><th>Selection</th><th>Research %</th><th>FanDuel</th></tr></thead><tbody>'+rows.map(q=>'<tr data-market-selection="'+esc(q.selection)+'"><td>'+esc(shorten?shorten(q.selection):q.selection)+'</td><td class="mma-number" data-probability="'+q.research_probability+'">'+percent(q.research_probability)+'</td><td data-quote-status="MISSING" aria-label="No verified FanDuel quote">—</td></tr>').join('')+'</tbody></table>';
 }
 function fighterTables(b,key){
  return b.fighters.map(f=>'<div class="mma-fighter-market"><h4>'+esc(f.fighter)+'</h4>'+table(f[key],s=>s.startsWith(f.fighter+' by ')?s.slice((f.fighter+' by ').length):s)+'</div>').join('');
 }
 const note=s=>'<p class="mma-market-note">'+esc(s)+'</p>';
 const panel=(b,index,body)=>'<section class="mma-market-panel" data-prop-bout="'+esc(b.bout_id)+'" data-market-family="'+FAMILIES[index]+'" data-prop-state="RESEARCH_UNISSUED"><div class="mma-market-heading"><span class="mma-market-number mono">0'+(index+1)+'</span><h3 class="mma-market-title">'+esc(TITLES[index])+'</h3></div><span class="mma-prop-state mono">Research only · no issued prop pick</span>'+body+'</section>';
 function four(b){
  const support=b.fighters.map(f=>f.fighter+': '+f.prior_fight_count+' prior recorded bouts').join(' · ');
  const pricing=note('FanDuel price: not captured for this market. No betting-value or strength rating has been assigned.');
  const conditional=note('Conditional research estimates: draw, no-contest and disqualification are not modeled.');
  const method=panel(b,0,fighterTables(b,'method')+pricing+note(support+'. Missing history is not evidence of no professional experience.')+conditional);
  const combined=panel(b,1,fighterTables(b,'combined_method')+pricing+note('Each row adds two mutually exclusive winning methods for that fighter. These three alternative combinations overlap; they are not three independent bets.')+conditional);
  const grid=b.total_rounds.research_grid;
  const reference='<div class="mma-reference-label mono">Model reference thresholds — NOT verified FanDuel lines</div><table class="mma-prop-table mma-total-grid"><thead><tr><th>Reference rounds</th><th>Over %</th><th>Under %</th></tr></thead><tbody>'+grid.map(g=>'<tr data-reference-line="'+g.line+'" data-offering-verified="false"><td>'+g.line+'</td><td class="mma-number" data-market-selection="'+esc(g.over.selection)+'" data-probability="'+g.over.research_probability+'">'+percent(g.over.research_probability)+'</td><td class="mma-number" data-market-selection="'+esc(g.under.selection)+'" data-probability="'+g.under.research_probability+'">'+percent(g.under.research_probability)+'</td></tr>').join('')+'</tbody></table>';
  const totals=panel(b,2,'<p class="mma-line-missing">Actual FanDuel rounds line: <strong>not captured</strong></p>'+reference+pricing+note('No Over/Under wager can be specified without the actual offered line and its price. The saved timing model uses historical within-round finishing times; reference thresholds are not sportsbook offers.')+conditional);
  const distance=panel(b,3,table([b.goes_distance.yes,b.goes_distance.no],s=>s.endsWith('Yes')?'Yes — full distance':'No — ends early')+pricing+note('This fight is scheduled for '+b.scheduled_rounds+' rounds. Full distance is separate from a points result: an early technical decision does not mean the scheduled duration was completed.')+note('This is one shared fight outcome, not a separate wager for each fighter.')+conditional);
  return '<div class="mma-market-grid" aria-label="Four betting market families">'+method+combined+totals+distance+'</div>';
 }
 function unavailable(boutId,reason){
  return '<div class="mma-market-grid" aria-label="Four betting market families">'+FAMILIES.map((family,i)=>'<section class="mma-market-panel" data-prop-bout="'+esc(boutId)+'" data-market-family="'+family+'" data-prop-state="UNAVAILABLE"><div class="mma-market-heading"><span class="mma-market-number mono">0'+(i+1)+'</span><h3 class="mma-market-title">'+esc(TITLES[i])+'</h3></div><span class="mma-prop-state mono">Not issued</span><p class="mma-line-missing">No verified '+(family==='TOTAL_ROUNDS'?'FanDuel line or price':'FanDuel price')+' available in this page payload.</p>'+note(reason)+note('No selection, probability or rating has been invented.')+'</section>').join('')+'</div>';
 }
 function render(t,d,reason='The saved four-market analysis is unavailable for this event.'){
  const container=document.createElement('div'),rows=M.checkIssued(t);
  container.innerHTML=M.board(t.card||[],rows);
  const byBout=new Map((d?.bouts||[]).map(b=>[b.bout_id,b]));
  for(const card of container.querySelectorAll('.mma-fight')){
   const old=Array.from(card.querySelectorAll('.mma-position'));
   const bid=old[0]?.dataset.positionBout||card.dataset.bout,b=byBout.get(bid);
   const history=document.createElement('details');history.className='mma-winner-history';
   const summary=document.createElement('summary');summary.textContent='Previously issued Winner — selection, price, rating and original rationale';history.append(summary);
   for(const position of old)history.append(position);
   const heading=card.querySelector('.game-header');heading.insertAdjacentHTML('afterend',b?four(b):unavailable(bid,reason));
   if(old.length)card.append(history);
   card.setAttribute('data-four-market-count','4');
  }
  return container.innerHTML;
 }
 async function load(t){
  const day=String(t.event?.event_date||'');
  if(!/^\d{4}-\d{2}-\d{2}$/.test(day))return {data:null,reason:'No current event date is available.'};
  try{
   const response=await fetch('/data/mma_four_markets_'+day.replaceAll('-','')+'.json',{cache:'no-store'});
   if(!response.ok)return {data:null,reason:'The four-market analysis has not been published for this event.'};
   return {data:validate(await response.json(),t),reason:null};
  }catch(error){return {data:null,reason:'The saved four-market analysis could not be verified against this issuance.'};}
 }
 return {validate,render,load,FAMILIES,TITLES};
})();
</script>
'''
