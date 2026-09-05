#!/usr/bin/env python3
"""Display actual grading state beside the unchanged issued MMA card."""
from _mma_public import close,head,hero,navigation,write
from _mma_forecast_display import DISPLAY_SCRIPT,DISPLAY_STYLE
SCRIPT=r'''
<script>
const M=window.ApexMmaDisplay;
Promise.all(['/data/mma_results_summary.json','/data/mma_today.json'].map(url=>fetch(url,{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error('HTTP '+r.status);return r.json()}))).then(([r,t])=>{
 const positions=M.checkIssued(t),card=Array.isArray(t.card)?t.card:[],e=t.event||{};
 const issued=Number(r.issued_event_count||0),graded=Number(r.graded_scientific_object_count||0);
 const rows=Array.isArray(r.latest_event_results)?r.latest_event_results:[];
 document.getElementById('results-meta').textContent=`${issued} ISSUED EVENTS · ${positions.length} CURRENT PICKS · ${graded} GRADED OBJECTS`;
 document.getElementById('issued').textContent=issued;
 document.getElementById('graded').textContent=graded;
 document.getElementById('current-picks').textContent=positions.length;
 document.getElementById('event-title').textContent=e.display_name||e.name||'UFC EVENT';
 document.getElementById('event-meta').textContent=[e.event_date,e.venue,e.city].filter(Boolean).join(' · ');
 document.getElementById('compact-issuance').textContent=M.compactStatus(t);
 if(rows.length){
  document.getElementById('results').innerHTML=rows.map(x=>`<article class="mma-result-state"><strong>${M.esc(x.matchup||x.selection||'MMA result')}</strong><p>${M.esc(x.market||'')} · ${M.esc(x.result||x.status||'Recorded grade')}</p></article>`).join('');
 }else{
  document.getElementById('results').textContent=issued||positions.length?'Issued picks are recorded. No official grades have been posted yet.':'No official positions have been issued for grading.';
 }
 document.getElementById('games').innerHTML=M.board(card,positions,{collapseRationale:true});
 document.getElementById('forecast-copy').textContent=M.status(t).detail;
 document.getElementById('issuance-meta').textContent=positions.length?'ISSUANCE '+t.issuance_id+' · MODEL '+t.active_model:'No current issuance';
}).catch(()=>{document.getElementById('results-meta').textContent='RESULTS DATA UNAVAILABLE';document.getElementById('results').textContent='The issued card or grading data could not be verified.';document.getElementById('games').textContent='';});
</script>
'''
def main():
 html=head('APEX — MMA Results','Issued APEX UFC / MMA picks and recorded grading results.','/mma/results')+'\n'+hero()+'\n'+navigation('RESULTS')
 html=html.replace('<body>','<body class="mma-four-box-page">').replace('</head>',DISPLAY_STYLE+'\n</head>')
 html+='''
 <div class="section-head"><div class="title">UFC / MMA RESULTS</div><div class="meta mono" id="results-meta">LOADING RESULTS</div></div>
 <div class="banner"><div class="cell"><div class="label">Issued Events</div><div class="val mono" id="issued">—</div></div><div class="cell"><div class="label">Current Picks</div><div class="val mono" id="current-picks">—</div></div><div class="cell"><div class="label">Graded Objects</div><div class="val mono" id="graded">—</div></div><div class="cell"><div class="label">Daily Grader</div><div class="val mono">7:00 AM ET</div></div></div>
 <main class="picks-page"><div class="mma-result-state" id="results" aria-live="polite">Reading recorded grades.</div>
 <div class="section-head"><div class="title" id="event-title">CURRENT EVENT</div><div class="meta mono" id="event-meta"></div></div>
 <div class="mma-compact-status mono"><span id="compact-issuance"></span><a href="/mma">Picks &amp; full rationale →</a></div>
 <div class="picks-board" id="games" aria-live="polite"></div>
 <details class="mma-audit-details"><summary>Issuance &amp; grading details</summary><p id="forecast-copy"></p><p class="mono" id="issuance-meta"></p><p>Issued selections, prices, probabilities and ratings are shown unchanged. A pending grade is not a win, loss or void.</p></details>
 </main>'''+DISPLAY_SCRIPT+SCRIPT+close()
 print('MMA_RESULTS_PATH='+str(write('mma/results/index.html',html)));return 0
if __name__=='__main__':raise SystemExit(main())
