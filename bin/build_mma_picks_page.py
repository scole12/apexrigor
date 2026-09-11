#!/usr/bin/env python3
"""Render the official MMA card with the shared NFL/NCAAF picks chrome."""
import json

from _mma_public import ROOT, close, head, hero, write
from _mma_forecast_contract import validated_card, validated_positions
from apply_cloudflare_web_analytics import BEACON_BLOCK
from apply_vercel_web_analytics import ANALYTICS_BLOCK


NAVIGATION = '''  <div class="apex-nav-stack">
  <nav class="sport-nav" aria-label="Sport selector">
    <a href="/">MLB</a>
    <a href="/ncaaf">NCAA FOOTBALL</a>
    <a href="/mma" class="active" aria-current="true">MMA / UFC</a>
    <a href="/nfl">NFL</a>
  </nav>
  <nav class="section-nav" aria-label="MMA sections">
    <a href="/mma" class="active" aria-current="true">PICKS</a>
    <a href="/mma/results">RESULTS</a>
    <a href="/mma/about">ABOUT</a>
  </nav>
  </div>'''

SCRIPT = r'''
<script>
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
const norm=v=>String(v??"").normalize("NFKD").replace(/[\u0300-\u036f]/g,"").replace(/[^a-z0-9]/gi,"").toLowerCase();
const pair=b=>b.fighter_a&&b.fighter_b?[norm(b.fighter_a),norm(b.fighter_b)].sort().join("|"):"";
const matchup=b=>b.fighter_a&&b.fighter_b?b.fighter_a+" vs "+b.fighter_b:b.matchup;
const paragraphs=v=>String(v||"").split(/\n\s*\n/).filter(x=>x.trim());
const allowedMarkets=new Set(["WINNER","METHOD","TIME"]);
const dateLabel=value=>{
 const [y,m,d]=String(value).split("-").map(Number);
 return new Intl.DateTimeFormat("en-US",{weekday:"long",year:"numeric",month:"long",day:"numeric",timeZone:"UTC"}).format(new Date(Date.UTC(y,m-1,d))).toUpperCase();
};
function clock(value){
 const time=new Date(value);
 return value&&Number.isFinite(time.getTime())?new Intl.DateTimeFormat("en-US",{timeZone:"America/New_York",hour:"numeric",minute:"2-digit"}).format(time)+" ET":"TIME TBA";
}
function boutTime(b,e){
 if(b.scheduled_start_utc||b.scheduled_start_et)return clock(b.scheduled_start_utc||b.scheduled_start_et);
 const segment=String(b.segment||"").toUpperCase();
 if(segment==="MAIN"||segment==="MAIN_CARD")return clock(e.main_card_start_utc||e.main_card_start_et)+" · MAIN CARD";
 if(segment==="PRELIMS"||segment==="PRELIM"||segment==="PRELIMINARY")return clock(e.prelims_start_utc||e.prelims_start_et)+" · PRELIMS";
 if(segment==="EARLY_PRELIMS")return clock(e.early_prelims_start_utc||e.early_prelims_start_et)+" · EARLY PRELIMS";
 return "TIME TBA";
}
function issuedPositions(d){
 if(!Array.isArray(d.positions))throw new Error("Missing positions array");
 const rows=d.positions;
 if(!rows.length){
  if(d.picks_published===true)throw new Error("Empty published issuance");
  if(d.active_model!=null||d.active_model_sha256!=null)throw new Error("Unissued payload exposes a model identity");
  return [];
 }
 if(d.picks_published!==true||d.release_state!=="SEALED_RELEASE_AVAILABLE"||!d.issuance_id||!["SEALED","ALREADY_ISSUED"].includes(d.issuance_status)||!d.active_model||!/^[0-9a-f]{64}$/.test(d.active_model_sha256||""))throw new Error("Unsealed issuance");
 const seen=new Set();
 for(const p of rows){
  if(!p||!["bout_id","matchup","fighter_a","fighter_b","market","selection","rationale"].every(k=>typeof p[k]==="string"&&p[k].trim())||!pair(p)||!paragraphs(p.rationale).length||p.sportsbook!=="FanDuel"||!["WEAK","MODERATE","STRONG","ELITE"].includes(p.tier)||!Number.isFinite(p.probability)||p.probability<0||p.probability>1||!Number.isFinite(p.price)||Math.abs(p.price)<100||(p.line!=null&&!Number.isFinite(p.line)))throw new Error("Invalid issued position");
  if(!allowedMarkets.has(p.market))throw new Error("Unsupported MMA public market");
  if((p.trace?.issuance_id||p.issuance_id)!==d.issuance_id||(p.trace?.model_sha256||p.model_sha256)!==d.active_model_sha256)throw new Error("Foreign issuance identity");
  const key=JSON.stringify([p.bout_id,p.market,p.selection,p.line??null]);
  if(seen.has(key))throw new Error("Duplicate issued position");
  seen.add(key);
 }
 return rows;
}
function issuedPanel(p){
 const headline=p.display_selection||p.selection;
 return '<section class="market-panel" data-market="'+esc(p.market)+'" data-position-state="SEALED" data-position-bout="'+esc(p.bout_id)+'">'
  +'<div class="market-label">'+esc(p.market)+'</div>'
  +'<div class="market-panel-head"><span class="pick-headline">'+esc(headline)+'</span>'
  +'<span class="rating-label">APEX WIN PROBABILITY RATING</span>'
  +'<span class="tier-badge tier-badge--'+esc(p.tier.toLowerCase())+'">'+esc(p.tier)+'</span></div>'
  +'<div class="meta mono">APEX WIN PROBABILITY: '+(p.probability*100).toFixed(1)+'% · Sportsbook: FanDuel · '+(p.price>0?'+':'')+esc(p.price)+'</div>'
  +'<div class="rationale-copy">'+paragraphs(p.rationale).map(text=>'<p>'+esc(text)+'</p>').join("")+'</div></section>';
}
fetch("/data/mma_today.json",{cache:"no-store"}).then(r=>{if(!r.ok)throw new Error("HTTP "+r.status);return r.json()}).then(d=>{
 if(!d.event?.event_date||!Array.isArray(d.card)||d.card.some(b=>!b||!matchup(b)))throw new Error("Invalid official card");
 const e=d.event,positions=issuedPositions(d);
 const forecast=d.forecast;
 if(!forecast||typeof forecast.code!=="string"||typeof forecast.headline!=="string"||typeof forecast.detail!=="string")throw new Error("Invalid forecast status");
 const displayOrders=d.card.map(b=>b.official_display_order);
 if(displayOrders.some(order=>!Number.isInteger(order))||[...displayOrders].sort((a,b)=>a-b).some((order,index)=>order!==index+1))throw new Error("Invalid official display order");
 const cardPairs=d.card.map(pair);
 const cardFighters=d.card.flatMap(b=>[norm(b.fighter_a),norm(b.fighter_b)]);
 if(cardPairs.some(value=>!value)||new Set(cardPairs).size!==cardPairs.length||new Set(cardFighters).size!==cardFighters.length)throw new Error("Duplicate official bout or fighter");
 const card=d.card.map((b,i)=>({b,order:Number.isFinite(b.official_display_order)?b.official_display_order:i+1,positions:[]})).sort((a,b)=>a.order-b.order);
 for(const p of positions){
  const matches=card.filter(g=>{
   const id=g.b.bout_id||g.b.apex_mma_bout_id;
   return id?id===p.bout_id:Boolean(pair(p)&&pair(g.b)===pair(p))||norm(matchup(g.b))===norm(p.matchup);
  });
  if(matches.length!==1)throw new Error("Position does not match one official bout");
  matches[0].positions.push(p);
 }
 const meta=dateLabel(e.event_date)+" · "+card.length+" SCHEDULED BOUTS · "+positions.length+" POSITIONS"
  +(positions.length?" · MODEL "+d.active_model:" · UNISSUED · "+forecast.code.replaceAll("_"," "));
 const html=card.map(({b,positions:issued},i)=>{
  let panels=issued.slice().sort((a,b)=>(a.market==="WINNER"?0:1)-(b.market==="WINNER"?0:1)).map(issuedPanel).join("");
  if(!issued.length){
   const badge=forecast.code==="AWAITING_T2"?"SCHEDULED":"FAIL CLOSED";
   panels='<section class="market-panel" data-position-state="UNISSUED" data-forecast-code="'+esc(forecast.code)+'"><div class="market-label">STATUS</div><div class="market-panel-head"><span class="pick-headline">UNISSUED — '+esc(forecast.headline.toUpperCase())+'</span><span class="tier-badge tier-badge--moderate">'+badge+'</span></div><div class="rationale-copy"><p>'+esc(forecast.detail)+'</p></div></section>';
  }
  const eventContext=[e.display_name||e.name,e.venue].filter(Boolean).join(" / ");
  const context=[String(b.weight_class||"").replaceAll("_"," "),eventContext].filter(Boolean).join(" · ");
  return '<article class="game-module" data-game="'+esc(b.bout_id||b.apex_mma_bout_id||matchup(b))+'" data-game-state="'+(issued.length?'ISSUED':'UNISSUED')+'">'
   +'<header class="game-header"><div class="game-num mono">F'+String(i+1).padStart(2,"0")+'</div><div class="game-meta">'
   +'<h2 class="game-matchup">'+esc(matchup(b))+'</h2><p class="game-pitchers mono">'+esc(context)+'</p></div><div class="game-time mono">'+esc(boutTime(b,e))+'</div></header>'
   +'<div class="market-grid'+(issued.length===1?' market-grid--single':'')+'">'+panels+'</div></article>';
 }).join("");
 document.getElementById("slate-meta").textContent=meta;
 const shell=document.querySelector(".shell");
 shell.setAttribute("data-slate-date",e.event_date);
 shell.setAttribute("data-public-issuance",positions.length?"true":"false");
 shell.setAttribute("data-picks-state",positions.length?"issued":"quiet");
 document.getElementById("games").innerHTML=html||'<div class="empty-state">No scheduled bouts are listed on the official card.</div>';
 document.getElementById("games").setAttribute("data-render-complete","true");
}).catch(()=>{
 document.getElementById("slate-meta").textContent="MMA DATA UNAVAILABLE";
 document.getElementById("games").innerHTML='<div class="empty-state">The current official card could not be verified. No positions are displayed.</div>';
 document.getElementById("games").setAttribute("data-render-complete","error");
});
</script>
'''


