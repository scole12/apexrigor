(() => {
  "use strict";
  const root = document.getElementById("results-root");
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const fmtRecord = (w,l,p=0) => `${Number(w).toLocaleString("en-US")}-${Number(l).toLocaleString("en-US")}${p?`-${p}P`:""}`;
  const recRows = (rows) => {
    const w = rows.filter(r => r.result === "WIN").length;
    const l = rows.filter(r => r.result === "LOSS").length;
    const p = rows.filter(r => r.result === "PUSH").length;
    const d = w+l;
    return { w,l,p, label: `${w}-${l}${p?`-${p}P`:""}`, rate: d?`${(100*w/d).toFixed(1)}%`:"—", n: rows.length };
  };
  const table = (headers, rows) => `<table class="results"><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map((c,i)=>`<td class="${i===0?"mono":"mono"}">${esc(c)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;

  async function load() {
    const archRes = await fetch("/data/nfl_results_archive.json", {cache:"no-store"});
    if (!archRes.ok) throw new Error("archive HTTP "+archRes.status);
    const archive = await archRes.json();
    if (!archive.canonical_result || !Array.isArray(archive.rows) || !archive.coverage || !archive.cumulative)
      throw new Error('Canonical NFL result pending');
    const nflSport = archive.cumulative;
    const overall = nflSport.season_record;
    const ow=overall.W, ol=overall.L, op=overall.PUSH;
    const owr=overall.win_rate===null ? '—' : `${(100*overall.win_rate).toFixed(1)}%`;
    const atsBanner=fmtRecord(nflSport.ats_record.W,nflSport.ats_record.L,nflSport.ats_record.PUSH);
    const totBanner=fmtRecord(nflSport.totals_record.W,nflSport.totals_record.L,nflSport.totals_record.PUSH);
    const props = nflSport.props_record;
    if (!props || ![props.W, props.L, props.PUSH].every(n => Number.isSafeInteger(n) && n >= 0))
      throw new Error('Canonical NFL Player Props record required');
    const propsBanner=fmtRecord(props.W,props.L,props.PUSH);
    const rate = record => record.W+record.L ? `${(100*record.W/(record.W+record.L)).toFixed(1)}%` : '—';
    const propsRate=rate(props), atsRate=rate(nflSport.ats_record), totRate=rate(nflSport.totals_record);
    const keys = new Set();
    const rows = archive.rows.map(r => {
      const key=JSON.stringify([r.sport,r.issuance_id,r.position_id]);
      if (r.sport!=='NFL' || !r.issuance_id || !r.position_id || keys.has(key)) throw new Error('Invalid canonical result identity');
      keys.add(key);
      return {id:key,date:r.game_date,game:r.game_id,matchup:r.matchup,market:r.market,pick:r.pick,
              tier:r.tier,result:({WIN:'W',LOSS:'L',PUSH:'P'})[r.result]||r.result,resultFull:r.result};
    });
    const byTier = (market) => ["WEAK","MODERATE","STRONG","ELITE"].map(tier => {
      const selected = rows.filter(r => r.tier === tier && (!market || r.market === market));
      const c = recRows(selected.map(r => ({result: r.resultFull === "W" || r.result === "W" ? "WIN" : r.resultFull === "L" || r.result === "L" ? "LOSS" : r.resultFull})));
      // fix resultFull mapping
      const sel = rows.filter(r => r.tier === tier && (!market || r.market === market));
      const wins = sel.filter(r => r.result === "W" || r.resultFull === "WIN").length;
      const losses = sel.filter(r => r.result === "L" || r.resultFull === "LOSS").length;
      const pushes = sel.filter(r => r.result === "P" || r.resultFull === "PUSH").length;
      const d = wins+losses;
      return [tier[0]+tier.slice(1).toLowerCase(), `${wins}-${losses}${pushes?`-${pushes}P`:""}`, d?`${(100*wins/d).toFixed(1)}%`:"—"];
    });

    const tracked = Object.values(archive.coverage).reduce((n,c)=>n+c.issued,0);
    const pending = archive.pending.length;
    if (rows.length+pending!==tracked) throw new Error('Canonical coverage mismatch');
    const today = new Intl.DateTimeFormat("en-US",{timeZone:"America/New_York", weekday:"long", month:"long", day:"numeric", year:"numeric"}).format(new Date()).toUpperCase();

    let html = "";
    // NFL record and coverage from the one canonical payload.
    html += `<div class="section-head"><div class="title">SEASON RECORD</div><div class="meta mono">${esc(today)} · ${Number(tracked).toLocaleString("en-US")} POSITIONS TRACKED</div></div>`;
    html += `<div class="banner" data-apex-season-record="${esc(fmtRecord(ow,ol,op))}" data-apex-season-win-rate="${esc(owr)}" data-apex-ats-record="${esc(atsBanner)}" data-apex-totals-record="${esc(totBanner)}" data-apex-props-record="${esc(propsBanner)}" data-apex-props-win-rate="${esc(propsRate)}">
      <div class="cell"><div class="label">NFL Overall</div><div class="val mono">${esc(fmtRecord(ow,ol,op))}</div><div class="label mono">${esc(owr)} WIN RATE</div></div>
      <div class="cell"><div class="label">NFL ATS</div><div class="val mono">${esc(atsBanner)}</div><div class="label mono">${esc(atsRate)} WIN RATE</div></div>
      <div class="cell"><div class="label">NFL Totals</div><div class="val mono">${esc(totBanner)}</div><div class="label mono">${esc(totRate)} WIN RATE</div></div>
      <div class="cell"><div class="label">NFL Player Props</div><div class="val mono">${esc(propsBanner)}</div><div class="label mono">${esc(propsRate)} WIN RATE</div></div>
    </div>`;

    // Tier tables follow Season Record directly (Scott 2026-09-17: remove Inherited V2 / AS-ISSUED head verbiage)
    html += `<div class="tier-grid">
      <div class="tier-col"><div class="tier-sub">ATS BY AS-ISSUED MODEL RATING</div>${table(["Model rating","Record","Win Rate"], byTier("ATS"))}</div>
      <div class="tier-col"><div class="tier-sub">TOTALS BY AS-ISSUED MODEL RATING</div>${table(["Model rating","Record","Win Rate"], byTier("TOTALS"))}</div>
    </div>`;
    // PROPS tier as third optional single like combined
    html += `<div class="tier-sub">PROPS BY AS-ISSUED MODEL RATING</div><div class="tier-single">${table(["Model rating","Record","Win Rate"], byTier("PROPS"))}</div>`;
    html += `<div class="tier-sub">COMBINED NFL BY AS-ISSUED MODEL RATING</div><div class="tier-single">${table(["Model rating","Record","Win Rate"], byTier(null))}</div>`;

    // DAILY ARCHIVE — MLB style Date / Record / Win Rate / Summary
    const days = new Map();
    for (const row of rows) {
      if (!days.has(row.date)) days.set(row.date, []);
      days.get(row.date).push(row);
    }
    const sortedDays = Array.from(days).sort(([a],[b]) => String(b).localeCompare(String(a)));
    const dailyRows = sortedDays.map(([date, selected]) => {
      const wins = selected.filter(r => r.result === "W").length;
      const losses = selected.filter(r => r.result === "L").length;
      const pushes = selected.filter(r => r.result === "P").length;
      const d = wins+losses;
      return [date, `${wins}W-${losses}L${pushes?`-${pushes}P`:""}`, d?`${(100*wins/d).toFixed(1)}%`:"—", `NFL ${wins}-${losses}`];
    });
    html += `<div class="section-head"><div class="title">DAILY ARCHIVE</div></div>`;
    html += table(["Date","Record","Win Rate","Summary"], dailyRows);

    // SLATE DETAIL — MLB columns: Game, Matchup, Market, Pick, Tier, Result
    for (const [date, selected] of sortedDays) {
      const details = selected.slice().sort((a,b)=>`${a.game}|${a.market}|${a.id}`.localeCompare(`${b.game}|${b.market}|${b.id}`))
        .map((row, idx) => [row.game || `G${String(idx+1).padStart(2,"0")}`, row.matchup, row.market, row.pick, row.tier, row.result]);
      html += `<div class="section-head"><div class="title">SLATE DETAIL — ${esc(date)}</div><div class="meta mono">${selected.length} POSITIONS</div></div>`;
      html += table(["Game","Matchup","Market","Pick","As-issued model rating","Result"], details);
    }
    root.innerHTML = html;
  }
  load().catch(err => {
    root.innerHTML = `<p class="muted">Results temporarily unavailable.</p>`;
    console.error(err);
  });
})();
