(() => {
  "use strict";
  const root = document.getElementById("results-root");
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const markets = {ATS: "ATS", TOTALS: "TOTALS"};
  const results = {W:"WIN", L:"LOSS", P:"PUSH", V:"VOID", WIN:"WIN", LOSS:"LOSS", PUSH:"PUSH", VOID:"VOID", PENDING:"PENDING"};
  const tiers = ["UNVERIFIED"];
  const fmtRecord = (w, l, p = 0) => `${w.toLocaleString("en-US")}-${l.toLocaleString("en-US")}${p ? `-${p}P` : ""}`;
  const rate = (w, l) => w + l ? `${(100 * w / (w + l)).toFixed(1)}%` : "—";
  const record = rows => {
    const w = rows.filter(row => row.result === "WIN").length;
    const l = rows.filter(row => row.result === "LOSS").length;
    const p = rows.filter(row => row.result === "PUSH").length;
    return {w, l, p, label: fmtRecord(w, l, p), rate: rate(w, l)};
  };
  const table = (headers, rows, scroll = false) => `${scroll ? '<div class="results-scroll" tabindex="0" role="region" aria-label="Slate detail">' : ""}<table class="results"><thead><tr>${headers.map(h => `<th scope="col">${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.map(row => `<tr>${row.map(value => `<td class="mono">${esc(value)}</td>`).join("")}</tr>`).join("")}</tbody></table>${scroll ? "</div>" : ""}`;
  function archiveRows(archive) {
    if (archive.sport !== "NBA" || !Array.isArray(archive.slates)) throw new Error("NBA archive unavailable");
    const issued = new Map();
    for (const slate of archive.slates) {
      if (!Array.isArray(slate.positions) || !/^\d{4}-\d{2}-\d{2}$/.test(slate.slate_date)) throw new Error("Invalid slate");
      for (const position of slate.positions) {
        if ((position.sport ?? "NBA") !== "NBA" || /^(NFL|MLB|NCAAF|MMA|NHL)_/i.test(position.game_id ?? "")) throw new Error("Non-NBA archive row");
        if ([position.engine, position.engine_version].some(value => String(value ?? "").startsWith("baseline:"))) throw new Error("Baseline archive row");
        if (!position.position_id || issued.has(position.position_id)) throw new Error("Duplicate or missing position");
        if (!["ATS", "TOTALS"].includes(position.market)) throw new Error("Unsupported NBA market");
        const result = position.result == null ? "PENDING" : (Object.hasOwn(results, position.result) ? results[position.result] : null);
        if (!result) throw new Error("Invalid NBA grade");
        issued.set(position.position_id, {
          id: position.position_id, date: slate.slate_date, game: position.game_id || "—",
          matchup: position.matchup || position.game_id || "—", market: position.market,
          pick: position.selection || "UNAVAILABLE", tier: "UNVERIFIED", result
        });
      }
    }
    return Array.from(issued.values());
  }
  async function load() {
    const response = await fetch("/data/nba_results_archive.json", {cache:"no-store"});
    if (!response.ok) throw new Error("NBA results data unavailable");
    const archive = await response.json();
    const rows = archiveRows(archive);
    const overall = record(rows);
    const total = record(rows.filter(row => row.market === "TOTALS"));
    const ats = record(rows.filter(row => row.market === "ATS"));
    const tracked = rows.length;
    const today = new Intl.DateTimeFormat("en-US", {timeZone:"America/New_York", weekday:"long", month:"long", day:"numeric", year:"numeric"}).format(new Date()).toUpperCase();
    const overallRecord = overall.label;
    const overallRate = overall.rate;
    let output = `<div class="section-head"><div class="title">NBA RECORD</div><div class="meta mono">${esc(today)} · ${Number(tracked).toLocaleString("en-US")} NBA POSITIONS TRACKED</div></div>`;
    output += `<div class="banner" data-apex-season-record="${esc(overallRecord)}" data-apex-season-win-rate="${esc(overallRate)}" data-apex-totals-record="${esc(total.label)}" data-apex-ats-record="${esc(ats.label)}">
      <div class="cell"><div class="label">NBA Overall</div><div class="val mono">${esc(overallRecord)}</div></div>
      <div class="cell"><div class="label">Win Rate</div><div class="val mono">${esc(overallRate)}</div></div>
      <div class="cell"><div class="label">TOTALS</div><div class="val mono">${esc(total.label)}</div></div>
      <div class="cell"><div class="label">ATS</div><div class="val mono">${esc(ats.label)}</div></div>
    </div>`;
    const byTier = market => tiers.map(tier => {
      const rec = record(rows.filter(row => row.tier === tier && (!market || row.market === market)));
      return [tier[0] + tier.slice(1).toLowerCase(), rec.label, rec.rate];
    });
    output += `<div class="section-head"><div class="title">AS-ISSUED TIER PERFORMANCE - UNVERIFIED</div><div class="meta mono">NBA FULL-GAME · ${rows.length ? "AS ISSUED" : "UNISSUED"}</div></div>`;
    output += `<div class="tier-grid">
      <div class="tier-col"><div class="tier-sub">TOTALS BY TIER VERIFICATION STATUS</div>${table(["Tier", "Record", "Win Rate"], byTier("TOTALS"))}</div>
      <div class="tier-col"><div class="tier-sub">ATS BY TIER VERIFICATION STATUS</div>${table(["Tier", "Record", "Win Rate"], byTier("ATS"))}</div>
    </div>`;
    output += `<div class="tier-sub">COMBINED NBA BY TIER VERIFICATION STATUS</div><div class="tier-single">${table(["Tier", "Record", "Win Rate"], byTier(null))}</div>`;
    const days = new Map();
    for (const row of rows) {
      if (!days.has(row.date)) days.set(row.date, []);
      days.get(row.date).push(row);
    }
    // A day appears in the results only once it has graded results (an issued card waiting for its games is not a 0-0 day).
    const sortedDays = Array.from(days).filter(([, selected]) => selected.some(row => row.result !== "PENDING")).sort(([a], [b]) => b.localeCompare(a));
    const daily = sortedDays.map(([day, selected]) => {
      const rec = record(selected);
      return [day, rec.label, rec.rate, `NBA ${rec.label}`];
    });
    output += `<div class="section-head"><div class="title">DAILY ARCHIVE</div></div>${table(["Date", "Record", "Win Rate", "Summary"], daily)}`;
    if (!rows.length) {
      output += `<p class="unissued-note mono">UNISSUED — No NBA picks have been issued.</p>`;
      output += `<div class="section-head"><div class="title">SLATE DETAIL</div><div class="meta mono">0 POSITIONS</div></div>${table(["Game", "Matchup", "Market", "Pick", "Tier", "Result"], [], true)}`;
    }
    for (const [day, selected] of sortedDays) {
      const details = selected.slice().sort((a, b) => `${a.game}|${a.market}|${a.id}`.localeCompare(`${b.game}|${b.market}|${b.id}`))
        .map(row => [row.game, row.matchup, markets[row.market], row.pick, row.tier, ({WIN:"W", LOSS:"L", PUSH:"P", VOID:"V"})[row.result] || row.result]);
      output += `<div class="section-head"><div class="title">SLATE DETAIL — ${esc(day)}</div><div class="meta mono">${selected.length} POSITIONS</div></div>${table(["Game", "Matchup", "Market", "Pick", "Tier", "Result"], details, true)}`;
    }
    root.innerHTML = output;
    root.dataset.status = rows.length ? "ISSUED" : "UNISSUED";
  }
  load().catch(error => {
    root.dataset.status = "UNAVAILABLE";
    root.innerHTML = '<p class="muted" role="status">Results temporarily unavailable.</p>';
    console.error(error);
  });
})();
