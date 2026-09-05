#!/usr/bin/env python3
"""Explain the actual published MMA card without overstating validation."""
from _mma_public import close,head,hero,navigation,write
from _mma_forecast_display import DISPLAY_SCRIPT,DISPLAY_STYLE
SCRIPT=r'''
<script>
const M=window.ApexMmaDisplay;
fetch('/data/mma_today.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error('HTTP '+r.status);return r.json()}).then(d=>{
 const positions=M.checkIssued(d),markets=[...new Set(positions.map(p=>M.label(p.market)))];
 document.getElementById('current-card').textContent=positions.length?`${d.event?.event_date||''} · ${positions.length} issued selections · ${markets.join(', ')}`:'No currently issued selections';
 document.getElementById('active-model').textContent=d.active_model||'No published model';
 document.getElementById('model-time').textContent=M.compactStatus(d);
 document.getElementById('issuance-record').textContent=M.status(d).detail;
 document.getElementById('coverage').textContent=positions.length?`The current card contains ${markets.join(', ').toLowerCase()} selections. Method-of-victory, double-chance and total-rounds picks are not part of this issuance unless they appear explicitly as separate issued markets.`:'The current issuance has no published markets.';
}).catch(()=>{document.getElementById('current-card').textContent='Current issuance details unavailable';});
</script>
'''
def main():
 html=head('APEX — About MMA','How to read the issued APEX UFC / MMA card, probability ratings and results.','/mma/about')+'\n'+hero()+'\n'+navigation('ABOUT')
 html=html.replace('<body>','<body class="mma-four-box-page">').replace('</head>',DISPLAY_STYLE+'\n</head>')
 html+='''
 <main class="about-page"><div class="about-container">
 <header class="about-section about-intro"><h1 class="about-section-title">UFC / MMA Forecasts</h1><p class="about-lede" id="current-card">Reading the current published card.</p><p class="about-copy"><a href="/mma">View all picks and rationale →</a></p></header>
 <section class="about-section about-module"><h2 class="about-section-title">Four boxes for each fight</h2><p class="about-copy">The pick box names the issued selection. FanDuel Price shows the captured American odds. APEX Probability is the model's estimated chance of that selection winning. APEX Rating preserves the probability tier assigned at issuance. Each fight's detailed rationale appears directly below those boxes.</p></section>
 <section class="about-section about-module"><h2 class="about-section-title">Current market coverage</h2><p class="about-copy" id="coverage">Reading issued markets.</p></section>
 <section class="about-section about-module"><h2 class="about-section-title">Probability is not betting value</h2><p class="about-copy">Weak, Moderate, Strong and Elite are issued probability tiers, not certifications of profitability. A high win probability does not establish value at a particular price. The current Winner model has not demonstrated a statistically proven advantage over the matched FanDuel benchmark. Captured prices are historical observations, not live offers.</p></section>
 <section class="about-section about-module"><h2 class="about-section-title">Model and issuance</h2><p class="about-copy mono" id="active-model"></p><p class="about-copy mono" id="model-time"></p><p class="about-copy" id="issuance-record"></p><p class="about-copy">The website reads the saved issuance. Display changes do not recalculate probabilities, replace selections, or rewrite the issue time. Any separately marked research preview is not an official issuance.</p></section>
 <section class="about-section about-module"><h2 class="about-section-title">Rationale and evidence</h2><p class="about-copy">The rationale is retained as issued. Historical measurements, model features and missing-history defaults are different kinds of information: a default is not an observed performance statistic, and a missing UFC history does not mean a fighter has no professional experience.</p></section>
 <section class="about-section about-module"><h2 class="about-section-title">Results and timing</h2><p class="about-copy">The scheduled workflow is T-3 data preparation, T-2 issuance and a 7:00 AM Eastern daily grader. A recovery issuance retains its actual timestamp. The Results page distinguishes recorded picks from posted grades and does not count pending outcomes as wins or losses.</p></section>
 </div></main>'''+DISPLAY_SCRIPT+SCRIPT+close()
 print('MMA_ABOUT_PATH='+str(write('mma/about/index.html',html)));return 0
if __name__=='__main__':raise SystemExit(main())
