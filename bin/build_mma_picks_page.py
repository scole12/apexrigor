#!/usr/bin/env python3
"""Render sealed MMA picks and full rationale using MLB/NCAA display classes."""
from _mma_public import close,head,hero,navigation,write
from _mma_forecast_display import DISPLAY_SCRIPT
SCRIPT=r'''
<script>
const M=window.ApexMmaDisplay;

function showResearch(d){
 if(d.picks_published||!/^\d{4}-\d{2}-\d{2}$/.test(String(d.event?.event_date||'')))return;
 const day=d.event.event_date;
 fetch('/data/mma_research_'+day+'.json',{cache:'no-store'}).then(r=>{if(!r.ok)return null;return r.json()}).then(r=>{
  if(!r)return;
  if(r.event_date!==day||r.status!=='UNVALIDATED_RESEARCH_NOT_OFFICIAL_ISSUANCE'||r.official_issuance!==false||r.scientific_release!=='NO')return;
  if(!Array.isArray(r.forecasts)||r.forecasts.length!==r.forecast_count||!r.forecast_count||r.forecast_count!==(d.card||[]).length)return;
  if(!(Date.parse(r.generated_at_utc)<Date.parse(r.event_start_utc)))return;
  if(r.forecasts.some(p=>!Number.isFinite(p.probability)||p.probability<0||p.probability>1||!Array.isArray(p.rationale)||p.rationale.length!==6||p.rationale.some(x=>typeof x!=='string')))return;
  const panels=r.forecasts.map(p=>`<article class="game-module" data-position-state="RESEARCH"><header class="game-header"><div class="game-num mono">F${String(p.order).padStart(2,'0')}</div><div class="game-meta"><h2 class="game-matchup">${M.esc(p.matchup)}</h2><p class="meta mono">WINNER FORECAST · UNVALIDATED RESEARCH</p></div></header><div class="market-grid market-grid--single"><section class="market-panel"><div class="market-label">RESEARCH MODEL SELECTION</div><div class="market-panel-head"><span class="pick-headline">${M.esc(p.selection)}</span><span class="rating-label">NO VALIDATED STRENGTH RATING</span></div><div class="meta mono">MODEL: ${(p.probability*100).toFixed(1)}% · ORIGINAL T-2 FANDUEL: ${M.esc(M.odds(p.price))} · PRICE BREAK-EVEN: ${(p.bookmaker_break_even_probability*100).toFixed(1)}%</div><div class="rationale-copy" aria-label="Research pick rationale">${p.rationale.map(t=>'<p>'+M.esc(t)+'</p>').join('')}</div></section></div></article>`).join('');
  document.getElementById('forecast-status').textContent='OFFICIAL T-2 NOT ISSUED · RESEARCH AVAILABLE';
  document.getElementById('forecast-headline').textContent='14 research model picks are available below';
  document.getElementById('forecast-copy').textContent='These are actual model forecasts generated '+M.stamp(r.generated_at_utc)+', after T-2 and before the event. The model has not demonstrated a reliable betting advantage. These are not an approved T-2 card and are excluded from official performance grading. Original T-2 prices are not a claim of current availability.';
  document.getElementById('forecast-status-panel').setAttribute('data-forecast-status','UNVALIDATED_RESEARCH');
  document.getElementById('card-title').textContent='RESEARCH PICKS & DETAILED RATIONALE';
  document.getElementById('card-meta').textContent='UNVALIDATED · NO PROVEN EDGE · NO FABRICATED RATINGS';
  document.getElementById('games').innerHTML=panels;
  document.getElementById('issuance-meta').innerHTML='OFFICIAL ISSUED POSITIONS: 0 · RESEARCH FORECASTS: '+r.forecast_count+' · <a href="/mma/research/'+day+'">OPEN RESEARCH REPORT</a>';
 }).catch(()=>{});
}
fetch('/data/mma_today.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error('HTTP '+r.status);return r.json()}).then(d=>{
 const e=d.event||{},positions=Array.isArray(d.positions)?d.positions:[],card=Array.isArray(d.card)?d.card:[];
 if(positions.length&&(!d.picks_published||!d.issuance_id||!d.active_model_sha256))throw new Error('Issued forecast identity is incomplete');
 const s=M.status(d);
 document.querySelector('.shell').setAttribute('data-public-issuance',positions.length?'true':'false');
 document.getElementById('slate-meta').textContent=`${e.event_date||''} · ${card.length} BOUTS · ${positions.length} ISSUED POSITIONS`;
 document.getElementById('event-title').textContent=e.display_name||e.name||'UFC EVENT';
 document.getElementById('event-meta').textContent=[e.venue,e.city,e.country].filter(Boolean).join(' · ');
 for(const [id,v] of [['prelims',e.prelims_start_utc],['maincard',e.main_card_start_utc],['t3time',d.t3?.scheduled_utc],['t2time',d.t2?.scheduled_utc]])document.getElementById(id).textContent=M.clock(v);
 document.getElementById('forecast-status').textContent=s.code.replaceAll('_',' ');
 document.getElementById('forecast-headline').textContent=s.headline;
 document.getElementById('forecast-copy').textContent=s.detail;
 document.getElementById('forecast-status-panel').setAttribute('data-forecast-status',s.code);
 document.getElementById('card-title').textContent=positions.length?'PICKS & DETAILED RATIONALE':'FIGHT CARD — NO ISSUED PICKS';
 document.getElementById('card-meta').textContent=positions.length?'FANDUEL AT ISSUANCE · RATINGS AS ISSUED':'SCHEDULE ONLY · NOT A FORECAST';
 document.getElementById('games').innerHTML=M.board(card,positions)||'<p class="meta mono">CURRENT CARD UNAVAILABLE</p>';
 document.getElementById('issuance-meta').textContent=positions.length?`ISSUANCE ${d.issuance_id} · MODEL ${d.active_model} · UPDATED ${M.stamp(d.generated_at_utc)}`:`LAST STATUS UPDATE ${M.stamp(d.generated_at_utc)}`;
 showResearch(d);
}).catch(error=>{
 document.getElementById('slate-meta').textContent='MMA FORECAST DATA UNAVAILABLE';
 document.getElementById('forecast-headline').textContent='Forecast unavailable';
 document.getElementById('forecast-status').textContent='DATA ERROR';
 document.getElementById('forecast-copy').textContent='No picks are displayed because the forecast data could not be verified.';
 document.getElementById('games').textContent='';
});
</script>
'''
def main():
 html=head('APEX — MMA Picks','APEX UFC / MMA picks, FanDuel prices, probabilities, ratings and detailed rationale.','/mma')+'\n'+hero()+'\n'+navigation('PICKS')
 html+='''
 <div class="section-head picks-board-head"><div class="title">UFC / MMA CARD</div><div class="meta mono" id="slate-meta">LOADING FORECAST STATUS</div></div>
 <main class="picks-page">
 <div class="section-head"><div class="title" id="event-title">UFC EVENT</div><div class="meta mono" id="event-meta"></div></div>
 <div class="banner">
 <div class="cell"><div class="label">Prelims</div><div class="val mono" id="prelims">—</div></div>
 <div class="cell"><div class="label">Main Card</div><div class="val mono" id="maincard">—</div></div>
 <div class="cell"><div class="label">T-3 Data</div><div class="val mono" id="t3time">—</div></div>
 <div class="cell"><div class="label">T-2 Forecast</div><div class="val mono" id="t2time">—</div></div>
 </div>
 <div class="section-head"><div class="title">FORECAST STATUS</div><div class="meta mono" id="forecast-status">CHECKING ISSUANCE</div></div>
 <div class="market-grid market-grid--single"><section class="market-panel" id="forecast-status-panel"><div class="market-label">T-2 FORECAST</div><div class="pick-headline" id="forecast-headline">Checking the issued forecast</div><div class="rationale-copy"><p id="forecast-copy">Reading the current UFC / MMA forecast record.</p></div></section></div>
 <div class="section-head"><div class="title" id="card-title">FIGHT CARD</div><div class="meta mono" id="card-meta"></div></div>
 <div class="picks-board" id="games" aria-live="polite"></div>
 <p class="meta mono" id="issuance-meta"></p>
 </main>'''+DISPLAY_SCRIPT+SCRIPT+close()
 print('MMA_PICKS_PATH='+str(write('mma/index.html',html)));return 0
if __name__=='__main__':raise SystemExit(main())
