"""Read-only results projection. Never runs inference or infers fight outcomes."""
LEDGER_SCRIPT = r'''
<script>
window.ApexMmaResults=(()=>{
 const tiers=['WEAK','MODERATE','STRONG','ELITE'];
 const aliases={W:'W',WIN:'W',WON:'W',L:'L',LOSS:'L',LOST:'L',P:'P',PUSH:'P',VOID:'VOID',VOIDED:'VOID',PENDING:'PENDING',UNSETTLED:'PENDING'};
 const outcome=v=>aliases[String(v??'PENDING').toUpperCase()]||'PENDING';
 const key=p=>JSON.stringify([p.issuance_id,p.bout_id,p.market,p.selection,p.line??null]);
 function ledger(today,summary,archive,validate){
  if(!Array.isArray(archive.events)||!Array.isArray(summary.latest_event_results))throw new Error('MMA result source format is incomplete');
  const events=[],byIssuance=new Map(),warnings=[];
  const documents=[...archive.events,today];
  for(const doc of documents){
   if(doc!==today&&(doc.official_issuance===false||doc.status==='UNVALIDATED_RESEARCH_NOT_OFFICIAL_ISSUANCE'))continue;
   const rows=validate(doc);if(!rows.length)continue;
   const date=doc.event?.event_date||doc.event_date;
   if(!/^\d{4}-\d{2}-\d{2}$/.test(String(date))||!doc.issuance_id)throw new Error('Issued result card lacks its date or issuance');
   const positions=rows.map((p,i)=>({...p,issuance_id:doc.issuance_id,event_date:date,order:i+1,result:'PENDING'}));
   const event={date,name:doc.event?.display_name||doc.event?.name||doc.event_name||'UFC event',issuance_id:doc.issuance_id,positions,grades:[...(doc.latest_results||doc.results||[])]};
   if(byIssuance.has(doc.issuance_id)){
    const previous=byIssuance.get(doc.issuance_id);
    if(JSON.stringify(previous.positions)!==JSON.stringify(positions))throw new Error('Conflicting as-issued archive');
    previous.grades.push(...event.grades);continue;
   }
   events.push(event);byIssuance.set(doc.issuance_id,event);
  }
  const positions=events.flatMap(e=>e.positions),seen=new Set(),grades=new Map();
  for(const p of positions){if(seen.has(key(p)))throw new Error('Duplicate issued position');seen.add(key(p));}
  const gradeRows=[...events.flatMap(e=>e.grades.map(g=>({...g,issuance_id:g.issuance_id||e.issuance_id}))),...summary.latest_event_results];
  for(const g of gradeRows){
   const bid=g.bout_id||g.apex_mma_bout_id,market=g.market||g.market_family,selection=g.issued_selection||g.selection;
   const matches=positions.filter(p=>bid&&p.bout_id===bid&&(!g.issuance_id||g.issuance_id===p.issuance_id)&&(!market||p.market===market)&&(!selection||p.selection===selection)&&(g.issued_line===undefined||g.issued_line===p.line));
   if(matches.length!==1){warnings.push('Some recorded grades could not be matched to an issued selection.');continue;}
   const p=matches[0],result=outcome(g.result||g.outcome||g.status),id=key(p);
   if(grades.has(id)&&grades.get(id)!==result)throw new Error('Conflicting published grades require reconciliation');
   grades.set(id,result);p.result=result;
  }
  if(Number(summary.issued_event_count||0)>events.length)warnings.push('Earlier issued event details are not present in the published archive.');
  if(Number(summary.commercial_settlement_count||0)>positions.filter(p=>p.result!=='PENDING').length)warnings.push('Some settlement details have not reached the public ledger.');
  events.sort((a,b)=>b.date.localeCompare(a.date)||a.issuance_id.localeCompare(b.issuance_id));
  return{events,positions,warnings:[...new Set(warnings)]};
 }
 function record(rows){const r={W:0,L:0,P:0,VOID:0,PENDING:0};for(const p of rows)r[outcome(p.result)]++;return r;}
 const recordText=r=>`${r.W.toLocaleString('en-US')}-${r.L.toLocaleString('en-US')}${r.P?'-'+r.P+'P':''}${r.VOID?'-'+r.VOID+'V':''}`;
 const winRate=r=>r.W+r.L?((100*r.W)/(r.W+r.L)).toFixed(1)+'%':'—';
 const marketLabel=v=>String(v).replaceAll('_',' ').replace(/\b\w/g,x=>x.toUpperCase());
 const dateLabel=v=>{if(!/^\d{4}-\d{2}-\d{2}$/.test(String(v)))return '—';return new Intl.DateTimeFormat('en-US',{timeZone:'UTC',month:'long',day:'2-digit',year:'numeric'}).format(new Date(v+'T12:00:00Z'));};
 return{tiers,outcome,ledger,record,recordText,winRate,marketLabel,dateLabel};
})();
</script>
'''
