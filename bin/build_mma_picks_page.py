#!/usr/bin/env python3
"""Build the release-gated APEX MMA picks/readiness page."""

from _mma_public import close, head, hero, navigation, write


SCRIPT = r"""
<script>
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const time=v=>new Intl.DateTimeFormat("en-US",{timeZone:"America/New_York",month:"short",day:"numeric",hour:"numeric",minute:"2-digit",timeZoneName:"short"}).format(new Date(v));
fetch("/data/mma_today.json",{cache:"no-store"}).then(r=>{if(!r.ok)throw new Error(`HTTP ${r.status}`);return r.json()}).then(d=>{
  document.getElementById("slate-meta").textContent=`${d.event.event_date} · ${d.fight_count} FIGHTS · ${d.release_state.replaceAll("_"," ")}`;
  const gate=d.picks_published?"":`<article class="game-module"><header class="game-header"><div class="game-num mono">GATE</div><div class="game-meta"><h2 class="game-matchup">No MMA picks issued</h2><p class="meta mono">${esc(d.release_state)}</p></div></header><div class="market-grid"><div class="market-panel"><div class="market-label">SCIENTIFIC STATUS</div><div class="pick-headline">Historical court not yet defensible</div><div class="rationale-copy"><p>APEX will not manufacture a fighter model from incomplete historical evidence. This preview remains readiness-only until a candidate survives chronological proper scoring, negative controls, and independent regeneration.</p></div></div></div></article>`;
  const card=d.card.map((b,i)=>`<article class="game-module"><header class="game-header"><div class="game-num mono">F${String(i+1).padStart(2,"0")}</div><div class="game-meta"><h2 class="game-matchup">${esc(b.fighter_a)} vs ${esc(b.fighter_b)}</h2><p class="meta mono">${esc(b.weight_class.replaceAll("_"," "))} · ${esc(b.segment)}</p></div><div class="game-time mono">${b.is_main_event?"MAIN EVENT":b.is_co_main_event?"CO-MAIN":"CARD"}</div></header></article>`).join("");
  document.getElementById("event-title").textContent=d.event.display_name;
  document.getElementById("event-meta").textContent=`${d.event.venue} · ${d.event.city}, ${d.event.country} · PRELIMS ${time(d.event.prelims_start_utc)}`;
  document.getElementById("card").innerHTML=gate+card;
}).catch(e=>{document.getElementById("slate-meta").textContent="MMA DATA UNAVAILABLE";document.getElementById("card").innerHTML=`<article class="game-module"><div class="meta mono">${esc(e.message)}</div></article>`});
</script>
"""


def main() -> int:
    html = head("APEX — MMA Picks", "APEX MMA release-gated forecasts and event readiness.", "/mma")
    html += "\n" + hero() + "\n" + navigation("PICKS")
    html += """
  <div class="section-head picks-board-head">
    <div class="title">MMA EVENT READINESS</div>
    <div class="meta mono" id="slate-meta">LOADING VERIFIED EVENT STATE</div>
  </div>
  <main class="picks-page">
    <div class="section-head"><div class="title" id="event-title">NEXT EVENT</div><div class="meta mono" id="event-meta"></div></div>
    <div class="picks-board" id="card" aria-live="polite"></div>
  </main>""" + SCRIPT + close()
    path = write("mma/index.html", html)
    print(f"MMA_PICKS_PATH={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
