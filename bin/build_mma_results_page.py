#!/usr/bin/env python3
"""Build the APEX MMA results page with a finished no-history state and next event."""

from _mma_public import close, head, hero, navigation, write
from _mma_forecast_display import DISPLAY_SCRIPT

SCRIPT = r"""
<script>
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const clock=v=>new Intl.DateTimeFormat("en-US",{timeZone:"America/New_York",hour:"numeric",minute:"2-digit",timeZoneName:"short"}).format(new Date(v));
const niceDate=v=>{if(!v)return "—";const [y,m,d]=String(v).split("-").map(Number);return new Intl.DateTimeFormat("en-US",{timeZone:"UTC",month:"long",day:"2-digit",year:"numeric"}).format(new Date(Date.UTC(y,m-1,d)))};
const label=v=>String(v??"").replaceAll("_"," ");
Promise.all([
 fetch("/data/mma_results_summary.json",{cache:"no-store"}).then(r=>{if(!r.ok)throw new Error(`results HTTP ${r.status}`);return r.json()}),
 fetch("/data/mma_today.json",{cache:"no-store"}).then(r=>{if(!r.ok)throw new Error(`event HTTP ${r.status}`);return r.json()})
]).then(([r,t])=>{
 const issued=Number(r.issued_event_count||0), graded=Number(r.graded_scientific_object_count||0), e=t.event||{};
 document.getElementById("results-meta").textContent=`${issued} ISSUED EVENTS · ${graded} GRADED OBJECTS`;
 document.getElementById("issued").textContent=issued;
 document.getElementById("graded").textContent=graded;
 document.getElementById("grader").textContent="7:00 AM ET";
 document.getElementById("nextdate").textContent=niceDate(e.event_date);
 const forecast=window.ApexMmaDisplay.status(t);
 document.getElementById("current-forecast-status").textContent=forecast.headline;
 document.getElementById("current-forecast-detail").textContent=forecast.detail;
 const rows=Array.isArray(r.latest_event_results)?r.latest_event_results:[];
 if(issued && rows.length){
   document.getElementById("results").innerHTML=rows.map((x,i)=>`<article class="game-module"><header class="game-header"><div class="game-num mono">R${String(i+1).padStart(2,"0")}</div><div class="game-meta"><h2 class="game-matchup">${esc(x.matchup||x.selection||"MMA RESULT")}</h2><p class="meta mono">${esc(x.market||"")} · ${esc(x.result||x.status||"")}</p></div></header></article>`).join("");
 } else {
   document.getElementById("results").innerHTML=`<article class="game-module"><header class="game-header"><div class="game-num mono">—</div><div class="game-meta"><h2 class="game-matchup">No issued MMA/UFC forecasts to grade</h2><p class="meta mono">NO PICKS WERE ISSUED; A RUNNING GRADER DOES NOT CREATE A RESULTS RECORD</p></div></header></article>`;
 }
 document.getElementById("next-title").textContent=e.display_name||e.name||"NEXT UFC EVENT";
 document.getElementById("next-meta").textContent=`${niceDate(e.event_date)} · ${e.venue||""} · ${e.city||""}${e.country?`, ${e.country}`:""}`;
 document.getElementById("prelims").textContent=clock(e.prelims_start_utc);
 document.getElementById("maincard").textContent=clock(e.main_card_start_utc);
 document.getElementById("t3time").textContent=clock(t.t3?.scheduled_utc);
 document.getElementById("t2time").textContent=clock(t.t2?.scheduled_utc);
 document.getElementById("next-card").innerHTML=(t.card||[]).map((b,i)=>`<article class="game-module"><header class="game-header"><div class="game-num mono">F${String(i+1).padStart(2,"0")}</div><div class="game-meta"><h2 class="game-matchup">${esc(b.fighter_a)} vs ${esc(b.fighter_b)}</h2><p class="meta mono">${esc(label(b.weight_class))} · ${esc(b.segment)}</p></div><div class="game-time mono">${b.is_main_event?"MAIN EVENT":b.is_co_main_event?"CO-MAIN":"CARD"}</div></header></article>`).join("");
}).catch(e=>{document.getElementById("results-meta").textContent="MMA RESULTS TEMPORARILY UNAVAILABLE";document.getElementById("results").textContent=e.message});
</script>
"""

def main() -> int:
    html = head("APEX — MMA Results", "APEX MMA/UFC production results and next-event schedule.", "/mma/results")
    html += "\n" + hero() + "\n" + navigation("RESULTS")
    html += """
  <div class="section-head"><div class="title">MMA / UFC RESULTS</div><div class="meta mono" id="results-meta">LOADING RESULTS</div></div>
  <div class="banner">
    <div class="cell"><div class="label">Issued Events</div><div class="val mono" id="issued">0</div></div>
    <div class="cell"><div class="label">Graded Objects</div><div class="val mono" id="graded">0</div></div>
    <div class="cell"><div class="label">Grader</div><div class="val mono" id="grader">7:00 AM ET</div></div>
    <div class="cell"><div class="label">Next Event</div><div class="val mono" id="nextdate">—</div></div>
  </div>
  <main class="picks-page">
    <div class="section-head"><div class="title">CURRENT EVENT FORECAST</div><a class="meta mono" href="/mma">PICKS &amp; DETAILED RATIONALE →</a></div>
    <div class="market-grid market-grid--single"><section class="market-panel"><div class="pick-headline" id="current-forecast-status">Checking issuance</div><div class="rationale-copy"><p id="current-forecast-detail">Reading the current forecast record.</p></div></section></div>
    <div class="section-head"><div class="title">PRODUCTION HISTORY</div></div>
    <div class="picks-board" id="results" aria-live="polite"></div>
    <div class="section-head"><div class="title">NEXT EVENT</div><div class="meta mono" id="next-meta"></div></div>
    <div class="section-head"><div class="title" id="next-title">UFC EVENT</div></div>
    <div class="banner">
      <div class="cell"><div class="label">Prelims</div><div class="val mono" id="prelims">—</div></div>
      <div class="cell"><div class="label">Main Card</div><div class="val mono" id="maincard">—</div></div>
      <div class="cell"><div class="label">T-3 Data</div><div class="val mono" id="t3time">—</div></div>
      <div class="cell"><div class="label">T-2 Forecast</div><div class="val mono" id="t2time">—</div></div>
    </div>
    <div class="picks-board" id="next-card"></div>
  </main>""" + DISPLAY_SCRIPT + SCRIPT + close()
    path = write("mma/results/index.html", html)
    print(f"MMA_RESULTS_PATH={path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
