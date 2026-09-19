#!/usr/bin/env python3
"""Render the official MMA card with the shared NFL/NCAAF picks chrome."""
import json
import html as html_lib
import hashlib
from datetime import date, datetime, timezone

from _mma_public import ROOT, close, head, hero, write
from _mma_forecast_contract import _fighter_pair, validated_card, validated_positions
from apply_cloudflare_web_analytics import BEACON_BLOCK
from apply_vercel_web_analytics import ANALYTICS_BLOCK
from apex_mma_late_presentation import COMPARISON_CSS, comparison_html, intro_paragraphs


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
function displayRows(d,positions){
 const display=d.market_display;
 if(display==null)return new Map();
 if(display.source_issuance_id!==d.issuance_id||display.source_positions_sha256!==d.positions_sha256||!Array.isArray(display.bouts))return new Map();
 const winners=positions.filter(p=>p.market==="WINNER"),rows=new Map();
 for(const b of display.bouts){
  const p=winners.find(p=>p.bout_id===b.bout_id);
  if(!p||rows.has(b.bout_id)||b.selected_fighter!==p.selection||b.prediction_sha256!==p.trace.prediction_sha256||!Array.isArray(b.moneylines)||b.moneylines.length!==2||!Array.isArray(b.slots)||b.slots.length!==4)return new Map();
  for(const [i,row] of b.slots.entries()){
   if(row.slot_id!=="L"+(i+1)||row.price!==null||row.plus_money!==null||!["NOT_POSTED","NOT_AVAILABLE"].includes(row.fanduel_status)||row.issuance_status!=="UNISSUED"||(row.probability!==null&&(!Number.isFinite(row.probability)||row.probability<0||row.probability>1)))return new Map();
  }
  rows.set(b.bout_id,{...b,sealed_at_utc:display.sealed_at_utc,source_card_sha256:display.source_card_sha256,source_issuance_id:display.source_issuance_id});
 }
 if(rows.size!==winners.length)return new Map();
 return rows;
}
function moneylineHeadsUp(b){
 if(!b)return "";
 const moneylines=b.moneylines.map(q=>esc(q.fighter)+" "+(q.price==null?"NOT CAPTURED AT T-2":(q.price>0?"+":"")+esc(q.price))).join(" · ");
 return '<p class="meta mono">FANDUEL MONEYLINES · '+moneylines+'</p>';
}
function marketBreakdown(b){
 if(!b)return "";
 const rows=b.slots.map(row=>{
  const probability=row.probability==null?'NOT AVAILABLE':(row.probability*100).toFixed(1)+'%';
  const price=Number.isFinite(row.price)&&Math.abs(row.price)>=100?'<span class="meta mono">FanDuel '+(row.price>0?'+':'')+esc(row.price)+'</span>':'';
  const plusMoney=price&&row.plus_money===true&&row.price>0?'<span class="meta mono">PLUS MONEY</span>':'';
  return '<section class="mma-market-slot" data-market-slot="'+esc(row.slot_id)+'" data-position-state="UNISSUED">'
   +'<div class="market-label">'+esc(row.slot_id)+'</div>'
   +'<h3 class="pick-headline">'+esc(row.selection)+'</h3>'
   +'<p class="meta mono mma-slot-probability">APEX PROBABILITY: <strong>'+probability+'</strong></p>'
   +(price?'<div class="mma-slot-price">'+price+plusMoney+'</div>':'')+'</section>';
 }).join("");
 return '<section class="market-panel mma-market-breakdown" data-source-issuance="'+esc(b.source_issuance_id)+'" data-source-card-sha256="'+esc(b.source_card_sha256)+'">'
  +'<div class="market-label">LONGSHOT MARKETS</div>'
  +'<p class="meta mono">MODEL BREAKDOWN · ISSUED CARD '+esc(clock(b.sealed_at_utc))+'</p>'
  +'<div class="mma-market-slots">'+rows+'</div></section>';
}
function issuedPanel(p,display){
 const headline=p.display_selection||p.selection;
 return '<section class="market-panel" data-market="'+esc(p.market)+'" data-position-state="SEALED" data-position-bout="'+esc(p.bout_id)+'">'
  +'<div class="market-label">'+esc(p.market==="WINNER"?"HEADS-UP WINNER":p.market)+'</div>'
  +'<div class="market-panel-head"><span class="pick-headline">'+esc(headline)+'</span>'
  +'<span class="rating-label">APEX WIN PROBABILITY RATING</span>'
  +'<span class="tier-badge tier-badge--'+esc(p.tier.toLowerCase())+'">'+esc(p.tier)+'</span></div>'
  +'<div class="meta mono">APEX WIN PROBABILITY: '+(p.probability*100).toFixed(1)+'% · Sportsbook: FanDuel · '+(p.price>0?'+':'')+esc(p.price)+'</div>'
  +moneylineHeadsUp(display)
  +'<div class="rationale-copy">'+paragraphs(p.rationale).map(text=>'<p>'+esc(text)+'</p>').join("")+'</div></section>';
}
fetch("/data/mma_today.json",{cache:"no-store"}).then(r=>{if(!r.ok)throw new Error("HTTP "+r.status);return r.json()}).then(d=>{
 if(!d.event?.event_date||!Array.isArray(d.card)||d.card.some(b=>!b||!matchup(b)))throw new Error("Invalid official card");
 const e=d.event,positions=issuedPositions(d),display=displayRows(d,positions);
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
  let panels=issued.slice().sort((a,b)=>(a.market==="WINNER"?0:1)-(b.market==="WINNER"?0:1)).map(p=>issuedPanel(p,p.market==="WINNER"?display.get(p.bout_id):null)).join("");
  const winner=issued.find(p=>p.market==="WINNER"),breakdown=winner?display.get(winner.bout_id):null;
  if(breakdown)panels+=marketBreakdown(breakdown);
  if(!issued.length){
   const badge=forecast.code==="AWAITING_T2"?"SCHEDULED":"FAIL CLOSED";
   panels='<section class="market-panel" data-position-state="UNISSUED" data-forecast-code="'+esc(forecast.code)+'"><div class="market-label">STATUS</div><div class="market-panel-head"><span class="pick-headline">UNISSUED — '+esc(forecast.headline.toUpperCase())+'</span><span class="tier-badge tier-badge--moderate">'+badge+'</span></div><div class="rationale-copy"><p>'+esc(forecast.detail)+'</p></div></section>';
  }
  const eventContext=[e.display_name||e.name,e.venue].filter(Boolean).join(" / ");
  const context=[String(b.weight_class||"").replaceAll("_"," "),eventContext].filter(Boolean).join(" · ");
  return '<article class="game-module" data-game="'+esc(b.bout_id||b.apex_mma_bout_id||matchup(b))+'" data-game-state="'+(issued.length?'ISSUED':'UNISSUED')+'">'
   +'<header class="game-header"><div class="game-num mono">F'+String(i+1).padStart(2,"0")+'</div><div class="game-meta">'
   +'<h2 class="game-matchup">'+esc(matchup(b))+'</h2><p class="game-pitchers mono">'+esc(context)+'</p></div><div class="game-time mono">'+esc(boutTime(b,e))+'</div></header>'
   +'<div class="market-grid'+(issued.length===1&&!breakdown?' market-grid--single':'')+'">'+panels+'</div></article>';
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


def late_report_page(payload):
    """Project the captured roster into the existing customer card components.

    Comparisons use the same frozen facts as the linked report. This projection
    neither refreshes the report nor creates an issuance or a live bout status.
    """
    report = payload['late_data_report']
    if (report.get('label') != 'LATE DATA RECOVERY NOT PREGAME T3'
            or report.get('sport') != 'MMA'
            or report.get('artifact_type') != 'LATE_DATA_REPORT'
            or report.get('picks') != [] or report.get('positions') != []
            or report.get('picks_published') is not False
            or report.get('official_issuance') is not False
            or payload.get('picks_published') is not False
            or validated_positions(payload)
            or payload.get('active_model') is not None
            or payload.get('active_model_sha256') is not None):
        raise RuntimeError('INVALID_LATE_DATA_WEBSITE_REPORT')
    digest = hashlib.sha256(json.dumps(
        {k: v for k, v in report.items() if k != 'report_sha256'},
        sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()
    if (digest != report.get('report_sha256')
            # The public Today contract omits raw event IDs; its builder already
            # checks the report ID against the canonical state before projection.
            or report.get('event_name') != payload['event'].get('name')
            or report.get('event_date') != payload['event'].get('event_date')):
        raise RuntimeError('LATE_DATA_WEBSITE_REPORT_BINDING_MISMATCH')
    event_date = date.fromisoformat(report['event_date'])
    pdf_relative = 'mma/reports/APEX_UFC_MMA_LATE_DATA_REPORT_' + event_date.strftime('%Y%m%d') + '.pdf'
    if not (ROOT / pdf_relative).is_file():
        raise RuntimeError('CAPTURED_LATE_REPORT_PDF_MISSING')
    # A presentation revision is an additional artifact, never an overwrite of
    # the PDF already accepted by the mail provider. Bind it to this exact report.
    revised_relative = pdf_relative[:-4] + '_PRESENTATION_REV2.pdf'
    revision_manifest = ROOT / (revised_relative + '.json')
    if revision_manifest.is_file():
        binding = json.loads(revision_manifest.read_text())
        revised_path = ROOT / revised_relative
        if (binding.get('report_sha256') != report['report_sha256']
                or binding.get('event_date') != report['event_date']
                or binding.get('original_pdf_sha256') != hashlib.sha256((ROOT / pdf_relative).read_bytes()).hexdigest()
                or not revised_path.is_file()
                or binding.get('pdf_sha256') != hashlib.sha256(revised_path.read_bytes()).hexdigest()):
            raise RuntimeError('LATE_REPORT_PRESENTATION_REVISION_BINDING_MISMATCH')
        pdf_relative = revised_relative

    roster, cancelled = {}, []
    for bout in report['official_card']['bouts']:
        pair = _fighter_pair(bout, 'Captured MMA roster')
        if bout.get('roster_disposition') == 'EXCLUDED_CANCELLED' and bout.get('source_status') == 'CANCELLED':
            cancelled.append(bout)
        elif bout.get('roster_disposition') == 'CURRENT_ROSTER' and bout.get('source_status') != 'CANCELLED':
            if pair in roster:
                raise RuntimeError('DUPLICATE_LATE_DATA_ROSTER_PAIR')
            roster[pair] = bout
        else:
            raise RuntimeError('UNVERIFIED_LATE_DATA_ROSTER_DISPOSITION')
    card = sorted(validated_card(payload), key=lambda b: b['official_display_order'])
    if (set(roster) != {_fighter_pair(b, 'Official MMA card') for b in card}
            or len(roster) != report.get('current_roster_bout_count')
            or len(cancelled) != report.get('excluded_bout_count')
            or any(_fighter_pair(b, 'Cancelled MMA pairing') in roster for b in cancelled)):
        raise RuntimeError('LATE_DATA_ROSTER_RECONCILIATION_MISMATCH')

    esc = lambda value: html_lib.escape(str(value), quote=True)
    capture = datetime.fromisoformat(report['source_captured_at_utc'].replace('Z', '+00:00'))
    if capture.tzinfo is None:
        raise RuntimeError('LATE_DATA_CAPTURE_TIMEZONE_REQUIRED')
    capture_label = capture.astimezone(timezone.utc).strftime('%B %d, %Y at %H:%M UTC')
    page = head('APEX — MMA Picks', 'MMA event roster and late factual report. No picks issued.', '/mma')
    page = page.replace('</head>', '<style>' + COMPARISON_CSS + '</style>\n' + BEACON_BLOCK + '\n' + ANALYTICS_BLOCK + '\n</head>')
    page += '\n' + hero().replace('<div class="shell">', '<div class="shell" data-picks-state="quiet" data-public-issuance="false" data-sport="MMA">')
    page += '\n' + NAVIGATION
    page += '<div class="section-head picks-board-head"><div class="title">TODAY\'S CARD</div><div class="meta mono" id="slate-meta">' + esc(event_date.strftime('%B %d, %Y').upper()) + ' · ' + str(len(card)) + ' BOUTS · NO PICKS ISSUED</div></div>'
    page += '<main class="picks-page"><section aria-labelledby="report-heading"><h1 class="game-matchup" id="report-heading">' + esc(report['event_name']) + '</h1>'
    page += '<div class="rationale-copy mma-report-intro">' + ''.join('<p>' + esc(text) + '</p>' for text in intro_paragraphs(report))
    page += '<p><a href="/' + esc(pdf_relative) + '">Read the fighter comparison report (PDF)</a></p></div></section>'
    page += '<section aria-labelledby="roster-heading"><h2 class="market-label" id="roster-heading">EVENT ROSTER</h2><div class="picks-board" id="games" data-render-complete="true" data-sport="MMA" data-artifact-type="LATE_DATA_REPORT">'
    for number, bout in enumerate(card, 1):
        captured = roster[_fighter_pair(bout, 'Official MMA card')]
        context = [captured.get('weight_class'), payload['event'].get('venue')]
        segment = {'MAIN': 'MAIN CARD', 'MAIN_CARD': 'MAIN CARD', 'PRELIMS': 'PRELIMS', 'EARLY_PRELIMS': 'EARLY PRELIMS'}.get(str(bout.get('segment', '')).upper(), 'EVENT ROSTER')
        page += '<article class="game-module" data-game-state="UNISSUED"><header class="game-header"><div class="game-num mono">F' + f'{number:02d}' + '</div><div class="game-meta"><h3 class="game-matchup">' + esc(bout['fighter_a'] + ' vs ' + bout['fighter_b']) + '</h3><p class="game-pitchers mono">' + esc(' · '.join(str(v) for v in context if v)) + '</p></div><div class="game-time mono">' + esc(segment) + '</div></header>'
        page += '<div class="market-grid market-grid--single"><section class="market-panel" data-position-state="UNISSUED"><div class="market-label">STATUS</div><div class="rationale-copy"><p>No picks issued for this bout.</p></div></section></div>'
        page += comparison_html(captured, report['event_date']) + '</article>'
    page += '</div></section>'
    if cancelled:
        page += '<section class="mma-cancelled" aria-labelledby="cancelled-heading"><h2 class="market-label" id="cancelled-heading">CANCELLED PAIRINGS</h2><div class="rationale-copy"><p>These pairings were cancelled and are excluded from the event roster above. The captured fighter profiles are retained below for completeness.</p></div>'
        for bout in cancelled:
            page += '<details class="game-module"><summary class="game-matchup">' + esc(bout['fighter_a'] + ' vs ' + bout['fighter_b']) + ' — Cancelled</summary>'
            page += comparison_html(bout, report['event_date']) + '</details>'
        page += '</section>'
    page += '</main><div class="tag">THE MATH SPEAKS.</div><div class="foot mono">APEX MMA / UFC · LATE FACTUAL REPORT · NO PICKS ISSUED</div>' + close()
    return page


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
    if payload.get('artifact_type') == 'LATE_DATA_REPORT':
        print('MMA_LATE_DATA_PATH=' + str(write('mma/index.html', late_report_page(payload))))
        return 0
    html = head('APEX — MMA Picks', 'APEX MMA / UFC official card and sealed FanDuel picks.', '/mma')
    html = html.replace('/assets/apex.css?v=apex-20260825-mma', '/assets/apex.css?v=apex-20260910-mma-card-parity')
    html = html.replace('</head>', '<style>.mma-market-breakdown{display:flex;flex-direction:column;align-self:stretch;min-width:0}.mma-market-slots{display:grid;grid-template-rows:repeat(4,minmax(0,1fr));flex:1;min-width:0}.mma-market-slot{display:flex;flex-direction:column;justify-content:flex-start;gap:12px;padding:22px 0;box-sizing:border-box;border-top:1px solid var(--hairline)}.mma-market-slot .market-label,.mma-market-slot .pick-headline,.mma-market-slot p{margin:0}.mma-market-slot .pick-headline{line-height:1.5;overflow-wrap:anywhere}.mma-slot-probability{font-size:14px;line-height:1.5}.mma-slot-probability strong{font-weight:700}.mma-slot-price{display:flex;gap:16px;flex-wrap:wrap}@media(max-width:900px){.mma-market-slots{grid-template-rows:none;grid-auto-rows:auto;flex:none}.mma-market-slot{padding:22px 0}}</style>' + BEACON_BLOCK + '\n' + ANALYTICS_BLOCK + '\n</head>')
    issuance_state = 'issued' if positions else 'quiet'
    public_flag = 'true' if positions else 'false'
    html += '\n' + hero().replace('<div class="shell">',
        '<div class="shell" data-picks-state="' + issuance_state + '" data-public-issuance="' + public_flag
        + '" data-sport="MMA" data-event-id="' + html_lib.escape(str(payload.get('event_id') or ''), quote=True)
        + '" data-issuance-id="' + html_lib.escape(str(payload.get('issuance_id') or ''), quote=True) + '">')
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
