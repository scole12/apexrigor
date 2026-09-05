#!/usr/bin/env python3
"""Render sealed MMA picks and full rationale using MLB/NCAA display classes."""
from _mma_public import close,head,hero,navigation,write
from _mma_forecast_display import DISPLAY_SCRIPT
SCRIPT=r'''
<script>
const M=window.ApexMmaDisplay;
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
