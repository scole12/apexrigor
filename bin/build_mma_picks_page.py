#!/usr/bin/env python3
"""Show four actual market families for every bout; preserve issued Winner records."""
from _mma_public import close,head,hero,navigation,write
from _mma_forecast_display import DISPLAY_SCRIPT,DISPLAY_STYLE
from _mma_four_market_display import FOUR_MARKET_SCRIPT,FOUR_MARKET_STYLE
SCRIPT=r'''
<script>
const M=window.ApexMmaDisplay,F=window.ApexMmaMarkets;
fetch('/data/mma_today.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error('HTTP '+r.status);return r.json()}).then(async d=>{
 const e=d.event||{},positions=M.checkIssued(d),card=Array.isArray(d.card)?d.card:[];
 const loaded=await F.load(d),research=loaded.data,s=M.status(d);
 document.querySelector('.shell').setAttribute('data-public-issuance',positions.length?'true':'false');
 document.querySelector('.shell').setAttribute('data-four-market-state',research?'RESEARCH_UNISSUED':'UNAVAILABLE');
 document.getElementById('slate-meta').textContent=`${e.event_date||''} · ${card.length} BOUTS · ${card.length*4} MARKET SECTIONS`;
 document.getElementById('event-title').textContent=e.display_name||e.name||'UFC EVENT';
 document.getElementById('event-meta').textContent=[e.venue,e.city,e.country].filter(Boolean).join(' · ');
 document.getElementById('compact-issuance').textContent=research?'RESEARCH REPLAY · '+M.stamp(research.completed_at_utc)+' · AFTER CARD START':'FOUR-MARKET ANALYSIS UNAVAILABLE';
 document.getElementById('card-title').textContent='FOUR MARKETS FOR EVERY FIGHT';
 document.getElementById('card-meta').textContent='METHOD · DOUBLE CHANCE · ROUNDS · DISTANCE';
 document.getElementById('games').innerHTML=F.render(d,research,loaded.reason);
 document.getElementById('forecast-status').textContent=s.code.replaceAll('_',' ');
 document.getElementById('forecast-headline').textContent='Previously issued Winner record';
 document.getElementById('forecast-copy').textContent=s.detail;
 document.getElementById('forecast-status-panel').setAttribute('data-forecast-status',s.code);
 document.getElementById('issuance-meta').textContent=positions.length?`${positions.length} PREVIOUSLY ISSUED WINNER SELECTIONS · ISSUANCE ${d.issuance_id} · MODEL ${d.active_model}`:'No current Winner issuance';
 document.getElementById('market-details').textContent=research?'Four-market run: '+research.completed_at_utc+' · '+research.confirmed_betting_positions+' issued prop bets · '+research.market_capture.verified_requested_prop_quotes+' verified requested prop quotes. Saved experimental probabilities only; not live forecasts and not an on-time pre-event issuance.':loaded.reason;
 document.getElementById('market-caveats').innerHTML=research?(research.caveats||[]).map(x=>'<p>'+M.esc(x)+'</p>').join(''):'';
 document.getElementById('games').setAttribute('data-render-complete','true');
}).catch(error=>{
 document.getElementById('slate-meta').textContent='MMA CARD DATA UNAVAILABLE';
 document.getElementById('compact-issuance').textContent='CURRENT EVENT COULD NOT BE VERIFIED';
 document.getElementById('games').textContent='The current event or its issued identity could not be verified. No positions were generated.';
 document.getElementById('games').setAttribute('data-render-complete','error');
});
</script>
'''
def main():
 html=head('APEX — MMA Picks','Four UFC / MMA markets per fight: method, Double Chance, total rounds and goes the distance.','/mma')+'\n'+hero()+'\n'+navigation('PICKS')
 html=html.replace('<body>','<body class="mma-four-box-page mma-four-market-page">').replace('</head>',DISPLAY_STYLE+'\n'+FOUR_MARKET_STYLE+'\n</head>')
 html+='''
 <div class="section-head picks-board-head"><div class="title">UFC / MMA CARD</div><div class="meta mono" id="slate-meta">LOADING FOUR-MARKET CARD</div></div>
 <main class="picks-page">
 <div class="section-head"><div class="title" id="event-title">UFC EVENT</div><div class="meta mono" id="event-meta"></div></div>
 <div class="mma-compact-status mono"><span id="compact-issuance">READING SAVED MARKET RUN</span><span>Prop prices not verified · <a href="#issuance-details">Source &amp; timing details</a></span></div>
 <div class="section-head"><div class="title" id="card-title">FOUR MARKETS FOR EVERY FIGHT</div><div class="meta mono" id="card-meta"></div></div>
 <div class="picks-board" id="games" aria-live="polite"></div>
 <details class="mma-audit-details" id="issuance-details"><summary>Source, timing &amp; issuance details</summary><p id="market-details"></p><div id="market-caveats"></div><div id="forecast-status-panel"><p class="mono" id="forecast-status"></p><h3 id="forecast-headline"></h3><p id="forecast-copy"></p><p class="mono" id="issuance-meta"></p><p>The original Winner selections remain unchanged and available under each fight. Their ratings do not apply to the four prop markets above. Research prop outcomes are excluded from the official Results ledger.</p></div></details>
 </main>'''+DISPLAY_SCRIPT+FOUR_MARKET_SCRIPT+SCRIPT+close()
 print('MMA_PICKS_PATH='+str(write('mma/index.html',html)));return 0
if __name__=='__main__':raise SystemExit(main())
