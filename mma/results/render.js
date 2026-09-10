(() => {
  "use strict";
  const root = document.getElementById("results-root");
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const fmtRecord = (w,l,p=0) => `${Number(w).toLocaleString("en-US")}-${Number(l).toLocaleString("en-US")}${p?`-${p}P`:""}`;
  const table = (headers, rows) => `<table class="results"><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map((c)=>`<td class="mono">${esc(c)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;

  async function load() {
    const [sumRes, archRes] = await Promise.all([
      fetch("/data/apex_results_summary.json", {cache:"no-store"}),
      fetch("/data/mma_results_archive.json", {cache:"no-store"}),
    ]);
    if (!sumRes.ok) throw new Error("summary HTTP "+sumRes.status);
    if (!archRes.ok) throw new Error("archive HTTP "+archRes.status);
    const summary = await sumRes.json();
    const archive = await archRes.json();
    const overall = summary.overall || {};
    const ow = overall.wins|0 || summary.overall_wins|0;
    const ol = overall.losses|0 || summary.overall_losses|0;
    const op = overall.pushes|0 || summary.overall_pushes|0;
    const owr = overall.win_rate_display || summary.overall_win_rate_display || (ow+ol?`${(100*ow/(ow+ol)).toFixed(1)}%`:"—");
    const tracked = overall.positions_tracked || overall.tracked_n || summary.positions_graded || (ow+ol+op);

    // H2H WINNER-only settlements (exclude longshot/4-market)
    const rows = [];
    for (const ev of archive.events || []) {
      const date = ev.event_date || (ev.event && ev.event.event_date) || "—";
      const eventName = ev.event_name || (ev.event && (ev.event.display_name || ev.event.name)) || "—";
      for (const r of ev.latest_results || []) {
        const market = String(r.market || "").toUpperCase();
        if (market && market !== "WINNER") continue;
        const result = ({W:"W", L:"L", WIN:"W", LOSS:"L", PUSH:"P", P:"P"})[r.result] || r.result;
        if (!result || result === "PENDING") continue;
        rows.push({
          date,
          event: eventName,
          bout: r.bout_id || "—",
          matchup: r.matchup || r.bout_name || r.selection || "—",
          market: "WINNER",
          pick: r.selection || "—",
          tier: r.rating_tier || r.tier || "—",
          result,
        });
      }
    }
    const w = rows.filter(r => r.result === "W").length;
    const l = rows.filter(r => r.result === "L").length;
    const p = rows.filter(r => r.result === "P").length;
    const winnerBanner = `${w}-${l}${p?`-${p}P`:""}`;
    const winnerRate = (w+l)?`${(100*w/(w+l)).toFixed(1)}%`:"—";

    const byTier = () => ["WEAK","MODERATE","STRONG","ELITE"].map(tier => {
      const sel = rows.filter(r => String(r.tier).toUpperCase() === tier);
      const tw = sel.filter(r => r.result === "W").length;
      const tl = sel.filter(r => r.result === "L").length;
      const tp = sel.filter(r => r.result === "P").length;
      const d = tw+tl;
      return [tier[0]+tier.slice(1).toLowerCase(), `${tw}-${tl}${tp?`-${tp}P`:""}`, d?`${(100*tw/d).toFixed(1)}%`:"—"];
    });

    const today = new Intl.DateTimeFormat("en-US",{timeZone:"America/New_York", weekday:"long", month:"long", day:"numeric", year:"numeric"}).format(new Date()).toUpperCase();
    let html = "";
    html += `<div class="section-head"><div class="title">SEASON RECORD</div><div class="meta mono">${esc(today)} · ${Number(tracked).toLocaleString("en-US")} POSITIONS TRACKED</div></div>`;
    html += `<div class="banner" data-apex-season-record="${esc(fmtRecord(ow,ol,op))}" data-apex-season-win-rate="${esc(owr)}" data-apex-winner-record="${esc(winnerBanner)}">
      <div class="cell"><div class="label">Overall</div><div class="val mono">${esc(fmtRecord(ow,ol,op))}</div></div>
      <div class="cell"><div class="label">Win Rate</div><div class="val mono">${esc(owr)}</div></div>
      <div class="cell"><div class="label">MMA Winner</div><div class="val mono">${esc(winnerBanner)}</div></div>
      <div class="cell"><div class="label">Win Rate (H2H)</div><div class="val mono">${esc(winnerRate)}</div></div>
    </div>`;

    html += `<div class="section-head"><div class="title">AS-ISSUED TIER PERFORMANCE</div><div class="meta mono">MMA WINNER · AS ISSUED · H2H ONLY</div></div>`;
    html += `<div class="tier-sub">WINNER BY CONFIDENCE TIER</div><div class="tier-single">${table(["Tier","Record","Win Rate"], byTier())}</div>`;

    const days = new Map();
    for (const row of rows) {
      if (!days.has(row.date)) days.set(row.date, []);
      days.get(row.date).push(row);
    }
    const sortedDays = Array.from(days).sort(([a],[b]) => String(b).localeCompare(String(a)));
    const dailyRows = sortedDays.map(([date, selected]) => {
      const dw = selected.filter(r => r.result === "W").length;
      const dl = selected.filter(r => r.result === "L").length;
      const dp = selected.filter(r => r.result === "P").length;
      const d = dw+dl;
      return [date, `${dw}W-${dl}L${dp?`-${dp}P`:""}`, d?`${(100*dw/d).toFixed(1)}%`:"—", `MMA ${dw}-${dl}`];
    });
    html += `<div class="section-head"><div class="title">DAILY ARCHIVE</div></div>`;
    html += table(["Date","Record","Win Rate","Summary"], dailyRows);

    for (const [date, selected] of sortedDays) {
      const details = selected.map((row, idx) => [`F${String(idx+1).padStart(2,"0")}`, row.matchup, row.market, row.pick, row.tier, row.result]);
      html += `<div class="section-head"><div class="title">SLATE DETAIL — ${esc(date)}</div><div class="meta mono">${selected.length} POSITIONS</div></div>`;
      html += table(["Bout","Matchup","Market","Pick","Tier","Result"], details);
    }
    if (!rows.length) html += `<div class="empty-state">MMA RESULTS BEGIN WITH THE FIRST GRADED APEX UFC CARD.</div>`;
    root.innerHTML = html;
  }
  load().catch(err => {
    root.innerHTML = `<p class="muted">Results temporarily unavailable.</p>`;
    console.error(err);
  });
})();
