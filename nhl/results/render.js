(() => {
  "use strict";
  const root = document.getElementById("results-root");
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const markets = {TOTALS: "Totals O/U", DOG_PLUS_1_5: "Underdog +1.5"};
  const results = {W:"WIN", L:"LOSS", P:"PUSH", V:"VOID", WIN:"WIN", LOSS:"LOSS", PUSH:"PUSH", VOID:"VOID", PENDING:"PENDING"};
  const tiers = ["WEAK", "MODERATE", "STRONG", "ELITE"];
  const fmtRecord = (w, l, p = 0) => `${w.toLocaleString("en-US")}-${l.toLocaleString("en-US")}${p ? `-${p}P` : ""}`;
  const rate = (w, l) => w + l ? `${(100 * w / (w + l)).toFixed(1)}%` : "—";
  const record = rows => {
    const w = rows.filter(row => row.result === "WIN").length;
    const l = rows.filter(row => row.result === "LOSS").length;
    const p = rows.filter(row => row.result === "PUSH").length;
    return {w, l, p, label: fmtRecord(w, l, p), rate: rate(w, l)};
  };
  const table = (headers, rows, scroll = false) => `${scroll ? '<div class="results-scroll" tabindex="0" role="region" aria-label="Slate detail">' : ""}<table class="results"><thead><tr>${headers.map(h => `<th scope="col">${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.map(row => `<tr>${row.map(value => `<td class="mono">${esc(value)}</td>`).join("")}</tr>`).join("")}</tbody></table>${scroll ? "</div>" : ""}`;
  const requireNHL = value => {
    if ((value.sport ?? "NHL") !== "NHL" || /^(NFL|MLB|NCAAF|MMA|NBA)_/i.test(value.game_id ?? "")) throw new Error("Non-NHL archive row");
  };
  const marketFor = position => {
    const market = position.market || position.engine;
    if (market === "TOTALS") return market;
    if (["ATS", "GOAL_LINE", "PUCK_LINE", "DOG_PLUS_1_5"].includes(market) &&
        (position.line ?? position.market_line) === 1.5 &&
        (position.is_underdog === true || position.side_role === "UNDERDOG")) return "DOG_PLUS_1_5";
    throw new Error("Unsupported NHL market or missing underdog +1.5 evidence");
  };
  function validateSummary(summary) {
    const overall = summary.overall;
    const included = summary.sports_included;
    if (!overall || !summary.sports?.nhl || !Array.isArray(included) || !included.length || new Set(included).size !== included.length) throw new Error("Fused Overall unavailable");
    for (const field of ["wins", "losses", "pushes"]) {
      if (!Number.isInteger(overall[field]) || overall[field] < 0) throw new Error("Fused Overall invalid");
      const values = included.map(sport => summary.sports[sport]?.[field]);
      if (values.some(value => !Number.isInteger(value) || value < 0) || values.reduce((a, b) => a + b, 0) !== overall[field]) throw new Error("Fused Overall mismatch");
    }
    if (!included.includes("nhl") && ["wins", "losses", "pushes"].some(field => summary.sports.nhl[field])) throw new Error("NHL missing from fused Overall");
    return overall;
  }
  function archiveRows(archive) {
    if (archive.sport !== "NHL" || !Array.isArray(archive.issuances) || !Array.isArray(archive.grades)) throw new Error("NHL archive unavailable");
    const issued = new Map();
    for (const issuance of archive.issuances) {
      requireNHL(issuance);
      if (!Array.isArray(issuance.positions) || !/^\d{4}-\d{2}-\d{2}$/.test(issuance.game_date)) throw new Error("Invalid issuance");
      for (const position of issuance.positions) {
        requireNHL(position);
        if (!position.position_id || issued.has(position.position_id)) throw new Error("Duplicate or missing position");
        issued.set(position.position_id, {
          id: position.position_id, date: issuance.game_date, game: position.game_id || "—",
          matchup: position.matchup || position.game_name || position.game_id || "—",
          market: marketFor(position), pick: position.display_selection || position.selection || "UNAVAILABLE",
          tier: position.rating_tier || position.tier || "UNAVAILABLE", result: "PENDING"
        });
      }
    }
    if (archive.status === "UNISSUED" && (issued.size || archive.grades.length)) throw new Error("Invalid UNISSUED archive");
    const ids = new Set(archive.grades.map(grade => grade.grade_id));
    if (ids.has(undefined) || ids.has(null) || ids.has("") || ids.size !== archive.grades.length) throw new Error("Invalid grade identities");
    const replaced = new Set();
    const ancestry = new Map();
    for (const grade of archive.grades) {
      requireNHL(grade);
      if (grade.supersedes_grade_id) {
        if (!ids.has(grade.supersedes_grade_id) || replaced.has(grade.supersedes_grade_id)) throw new Error("Ambiguous grade replacement");
        replaced.add(grade.supersedes_grade_id);
        ancestry.set(grade.grade_id, grade.supersedes_grade_id);
      }
    }
    for (let identity of ancestry.keys()) {
      const seen = new Set();
      while (ancestry.has(identity)) {
        if (seen.has(identity)) throw new Error("Cyclic grade replacement");
        seen.add(identity); identity = ancestry.get(identity);
      }
    }
    const settled = new Set();
    for (const grade of archive.grades) {
      if (replaced.has(grade.grade_id)) continue;
      if (!Array.isArray(grade.settlements)) throw new Error("Missing settlements");
      for (const settlement of grade.settlements) {
        requireNHL(settlement);
        const source = issued.get(settlement.position_id);
        if (!source || settled.has(settlement.position_id) || !Object.hasOwn(results, settlement.result)) throw new Error("Unbound or invalid settlement");
        if (settlement.game_id && settlement.game_id !== source.game) throw new Error("Settlement game mismatch");
        if (["WIN", "LOSS", "PUSH"].includes(results[settlement.result]) && !Object.keys(settlement.settlement_evidence || {}).length) throw new Error("Missing settlement evidence");
        source.result = results[settlement.result];
        settled.add(settlement.position_id);
      }
    }
    return Array.from(issued.values());
  }
  async function load() {
    const responses = await Promise.all([
      fetch("/data/apex_results_summary.json", {cache:"no-store"}),
      fetch("/data/nhl_results_archive.json", {cache:"no-store"})
    ]);
    if (responses.some(response => !response.ok)) throw new Error("Results data unavailable");
    const [summary, archive] = await Promise.all(responses.map(response => response.json()));
    const overall = validateSummary(summary);
    const rows = archiveRows(archive);
    const total = record(rows.filter(row => row.market === "TOTALS"));
    const dog = record(rows.filter(row => row.market === "DOG_PLUS_1_5"));
    const tracked = overall.positions_tracked ?? overall.wins + overall.losses + overall.pushes;
    const today = new Intl.DateTimeFormat("en-US", {timeZone:"America/New_York", weekday:"long", month:"long", day:"numeric", year:"numeric"}).format(new Date()).toUpperCase();
    const overallRecord = fmtRecord(overall.wins, overall.losses, overall.pushes);
    const overallRate = rate(overall.wins, overall.losses);
    let output = `<div class="section-head"><div class="title">SEASON RECORD</div><div class="meta mono">${esc(today)} · ${Number(tracked).toLocaleString("en-US")} POSITIONS TRACKED</div></div>`;
    output += `<div class="banner" data-apex-season-record="${esc(overallRecord)}" data-apex-season-win-rate="${esc(overallRate)}" data-apex-totals-record="${esc(total.label)}" data-apex-underdog-record="${esc(dog.label)}">
      <div class="cell"><div class="label">Overall</div><div class="val mono">${esc(overallRecord)}</div></div>
      <div class="cell"><div class="label">Win Rate</div><div class="val mono">${esc(overallRate)}</div></div>
      <div class="cell"><div class="label">Totals O/U</div><div class="val mono">${esc(total.label)}</div></div>
      <div class="cell"><div class="label">Underdog +1.5</div><div class="val mono">${esc(dog.label)}</div></div>
    </div>`;
    const byTier = market => tiers.map(tier => {
      const rec = record(rows.filter(row => row.tier === tier && (!market || row.market === market)));
      return [tier[0] + tier.slice(1).toLowerCase(), rec.label, rec.rate];
    });
    output += `<div class="section-head"><div class="title">AS-ISSUED TIER PERFORMANCE</div><div class="meta mono">NHL FULL-GAME · ${rows.length ? "AS ISSUED" : "UNISSUED"}</div></div>`;
    output += `<div class="tier-grid">
      <div class="tier-col"><div class="tier-sub">TOTALS O/U BY CONFIDENCE TIER</div>${table(["Tier", "Record", "Win Rate"], byTier("TOTALS"))}</div>
      <div class="tier-col"><div class="tier-sub">UNDERDOG +1.5 BY CONFIDENCE TIER</div>${table(["Tier", "Record", "Win Rate"], byTier("DOG_PLUS_1_5"))}</div>
    </div>`;
    output += `<div class="tier-sub">COMBINED NHL BY CONFIDENCE TIER</div><div class="tier-single">${table(["Tier", "Record", "Win Rate"], byTier(null))}</div>`;
    const days = new Map();
    for (const row of rows) {
      if (!days.has(row.date)) days.set(row.date, []);
      days.get(row.date).push(row);
    }
    const sortedDays = Array.from(days).sort(([a], [b]) => b.localeCompare(a));
    const daily = sortedDays.map(([day, selected]) => {
      const rec = record(selected);
      return [day, rec.label, rec.rate, `NHL ${rec.label}`];
    });
    output += `<div class="section-head"><div class="title">DAILY ARCHIVE</div></div>${table(["Date", "Record", "Win Rate", "Summary"], daily)}`;
    if (!rows.length) {
      output += `<p class="unissued-note mono">UNISSUED — No NHL picks have been issued.</p>`;
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
