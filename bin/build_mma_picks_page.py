#!/usr/bin/env python3
"""Build the APEX MMA picks/readiness page from the canonical public snapshot."""

from _mma_public import close, head, hero, navigation, write

SCRIPT = r"""
<script>
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt=v=>new Intl.DateTimeFormat("en-US",{timeZone:"America/New_York",month:"short",day:"numeric",hour:"numeric",minute:"2-digit",timeZoneName:"short"}).format(new Date(v));
const clock=v=>new Intl.DateTimeFormat("en-US",{timeZone:"America/New_York",hour:"numeric",minute:"2-digit",timeZoneName:"short"}).format(new Date(v));
const label=v=>String(v??"").replaceAll("_"," ");
const fightRow=(b,i)=>`<article class="game-module"><header class="game-header"><div class="game-num mono">F${String(i+1).padStart(2,"0")}</div><div class="game-meta"><h2 class="game-matchup">${esc(b.fighter_a)} vs ${esc(b.fighter_b)}</h2><p class="meta mono">${esc(label(b.weight_class))} · ${esc(b.segment)}</p></div><div class="game-time mono">${b.is_main_event?"MAIN EVENT":b.is_co_main_event?"CO-MAIN":"CARD"}</div></header></article>`;
fetch("/data/mma_today.json",{cache:"no-store"}).then(r=>{if(!r.ok)throw new Error(`HTTP ${r.status}`);return r.json()}).then(d=>{
 const e=d.event||{};
 document.getElementById("slate-meta").textContent=`${e.event_date||""} · ${d.fight_count||0} BOUTS`;
 document.getElementById("event-title").textContent=e.display_name||e.name||"NEXT UFC EVENT";
 document.getElementById("event-meta").textContent=`${e.venue||""} · ${e.city||""}${e.country?`, ${e.country}`:""}`;
 document.getElementById("prelims").textContent=clock(e.prelims_start_utc);
 document.getElementById("maincard").textContent=clock(e.main_card_start_utc);
 document.getElementById("t3time").textContent=clock(d.t3?.scheduled_utc);
 document.getElementById("t2time").textContent=clock(d.t2?.scheduled_utc);
 const status=d.picks_published?"FORECASTS ISSUED":"PREGAME DATA PENDING";
 const copy=d.picks_published?"Official APEX MMA/UFC forecasts are available below.":"Forecasts publish at T-2 only when the current scientific release and event inputs pass the production checks.";
 document.getElementById("forecast-status").textContent=status;
 document.getElementById("forecast-copy").textContent=copy;
 const positions=Array.isArray(d.positions)?d.positions:[];
 const positionHtml=positions.map((p,i)=>`<article class="game-module"><header class="game-header"><div class="game-num mono">P${String(i+1).padStart(2,"0")}</div><div class="game-meta"><h2 class="game-matchup">${esc(p.matchup||p.selection||"MMA POSITION")}</h2><p class="meta mono">${esc(p.market||"")}</p></div><div class="game-time mono">${esc(p.tier||"")}</div></header></article>`).join("");
 const card=(d.card||[]).map(fightRow).join("");
 document.getElementById("positions").innerHTML=positionHtml;
 document.getElementById("positions-wrap").hidden=!positions.length;
 document.getElementById("card").innerHTML=card||`<div class="meta mono">CURRENT CARD PENDING</div>`;
}).catch(e=>{document.getElementById("slate-meta").textContent="MMA EVENT DATA TEMPORARILY UNAVAILABLE";document.getElementById("card").innerHTML=`<div class="meta mono">${esc(e.message)}</div>`});
</script>
"""

def main() -> int:
    html = head("APEX — MMA Picks", "APEX MMA/UFC forecasts and next-event readiness.", "/mma")
    html += "\n" + hero() + "\n" + navigation("PICKS")
    html += """
  <div class="section-head picks-board-head">
    <div class="title">NEXT EVENT</div>
    <div class="meta mono" id="slate-meta">LOADING EVENT</div>
  </div>
  <main class="picks-page">
    <div class="section-head"><div class="title" id="event-title">UFC EVENT</div><div class="meta mono" id="event-meta"></div></div>
    <div class="banner">
      <div class="cell"><div class="label">Prelims</div><div class="val mono" id="prelims">—</div></div>
      <div class="cell"><div class="label">Main Card</div><div class="val mono" id="maincard">—</div></div>
      <div class="cell"><div class="label">T-3 Data</div><div class="val mono" id="t3time">—</div></div>
      <div class="cell"><div class="label">T-2 Forecast</div><div class="val mono" id="t2time">—</div></div>
    </div>
    <div class="section-head"><div class="title">FORECAST STATUS</div><div class="meta mono" id="forecast-status">PREGAME DATA PENDING</div></div>
    <div class="market-grid"><div class="market-panel"><div class="market-label">T-2 FORECAST</div><div class="pick-headline">Pregame data pending</div><div class="rationale-copy"><p id="forecast-copy">Forecasts publish at T-2 only when the current scientific release and event inputs pass the production checks.</p></div></div></div>
    <section id="positions-wrap" hidden><div class="section-head"><div class="title">OFFICIAL FORECASTS</div></div><div class="picks-board" id="positions"></div></section>
    <div class="section-head"><div class="title">FIGHT CARD</div><div class="meta mono">CURRENT UFC CARD</div></div>
    <div class="picks-board" id="card" aria-live="polite"></div>
  </main>""" + SCRIPT + close()
    path = write("mma/index.html", html)
    print(f"MMA_PICKS_PATH={path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
