#!/usr/bin/env python3
"""MMA season results, tier performance, archive and ledger in the MLB/NCAA layout."""
from _mma_public import close, head, hero, navigation, write
from _mma_forecast_display import DISPLAY_SCRIPT
from _mma_results_view import LEDGER_SCRIPT
STYLE='''
<style id="mma-results-style">
.mma-results-page [hidden]{display:none!important}
.mma-results-page .results-scroll{width:100%;max-width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch}
.mma-results-page table.results{width:100%;border-collapse:collapse}
.mma-results-page .position-ledger{min-width:920px}
.mma-results-page .position-ledger td{font-size:12px;vertical-align:top;line-height:1.65}
.mma-results-page .position-ledger th{white-space:nowrap}
.mma-results-page .position-ledger .matchup{min-width:170px;max-width:220px;white-space:normal}
.mma-results-page .result-mark{font-size:10px;letter-spacing:.08em;white-space:nowrap;border:1px solid #555;padding:5px 7px;display:inline-block}
.mma-results-page .result-mark--PENDING{color:#aaa;border-color:#333}
.mma-results-page .result-mark--W{background:#eee;color:#111;border-color:#eee}
.mma-results-page .results-note{color:#aaa;font-size:12px;line-height:1.7;margin:14px 0 22px}
.mma-results-page .results-error{border:1px solid #666;padding:18px;margin:20px 0;line-height:1.7}
.mma-results-page .results-tier-single{max-width:600px;width:100%}
.mma-results-page .event-summary{padding-bottom:20px}
.mma-results-page .results-details{border-top:1px solid #333;margin-top:28px;padding:16px 0;color:#aaa;font-size:12px;line-height:1.7}
.mma-results-page .results-details summary{cursor:pointer;text-transform:uppercase;letter-spacing:.1em;font-size:11px}
.mma-results-page .results-details p{overflow-wrap:anywhere}
@media(max-width:700px){.mma-results-page .banner .val{font-size:23px}.mma-results-page .section-head{gap:10px;flex-wrap:wrap}.mma-results-page .meta{overflow-wrap:anywhere}.mma-results-page .archive-table{min-width:560px}.mma-results-page .tier-grid{display:block}.mma-results-page .tier-col{margin-bottom:20px}}

@media(max-width:700px){
.mma-results-page .position-ledger,.mma-results-page .archive-table{min-width:0}
.mma-results-page .position-ledger .matchup{min-width:0;max-width:none}
.mma-results-page .position-ledger td[data-label]::before{content:attr(data-label) " · ";display:inline;font-size:10px;letter-spacing:.07em;text-transform:uppercase;color:#999}
.mma-results-page .position-ledger td:first-child::before{display:none}
.mma-results-page #tier-performance table.results,.mma-results-page #combined-tiers table.results{display:table;table-layout:auto;font-size:11px}
.mma-results-page #tier-performance thead,.mma-results-page #combined-tiers thead{display:table-header-group}
.mma-results-page #tier-performance tbody,.mma-results-page #combined-tiers tbody{display:table-row-group}
.mma-results-page #tier-performance tr,.mma-results-page #combined-tiers tr{display:table-row;margin:0;padding:0;border:0}
.mma-results-page #tier-performance td,.mma-results-page #combined-tiers td{display:table-cell;width:auto;padding:10px 5px;font-size:11px;white-space:nowrap;border-bottom:1px solid #222}
.mma-results-page #tier-performance th,.mma-results-page #combined-tiers th{padding:10px 5px;font-size:9px;letter-spacing:.06em}
.mma-results-page #tier-performance td::before,.mma-results-page #combined-tiers td::before{display:none;content:none}
}
</style>
'''
SCRIPT=r'''
<script>
const M=window.ApexMmaDisplay,R=window.ApexMmaResults;
const section=(title,meta='')=>`<div class="section-head"><div class="title">${M.esc(title)}</div><div class="meta mono">${M.esc(meta)}</div></div>`;
const cell=(label,value,id='')=>`<div class="cell"><div class="label">${M.esc(label)}</div><div class="val mono"${id?' id="'+id+'"':''}>${M.esc(value)}</div></div>`;
function tierTable(rows,market){return `<table class="results" data-tier-market="${M.esc(market)}"><thead><tr><th>Tier</th><th>Record</th><th>Win Rate</th><th>Pending</th></tr></thead><tbody>${R.tiers.map(t=>{
 const s=R.record(rows.filter(p=>p.tier===t));return `<tr data-apex-tier="${t}" data-apex-tier-market="${M.esc(market)}"><td class="mono">${t[0]+t.slice(1).toLowerCase()}</td><td class="mono">${R.recordText(s)}</td><td class="mono muted">${R.winRate(s)}</td><td class="mono muted">${s.PENDING}</td></tr>`;
 }).join('')}</tbody></table>`;}
function positionTable(event){return `<div class="results-scroll" role="region" aria-label="${M.esc(event.date)} position ledger" tabindex="0"><table class="results position-ledger"><thead><tr><th>Fight</th><th>Matchup</th><th>Market</th><th>Issued Pick</th><th>FanDuel</th><th>APEX</th><th>Tier</th><th>Result</th></tr></thead><tbody>${event.positions.map(p=>{
 const pick=p.display_selection||(p.selection+(p.line===null||p.line===undefined?'':' '+p.line));
 return `<tr data-position-bout="${M.esc(p.bout_id)}" data-issuance="${M.esc(p.issuance_id)}" data-result="${p.result}"><td class="mono" data-label="Fight">F${String(p.order).padStart(2,'0')}</td><td class="matchup" data-label="Matchup">${M.esc(p.matchup)}</td><td class="mono" data-label="Market">${M.esc(R.marketLabel(p.market))}</td><td data-field="pick" data-label="Issued pick">${M.esc(pick)}</td><td class="mono" data-field="price" data-label="FanDuel">${M.esc(M.odds(p.price))}</td><td class="mono" data-field="probability" data-label="APEX probability">${(p.probability*100).toFixed(1)}%</td><td class="mono" data-field="rating" data-label="Tier">${M.esc(p.tier)}</td><td data-label="Result"><span class="result-mark result-mark--${p.result}">${p.result}</span></td></tr>`;
 }).join('')}</tbody></table></div>`;}
Promise.all(['/data/mma_today.json','/data/mma_results_summary.json','/data/mma_results_archive.json'].map(url=>fetch(url,{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error('HTTP '+r.status);return r.json()}))).then(([today,summary,archive])=>{
 const data=R.ledger(today,summary,archive,M.checkIssued),all=R.record(data.positions),markets=[...new Set(data.positions.map(p=>p.market))].sort();
 const primary=markets[0]||'WINNER',primaryRecord=R.record(data.positions.filter(p=>p.market===primary));
 document.getElementById('results-meta').textContent=`${data.positions.length} POSITIONS TRACKED · ${all.PENDING} PENDING`;
 document.getElementById('season-banner').innerHTML=cell('Overall',R.recordText(all),'season-record')+cell('Win Rate',R.winRate(all),'season-win-rate')+cell(R.marketLabel(primary),R.recordText(primaryRecord),'primary-record')+cell('Pending',all.PENDING,'pending-count');
 document.getElementById('season-banner').setAttribute('data-apex-season-record',R.recordText(all));
 document.getElementById('season-banner').setAttribute('data-apex-season-win-rate',R.winRate(all));
 document.getElementById('grade-note').textContent=all.PENDING===data.positions.length&&all.PENDING?'Issued selections are recorded below. Official grades have not been posted yet.':`${all.W+all.L+all.P+all.VOID} settled · ${all.PENDING} pending. Win rate uses wins and losses only.`;
 document.getElementById('coverage-warning').textContent=data.warnings.join(' ');document.getElementById('coverage-warning').hidden=!data.warnings.length;
 document.getElementById('tier-period').textContent=data.events.length?`${R.dateLabel(data.events[data.events.length-1].date)} — ${R.dateLabel(data.events[0].date)}`:'NO ISSUED EVENTS';
 const groupHtml=(markets.length?markets:['WINNER']).map(m=>`<div class="tier-col"><div class="tier-sub">${M.esc(R.marketLabel(m))} BY CONFIDENCE TIER</div>${tierTable(data.positions.filter(p=>p.market===m),m)}</div>`).join('');
 document.getElementById('tier-performance').className=markets.length>1?'tier-grid':'results-tier-single';document.getElementById('tier-performance').innerHTML=groupHtml;
 document.getElementById('combined-tiers').innerHTML=markets.length>1?'<div class="tier-sub">COMBINED MMA BY CONFIDENCE TIER</div><div class="tier-single">'+tierTable(data.positions,'COMBINED')+'</div>':'';
 const days=[...new Set(data.events.map(e=>e.date))];
 document.getElementById('daily-archive').innerHTML=days.length?days.map(day=>{
  const entries=data.events.filter(e=>e.date===day),s=R.record(entries.flatMap(e=>e.positions));
  return `<tr><td class="mono"><a href="#event-${day}">${R.dateLabel(day)}</a></td><td class="mono">${R.recordText(s)}</td><td class="mono muted">${R.winRate(s)}</td><td class="muted">${M.esc(entries.map(e=>e.name).join(' · '))}${s.PENDING?' · '+s.PENDING+' pending':''}</td></tr>`;
 }).join(''):'<tr><td colspan="4" class="muted">No issued events in the results archive.</td></tr>';
 const latest=data.events[0];
 document.getElementById('latest-title').textContent=latest&&latest.positions.some(p=>p.result!=='PENDING')?'LATEST EVENT RESULTS':'LATEST EVENT';
 document.getElementById('latest-date').textContent=latest?R.dateLabel(latest.date).toUpperCase():'';
 if(latest){const s=R.record(latest.positions);document.getElementById('latest-summary').innerHTML=cell('Event Record',R.recordText(s))+cell('Win Rate',R.winRate(s))+cell('Positions',latest.positions.length)+cell('Pending',s.PENDING);}
 document.getElementById('event-ledgers').innerHTML=data.events.map((event,i)=>{
  const title=`${R.dateLabel(event.date)} · Position Ledger`,meta=event.name;
  return `<section class="event-summary" id="event-${event.date}" data-event-date="${event.date}">${section(title,meta)}${positionTable(event)}${i===0?'<p class="results-note"><a href="/mma">View picks and full rationale →</a></p>':''}</section>`;
 }).join('');
 document.getElementById('asof').textContent='SOURCE UPDATE '+M.stamp(summary.generated_at_utc)+' · '+M.compactStatus(today);
 document.getElementById('results-root').hidden=false;
}).catch(()=>{document.getElementById('results-meta').textContent='RESULTS DATA UNAVAILABLE';document.getElementById('results-root').hidden=true;const error=document.getElementById('results-error');error.hidden=false;error.textContent='The issued selections or grading ledger could not be verified. No record is being shown from incomplete data.';});
</script>
'''
def main():
    html=head('APEX — MMA Results','APEX UFC / MMA season record, as-issued tier performance, daily archive and position ledger.','/mma/results')+'\n'+hero()+'\n'+navigation('RESULTS')
    html=html.replace('<body>','<body class="mma-results-page">').replace('</head>',STYLE+'\n</head>')
    html+='''
<div class="section-head"><div class="title">SEASON RECORD</div><div class="meta mono" id="results-meta">LOADING RESULTS</div></div>
<div id="results-error" class="results-error" hidden role="alert"></div>
<main id="results-root" hidden>
<div class="banner" id="season-banner"></div>
<p class="results-note" id="grade-note"></p><p class="results-error" id="coverage-warning" hidden></p>
<div class="section-head"><div class="title">AS-ISSUED TIER PERFORMANCE</div><div class="meta mono" id="tier-period"></div></div>
<div id="tier-performance"></div><div id="combined-tiers"></div>
<div class="section-head"><div class="title">DAILY ARCHIVE</div></div>
<div class="results-scroll" role="region" aria-label="Daily results archive" tabindex="0"><table class="results archive-table"><thead><tr><th>Date</th><th>Record</th><th>Win Rate</th><th>Summary</th></tr></thead><tbody id="daily-archive"></tbody></table></div>
<div class="section-head"><div class="title" id="latest-title">LATEST EVENT</div><div class="meta mono" id="latest-date"></div></div>
<div class="banner" id="latest-summary"></div><div id="event-ledgers"></div>
<details class="results-details"><summary>Grading &amp; issuance details</summary><p id="asof"></p><p>Only recorded grades are counted. Pending results are not wins, losses, pushes or voids. Win rate is wins divided by wins plus losses. Prices, probabilities and ratings are preserved as issued; ratings are not a proven betting advantage.</p></details>
</main>'''+DISPLAY_SCRIPT+LEDGER_SCRIPT+SCRIPT+close()
    print('MMA_RESULTS_PATH='+str(write('mma/results/index.html',html)))
    return 0
if __name__=='__main__':raise SystemExit(main())
