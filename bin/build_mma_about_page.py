#!/usr/bin/env python3
"""Explain the actual published MMA card without overstating validation."""
from _mma_public import close,head,hero,write
from _mma_forecast_display import DISPLAY_SCRIPT,DISPLAY_STYLE
from apply_cloudflare_web_analytics import BEACON_BLOCK
from apply_shared_sport_selector import navigation
from apply_vercel_web_analytics import ANALYTICS_BLOCK
SCRIPT=r'''
<script>
const M=window.ApexMmaDisplay;
fetch('/data/mma_today.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error('HTTP '+r.status);return r.json()}).then(d=>{
 const positions=M.checkIssued(d),markets=[...new Set(positions.map(p=>M.label(p.market)))];
 const gate=d.science_gate;
 if(!gate||typeof gate.keep!=='string'||typeof gate.edge_cert!=='string'||typeof gate.policy!=='string'||typeof gate.eligible!=='boolean')throw new Error('Invalid science gate');
 document.getElementById('current-card').textContent=positions.length?`${d.event?.event_date||''} · ${positions.length} issued selections · ${markets.join(', ')}`:'No currently issued selections';
 document.getElementById('issuance-record').textContent=M.status(d).detail;
 document.getElementById('coverage').textContent=positions.length?`The current card contains ${markets.join(', ').toLowerCase()} selections from the sealed joint release.`:'No markets are issued for this event. Only exact Winner, Method and Time marginals from a sealed joint release can appear.';
 document.getElementById('science-state').textContent=`KEEP=${gate.keep} · EDGE_CERT=${gate.edge_cert} · CI_FULLY_BELOW_0=${gate.ci_fully_below_0?'YES':'NO'} · POLICY=${gate.policy}`;
}).catch(()=>{
 document.getElementById('current-card').textContent='Current issuance details unavailable';
 document.getElementById('coverage').textContent='No public market can be verified.';
 document.getElementById('issuance-record').textContent='No sealed issuance can be verified.';
 document.getElementById('science-state').textContent='Science-gate state unavailable; production remains fail-closed.';
});
</script>
'''
def main():
 html=head('APEX — About MMA','How to read the issued APEX UFC / MMA card, probability ratings and results.','/mma/about')+'\n'+hero()+'\n'+navigation('mma','about',True)
 html=html.replace('<body>','<body class="mma-four-box-page">').replace('</head>',DISPLAY_STYLE+'\n'+BEACON_BLOCK+'\n'+ANALYTICS_BLOCK+'\n</head>')
 html+='''
 <main class="about-page"><div class="about-container">
 <header class="about-section about-intro"><h1 class="about-section-title">UFC / MMA Forecasts</h1><p class="about-lede" id="current-card">Reading the current published card.</p><p class="about-copy"><a href="/mma">View all picks and rationale →</a></p></header>
 <section class="about-section about-module"><h2 class="about-section-title">How an issued selection appears</h2><p class="about-copy">An issued market panel names the selection, its captured FanDuel American odds, the estimated probability and the probability rating saved at issuance. The full as-issued rationale appears in the same fight panel.</p></section>
 <section class="about-section about-module"><h2 class="about-section-title">Current market coverage</h2><p class="about-copy" id="coverage">Reading issued markets.</p></section>
 <section class="about-section about-module"><h2 class="about-section-title">Science gate</h2><p class="about-copy mono" id="science-state">Reading the sealed science-gate state.</p><p class="about-copy">MMA production is fail-closed. A joint P(WINNER, METHOD, TIME) release can publish only after it beats matched-time FanDuel on the required proper scores, its event-level confidence interval is fully below zero, and the exact release is authorized for production. Otherwise the card remains status-only.</p></section>
 <section class="about-section about-module"><h2 class="about-section-title">Probability is not betting value</h2><p class="about-copy">Weak, Moderate, Strong and Elite are probability tiers saved only for an issued position; they are not certifications of profitability. A high win probability does not establish value at a particular price. Captured prices are historical observations, not live offers.</p></section>
 <section class="about-section about-module"><h2 class="about-section-title">Issuance integrity</h2><p class="about-copy" id="issuance-record">Reading the current issuance state.</p><p class="about-copy">The website reads the saved issuance. Display changes do not recalculate probabilities, replace selections, or rewrite the issue time. Separately marked research is never an official issuance.</p></section>
 <section class="about-section about-module"><h2 class="about-section-title">Rationale and evidence</h2><p class="about-copy">The rationale is retained as issued. Historical measurements, model features and missing-history defaults are different kinds of information: a default is not an observed performance statistic, and a missing UFC history does not mean a fighter has no professional experience.</p></section>
 <section class="about-section about-module"><h2 class="about-section-title">Results and event timing</h2><p class="about-copy">The workflow is event-based: T-3 prepares facts three hours before the first scheduled bout, T-2 runs two hours before that bout, and the grader runs at 7:00 AM Eastern the next morning. Off-event days do not run a grader. A recovery issuance retains its actual timestamp. The Results page distinguishes recorded picks from posted grades and does not count pending outcomes as wins or losses.</p></section>
 </div></main>'''+DISPLAY_SCRIPT+SCRIPT+close()
 print('MMA_ABOUT_PATH='+str(write('mma/about/index.html',html)));return 0
if __name__=='__main__':raise SystemExit(main())
