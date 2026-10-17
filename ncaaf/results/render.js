(() => {
  "use strict";
  const root = document.getElementById("results-root");
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const emptyRecord = () => ({W:0, L:0, PUSH:0, VOID:0, PENDING:0});
  const record = r => `${r.W}-${r.L}-${r.PUSH}P`;
  const rate = r => r.W + r.L ? `${(100 * r.W / (r.W + r.L)).toFixed(1)}%` : "—";
  const dateLabel = value => new Intl.DateTimeFormat("en-US", {timeZone:"UTC", year:"numeric", month:"long", day:"numeric"}).format(new Date(`${value}T00:00:00Z`));
  const table = (headers, rows) => `<table class="results"><thead><tr>${headers.map(h => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.map(row => `<tr>${row.map((cell, index) => `<td class="mono" data-label="${esc(headers[index])}">${esc(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  const section = (title, meta = "") => `<div class="section-head"><div class="title">${esc(title)}</div><div class="meta mono">${esc(meta)}</div></div>`;
  const tierTable = groups => table(["Tier", "Record", "Win Rate", "Pending", "Void"], ["WEAK", "MODERATE", "STRONG", "ELITE"].map(tier => {
    const r = groups?.[tier] || emptyRecord();
    return [tier[0] + tier.slice(1).toLowerCase(), record(r), rate(r), r.PENDING, r.VOID];
  }));
  function ratingIdentity(row) {
    const hash = row.tier_policy_sha256;
    if (!hash) return {key:"unknown", label:"Historical ratings — definition not recorded", hash:null};
    const label = row.rating_version || row.rating_policy_id || "Recorded rating definition";
    return {key:JSON.stringify([hash, label]), label, hash};
  }
  async function fetchJSON(path) {
    const response = await fetch(path, {cache:"no-store"});
    if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
    return response.json();
  }

  async function load() {
    const ncaaf = await fetchJSON("/data/ncaaf_results_cumulative.json");
    const overall = ncaaf.season_record || emptyRecord();
    const overallLabel = `${overall.W.toLocaleString("en-US")}-${overall.L.toLocaleString("en-US")}-${overall.PUSH}P`;
    const overallRate = rate(overall);
    const ats = ncaaf.ats_record || emptyRecord();
    const totals = ncaaf.totals_record || emptyRecord();
    const through = ncaaf.latest_graded_date ? `THROUGH ${dateLabel(ncaaf.latest_graded_date).toUpperCase()}` : "";
    let html = section("SEASON RECORD", `${through} · ${(ncaaf.positions || []).length.toLocaleString("en-US")} POSITIONS TRACKED`);
    html += `<div class="banner banner-3" data-apex-season-record="${esc(overallLabel)}" data-apex-season-win-rate="${esc(overallRate)}" data-apex-ats-record="${esc(record(ats))}" data-apex-totals-record="${esc(record(totals))}">
      <div class="cell"><div class="label">NCAAF Overall</div><div class="val mono">${esc(overallLabel)}</div></div>
      <div class="cell"><div class="label">Win Rate</div><div class="val mono">${esc(overallRate)}</div></div>
      <div class="cell"><div class="label">NCAAF ATS</div><div class="val mono">${esc(record(ats))}</div></div>
      <div class="cell"><div class="label">ATS Win Rate</div><div class="val mono">${esc(rate(ats))}</div></div>
      <div class="cell"><div class="label">NCAAF Totals</div><div class="val mono">${esc(record(totals))}</div></div>
      <div class="cell"><div class="label">Totals Win Rate</div><div class="val mono">${esc(rate(totals))}</div></div>
    </div>`;
    html += section("TIER PERFORMANCE BY RATING VERSION", "NCAAF FULL-GAME · RECORDED PUBLIC RATINGS");
    html += `<p class="muted">Relative confidence tiers rank picks within each engine’s slate. Historical rating definitions are shown separately. Original issuance ratings and any recorded public revision remain identifiable below.</p>`;
    const versions = new Map();
    for (const row of ncaaf.positions || []) {
      if (row.daily_record_eligible === false || !Object.hasOwn(emptyRecord(), row.result)) continue;
      const identity = ratingIdentity(row);
      if (!versions.has(identity.key)) versions.set(identity.key, {identity, rows:[]});
      versions.get(identity.key).rows.push(row);
    }
    for (const {identity, rows} of versions.values()) {
      const byTier = selected => selected.reduce((groups, row) => {
        const tier = row.tier || row.as_issued_tier;
        if (!["WEAK", "MODERATE", "STRONG", "ELITE"].includes(tier)) return groups;
        groups[tier] ||= emptyRecord();
        groups[tier][row.result]++;
        return groups;
      }, {});
      html += section(identity.label, identity.hash ? `POLICY ${identity.hash}` : "POLICY IDENTITY NOT INCLUDED IN SOURCE RECORD");
      html += `<div class="tier-grid"><div class="tier-col"><div class="tier-sub">ATS BY CONFIDENCE TIER</div>${tierTable(byTier(rows.filter(r => r.market === "ATS")))}</div><div class="tier-col"><div class="tier-sub">TOTALS BY CONFIDENCE TIER</div>${tierTable(byTier(rows.filter(r => r.market === "TOTALS")))}</div></div>`;
      html += `<div class="tier-sub">COMBINED NCAAF BY CONFIDENCE TIER</div><div class="tier-single">${tierTable(byTier(rows))}</div>`;
    }

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
      html += table(["Game", "Matchup", "Market", "Pick", "Public Tier", "Original Tier", "Rating Version", "Result"], rows.map(r => [String(r.game_id).slice(-6), r.matchup, r.market === "TOTALS" ? "TOTAL" : r.market, r.pick, r.tier || r.as_issued_tier, r.original_tier || r.as_issued_tier, ratingIdentity(r).label, r.result]));
    }
    if (!sortedDays.length) html += `<div class="empty-state">NCAA RESULTS BEGIN WITH THE FIRST GRADED APEX NCAA SLATE.</div>`;
    root.innerHTML = html;
  }
  load().catch(error => {
    root.innerHTML = `<div class="empty-state">RESULTS DATA UNAVAILABLE</div>`;
    console.error(error);
  });
})();
