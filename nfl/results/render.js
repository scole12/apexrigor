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
    const [sumRes, archRes] = await Promise.all([
      fetch("/data/apex_results_summary.json", {cache:"no-store"}),
      fetch("/data/nfl_results_archive.json", {cache:"no-store"}),
    ]);
    if (!sumRes.ok) throw new Error("summary HTTP "+sumRes.status);
    if (!archRes.ok) throw new Error("archive HTTP "+archRes.status);
    const summary = await sumRes.json();
    const archive = await archRes.json();
    const overall = summary.overall || {};
    const nflSport = (summary.sports || {}).nfl || {};
    const ow = overall.wins|0, ol = overall.losses|0, op = overall.pushes|0;
    const owr = overall.win_rate_display || (ow+ol?`${(100*ow/(ow+ol)).toFixed(1)}%`:"—");
    // NFL market lines from sport block / cumulative fields
    const ats = nflSport.ats_record || "0W-0L-0P";
    const tot = nflSport.totals_record || "0W-0L-0P";
    const props = nflSport.props_record || "0W-0L-0P";
    // normalize 0W-1L-0P -> 0-1 for banner? MLB uses 909-842-4P without W letters in banner
    const strip = (s) => String(s).replace(/W/g,"").replace(/L/g,"-").replace(/-0P$/,"").replace(/P$/,(m)=>m);
    // Better parse W/L/P
    const parseWLP = (s) => {
      const m = String(s).match(/(\\d+)W-(\\d+)L(?:-(\\d+)P)?/);
      if (!m) return String(s).replace(/W|L/g,"");
      return fmtRecord(+m[1], +m[2], +(m[3]||0)).replace(/,/g,""); // NFL small N no commas needed but ok
    };
    const atsBanner = (() => { const m=String(ats).match(/(\\d+)W-(\\d+)L(?:-(\\d+)P)?/); return m?`${m[1]}-${m[2]}${m[3]&&+m[3]?`-${m[3]}P`:""}`:ats; })();
    const totBanner = (() => { const m=String(tot).match(/(\\d+)W-(\\d+)L(?:-(\\d+)P)?/); return m?`${m[1]}-${m[2]}${m[3]&&+m[3]?`-${m[3]}P`:""}`:tot; })();

    // Build settled rows from archive (same as before)
    const issued = new Map();
    for (const issuance of archive.issuances || []) {
      const gd = issuance.game_date;
      for (const position of issuance.positions || []) {
        issued.set(position.position_id, { position, date: gd || "—" });
      }
    }
    const replaced = new Set((archive.grades || []).map(g => g.supersedes_grade_id).filter(Boolean));
    const settled = new Map();
    for (const grade of archive.grades || []) {
      if (replaced.has(grade.grade_id)) continue;
      for (const settlement of grade.settlements || []) {
        if (!settlement.result || settlement.result === "PENDING") continue;
        const source = issued.get(settlement.position_id);
        if (!source) continue;
        const position = source.position;
        const evidence = settlement.settlement_evidence || {};
        const actual = evidence.official_value ?? evidence.official_total ??
          (evidence.covered_margin == null ? "—" : `${evidence.covered_margin > 0 ? "+" : ""}${evidence.covered_margin} vs spread`);
        settled.set(settlement.position_id, {
          id: settlement.position_id,
          date: source.date,
          game: position.game_id || "—",
          matchup: position.matchup || position.game_name || position.game_id || "—",
          market: position.market,
          pick: position.display_selection || position.selection,
          tier: position.rating_tier || "—",
          result: ({ W: "W", L: "L", WIN: "W", LOSS: "L", PUSH: "P" })[settlement.result] || settlement.result,
          resultFull: ({ W: "WIN", L: "LOSS" })[settlement.result] || settlement.result,
        });
      }
    }
    const rows = Array.from(settled.values());
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

    const tracked = overall.positions_tracked || overall.tracked_n || (ow+ol+op);
    const today = new Intl.DateTimeFormat("en-US",{timeZone:"America/New_York", weekday:"long", month:"long", day:"numeric", year:"numeric"}).format(new Date()).toUpperCase();

    let html = "";
    // MLB-identical SEASON RECORD + banner (Overall = TOTAL APEX fused)
    html += `<div class="section-head"><div class="title">SEASON RECORD</div><div class="meta mono">${esc(today)} · ${Number(tracked).toLocaleString("en-US")} POSITIONS TRACKED</div></div>`;
    html += `<div class="banner" data-apex-season-record="${esc(fmtRecord(ow,ol,op))}" data-apex-season-win-rate="${esc(owr)}" data-apex-ats-record="${esc(atsBanner)}" data-apex-totals-record="${esc(totBanner)}">
      <div class="cell"><div class="label">Overall</div><div class="val mono">${esc(fmtRecord(ow,ol,op))}</div></div>
      <div class="cell"><div class="label">Win Rate</div><div class="val mono">${esc(owr)}</div></div>
      <div class="cell"><div class="label">NFL ATS</div><div class="val mono">${esc(atsBanner)}</div></div>
      <div class="cell"><div class="label">NFL Totals</div><div class="val mono">${esc(totBanner)}</div></div>
    </div>`;
    html += ``;

    // AS-ISSUED TIER PERFORMANCE — ATS | TOTALS side by side like MLB
    html += `<div class="section-head"><div class="title">AS-ISSUED TIER PERFORMANCE</div><div class="meta mono">NFL FULL-GAME · AS ISSUED</div></div>`;
    html += `<div class="tier-grid">
      <div class="tier-col"><div class="tier-sub">ATS BY CONFIDENCE TIER</div>${table(["Tier","Record","Win Rate"], byTier("ATS"))}</div>
      <div class="tier-col"><div class="tier-sub">TOTALS BY CONFIDENCE TIER</div>${table(["Tier","Record","Win Rate"], byTier("TOTALS"))}</div>
    </div>`;
    // PROPS tier as third optional single like combined
    html += `<div class="tier-sub">PROPS BY CONFIDENCE TIER</div><div class="tier-single">${table(["Tier","Record","Win Rate"], byTier("PROPS"))}</div>`;
    html += `<div class="tier-sub">COMBINED NFL BY CONFIDENCE TIER</div><div class="tier-single">${table(["Tier","Record","Win Rate"], byTier(null))}</div>`;

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
      html += table(["Game","Matchup","Market","Pick","Tier","Result"], details);
    }
    root.innerHTML = html;
  }
  load().catch(err => {
    root.innerHTML = `<p class="muted">Results temporarily unavailable.</p>`;
    console.error(err);
  });
})();
