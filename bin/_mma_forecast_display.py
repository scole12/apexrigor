"""MMA uses the same game-module and market-panel markup as MLB/NCAA."""
DISPLAY_SCRIPT = r'''
<script>
window.ApexMmaDisplay=(()=>{
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const label=v=>String(v??'').replaceAll('_',' ');
 const clock=v=>{const d=new Date(v);return v&&Number.isFinite(d.getTime())?new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',hour:'numeric',minute:'2-digit',timeZoneName:'short'}).format(d):'TIME TBA'};
 const stamp=v=>{const d=new Date(v);return v&&Number.isFinite(d.getTime())?new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',month:'short',day:'numeric',hour:'numeric',minute:'2-digit',timeZoneName:'short'}).format(d):'Not recorded'};
 const odds=v=>v===null||v===undefined?'Not recorded':(Number(v)>0?'+':'')+String(v);
 const norm=v=>String(v??'').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]/gi,'').toLowerCase();
 const pair=b=>[norm(b.fighter_a),norm(b.fighter_b)].filter(Boolean).sort().join('|');
 function panel(p){
  let headline=p.display_selection||p.selection;
  if(!p.display_selection&&p.line!==null&&p.line!==undefined&&!String(headline).endsWith(' '+p.line))headline+=' '+p.line;
  const rationale=String(p.rationale||'').split(/\n\s*\n/).filter(x=>x.trim());
  const issued=p.trace?.issuance_id||p.issuance_id||'';
  const probability=Number(p.probability);
  return `<section class="market-panel" data-market="${esc(p.market)}" data-position-state="SEALED" data-issuance="${esc(issued)}"><div class="market-label">${esc(label(p.market))}</div><div class="market-panel-head"><span class="pick-headline">${esc(headline)}</span><span class="rating-label">APEX WIN PROBABILITY RATING</span><span class="tier-badge tier-badge--${esc(String(p.tier).toLowerCase())}">${esc(p.tier)}</span></div><div class="meta mono">APEX PROBABILITY: ${(probability*100).toFixed(1)}% · FANDUEL: ${esc(odds(p.price))}${p.line!==null&&p.line!==undefined?' · LINE: '+esc(p.line):''}</div><div class="rationale-copy" aria-label="Pick rationale">${rationale.map(x=>'<p>'+esc(x)+'</p>').join('')}</div>${p.quote_time?'<div class="meta mono">FANDUEL CAPTURE: '+esc(stamp(p.quote_time))+'</div>':''}</section>`;
 }
 function boutCard(b,positions,i){
  const name=b.matchup||(b.fighter_a&&b.fighter_b?b.fighter_a+' vs '+b.fighter_b:'MMA BOUT');
  const context=[label(b.weight_class),b.segment,b.scheduled_rounds?b.scheduled_rounds+' ROUNDS':null].filter(Boolean).join(' · ');
  const time=b.scheduled_start_utc?clock(b.scheduled_start_utc):(b.is_main_event?'MAIN EVENT':b.is_co_main_event?'CO-MAIN':'CARD ORDER '+String(b.official_display_order||i+1));
  const body=positions.length?'<div class="market-grid'+(positions.length===1?' market-grid--single':'')+'">'+positions.map(panel).join('')+'</div>':'<p class="meta mono" data-position-state="UNISSUED">NOT ISSUED · NO FORECAST OR PICK RATIONALE AVAILABLE</p>';
  return `<article class="game-module" data-bout="${esc(b.bout_id||b.apex_mma_bout_id||name)}" data-game-state="${positions.length?'ISSUED':'UNISSUED'}"><header class="game-header"><div class="game-num mono">F${String(i+1).padStart(2,'0')}</div><div class="game-meta"><h2 class="game-matchup">${esc(name)}</h2><p class="game-pitchers mono">${esc(context)}</p></div><div class="game-time mono">${esc(time)}</div></header>${body}</article>`;
 }
 function board(card,positions){
  const groups=card.map(b=>({b,positions:[]}));
  for(const p of positions){
   let group=groups.find(g=>(g.b.bout_id||g.b.apex_mma_bout_id)===p.bout_id||((pair(p)&&pair(g.b)===pair(p)))||norm(g.b.matchup||(g.b.fighter_a+' vs '+g.b.fighter_b))===norm(p.matchup));
   if(!group){group={b:{...p,official_display_order:groups.length+1},positions:[]};groups.push(group)}
   group.positions.push(p);
  }
  return groups.map((g,i)=>boutCard(g.b,g.positions,i)).join('');
 }
 function status(d){
  if(d.forecast)return d.forecast;
  if(d.picks_published&&(d.positions||[]).length)return{code:'FORECASTS_ISSUED',headline:'Forecasts issued',detail:'Selections and rationale from the sealed T-2 card.'};
  const s=String(d.t2?.status||'');const due=Date.parse(d.t2?.scheduled_utc||'');
  if((/FAIL|BLOCKED|NO_RELEASE/.test(s)&&!s.includes('AWAITING_TARGET'))||(Number.isFinite(due)&&Date.now()>=due))return{code:'NO_FORECASTS_ISSUED',headline:'No forecasts issued',detail:'No approved forecast card is available for this event. The schedule is not a set of picks.'};
  return{code:'AWAITING_T2',headline:'Awaiting the T-2 forecast run',detail:'No forecasts have been issued yet.'};
 }
 return {esc,label,clock,stamp,odds,panel,board,status};
})();
</script>
'''