def main():
    # The existing contract validates the authoritative fields without changing them.
    payload = json.loads((ROOT / "data/mma_today.json").read_text())
    validated_card(payload)
    positions = validated_positions(payload)
    if not positions and (
        payload.get("active_model") is not None
        or payload.get("active_model_sha256") is not None
    ):
        raise RuntimeError("unissued MMA public payload exposes a model identity")
    html = head('APEX — MMA Picks', 'APEX MMA / UFC official card and sealed FanDuel picks.', '/mma')
    html = html.replace('/assets/apex.css?v=apex-20260825-mma', '/assets/apex.css?v=apex-20260910-mma-card-parity')
    html = html.replace('</head>', BEACON_BLOCK + '\n' + ANALYTICS_BLOCK + '\n</head>')
    html += '\n' + hero().replace('<div class="shell">', '<div class="shell" data-picks-state="quiet" data-public-issuance="false" data-sport="MMA">')
    html += '\n' + NAVIGATION + '''
  <div class="section-head picks-board-head">
    <div class="title">TODAY'S CARD</div>
    <div class="meta mono" id="slate-meta">LOADING OFFICIAL CARD</div>
  </div>
  <main class="picks-page"><div class="picks-board" id="games" aria-live="polite"></div></main>
  <div class="tag">THE MATH SPEAKS.</div>
  <div class="foot mono">APEX MMA / UFC · SEALED FANDUEL POSITIONS</div>
'''
    html += SCRIPT + close()
    print('MMA_PICKS_PATH=' + str(write('mma/index.html', html)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
