(() => {
  "use strict";
  const root = document.getElementById("results-root");
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const emptyRecord = () => ({W:0, L:0, PUSH:0, VOID:0, PENDING:0});
  const record = r => `${r.W}-${r.L}-${r.PUSH}P`;
  const rate = r => r.W + r.L ? `${(100 * r.W / (r.W + r.L)).toFixed(1)}%` : "—";
  const dateLabel = value => new Intl.DateTimeFormat("en-US", {timeZone:"UTC", year:"numeric", month:"long", day:"numeric"}).format(new Date(`${value}T00:00:00Z`));
  const table = (headers, rows) => `<table class="results"><thead><tr>${headers.map(h => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.map(row => `<tr>${row.map(cell => `<td class="mono">${esc(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  const section = (title, meta = "") => `<div class="section-head"><div class="title">${esc(title)}</div><div class="meta mono">${esc(meta)}</div></div>`;
  const tierTable = groups => table(["Tier", "Record", "Win Rate"], ["WEAK", "MODERATE", "STRONG", "ELITE"].map(tier => {
    const r = groups?.[tier] || emptyRecord();
    return [tier[0] + tier.slice(1).toLowerCase(), record(r), rate(r)];
  }));
  async function fetchJSON(path) {
    const response = await fetch(path, {cache:"no-store"});
    if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
    return response.json();
  }

  async function load() {
    const [apex, ncaaf] = await Promise.all([
      fetchJSON("/data/apex_results_summary.json"),
      fetchJSON("/data/ncaaf_results_cumulative.json"),
    ]);
    for (const key of ["wins", "losses", "pushes"]) {
      const value = apex[`overall_${key}`];
      if (!Number.isSafeInteger(value) || value < 0 || apex.overall?.[key] !== value) {
        throw new Error(`Invalid fused overall ${key}`);
      }
    }
    const overall = {W:apex.overall_wins, L:apex.overall_losses, PUSH:apex.overall_pushes};
    const overallLabel = `${overall.W.toLocaleString("en-US")}-${overall.L.toLocaleString("en-US")}-${overall.PUSH}P`;
    const overallRate = apex.overall_win_rate_display || rate(overall);
    const ats = ncaaf.ats_record || emptyRecord();
    const totals = ncaaf.totals_record || emptyRecord();
    const through = apex.latest_graded_date ? `THROUGH ${dateLabel(apex.latest_graded_date).toUpperCase()}` : "";
    let html = section("SEASON RECORD", `${through} · ${Number((apex.overall&&apex.overall.positions_tracked)||apex.positions_graded||0).toLocaleString("en-US")} POSITIONS TRACKED`);
    html += `<div class="banner" data-apex-season-record="${esc(overallLabel)}" data-apex-season-win-rate="${esc(overallRate)}" data-apex-ats-record="${esc(record(ats))}" data-apex-totals-record="${esc(record(totals))}">
      <div class="cell"><div class="label">Overall</div><div class="val mono">${esc(overallLabel)}</div></div>
      <div class="cell"><div class="label">Win Rate</div><div class="val mono">${esc(overallRate)}</div></div>
      <div class="cell"><div class="label">NCAAF ATS</div><div class="val mono">${esc(record(ats))}</div></div>
      <div class="cell"><div class="label">NCAAF Totals</div><div class="val mono">${esc(record(totals))}</div></div>
    </div>`;
    html += section("AS-ISSUED TIER PERFORMANCE", "NCAAF FULL-GAME · AS ISSUED");
    html += `<div class="tier-grid"><div class="tier-col"><div class="tier-sub">ATS BY CONFIDENCE TIER</div>${tierTable(ncaaf.ats_by_tier)}</div><div class="tier-col"><div class="tier-sub">TOTALS BY CONFIDENCE TIER</div>${tierTable(ncaaf.totals_by_tier)}</div></div>`;
    html += `<div class="tier-sub">COMBINED NCAAF BY CONFIDENCE TIER</div><div class="tier-single">${tierTable(ncaaf.combined_by_tier)}</div>`;

    const days = new Map();
    for (const row of ncaaf.positions || []) {
      if (!days.has(row.slate_date)) days.set(row.slate_date, []);
      days.get(row.slate_date).push(row);
    }
    const count = rows => rows.reduce((r, row) => {
      if (Object.hasOwn(r, row.result)) r[row.result]++;
      return r;
    }, emptyRecord());
    const sortedDays = Array.from(days).sort(([a], [b]) => b.localeCompare(a));
    html += section("DAILY ARCHIVE");
    html += table(["Date", "Record", "Win Rate", "Summary"], sortedDays.map(([date, rows]) => {
      const all = count(rows);
      return [dateLabel(date), record(all), rate(all), `ATS ${record(count(rows.filter(r => r.market === "ATS")))} · TOTALS ${record(count(rows.filter(r => r.market === "TOTALS")))} · ${rows.length} POSITIONS`];
    }));
    for (const [date, rows] of sortedDays) {
      html += section(`SLATE DETAIL — ${dateLabel(date).toUpperCase()}`, `${rows.length} POSITIONS`);
      html += table(["Game", "Matchup", "Market", "Pick", "Tier", "Result"], rows.map(r => [String(r.game_id).slice(-6), r.matchup, r.market === "TOTALS" ? "TOTAL" : r.market, r.pick, r.as_issued_tier, r.result]));
    }
    if (!sortedDays.length) html += `<div class="empty-state">NCAA RESULTS BEGIN WITH THE FIRST GRADED APEX NCAA SLATE.</div>`;
    root.innerHTML = html;
  }
  load().catch(error => {
    root.innerHTML = `<div class="empty-state">RESULTS DATA UNAVAILABLE</div>`;
    console.error(error);
  });
})();
