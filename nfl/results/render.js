(() => {
  "use strict";

  const root = document.getElementById("results-root");
  const esc = value => String(value ?? "").replace(/[&<>"']/g, character => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[character]);
  const record = rows => {
    const wins = rows.filter(row => row.result === "WIN").length;
    const losses = rows.filter(row => row.result === "LOSS").length;
    const pushes = rows.filter(row => row.result === "PUSH").length;
    return {
      label: `${wins}-${losses}${pushes ? `-${pushes}P` : ""}`,
      rate: wins + losses ? `${(100 * wins / (wins + losses)).toFixed(1)}%` : "—"
    };
  };
  const table = (headers, rows) => `<div class="nfl-results-scroll"><table class="results"><thead><tr>${headers.map(header => `<th scope="col">${esc(header)}</th>`).join("")}</tr></thead><tbody>${rows.map(row => `<tr>${row.map((cell, index) => `<td data-label="${esc(headers[index])}">${esc(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  const section = (title, body) => `<section class="nfl-results-section"><div class="section-head"><div class="title">${esc(title)}</div></div>${body}</section>`;
  const signed = value => value == null ? "—" : `${value > 0 ? "+" : ""}${value}`;
  const issuedDate = issuance => {
    if (issuance.game_date) return issuance.game_date;
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit"
    }).formatToParts(new Date(issuance.issued_at));
    const values = Object.fromEntries(parts.map(part => [part.type, part.value]));
    return `${values.year}-${values.month}-${values.day}`;
  };

  async function render() {
    const response = await fetch("/data/nfl_results_archive.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`NFL results HTTP ${response.status}`);
    const archive = await response.json();
    const issued = new Map();
    for (const issuance of archive.issuances || []) {
      for (const position of issuance.positions || []) {
        issued.set(position.position_id, { position, date: issuedDate(issuance) });
      }
    }
    const replaced = new Set((archive.grades || []).map(grade => grade.supersedes_grade_id).filter(Boolean));
    const settled = new Map();
    for (const grade of archive.grades || []) {
      if (replaced.has(grade.grade_id)) continue;
      for (const settlement of grade.settlements || []) {
        if (!settlement.result || settlement.result === "PENDING") continue;
        const source = issued.get(settlement.position_id);
        if (!source) throw new Error("NFL result has no published pick");
        const position = source.position;
        const evidence = settlement.settlement_evidence || {};
        const actual = evidence.official_value ?? evidence.official_total ??
          (evidence.covered_margin == null ? "—" : `${signed(evidence.covered_margin)} vs spread`);
        settled.set(settlement.position_id, {
          id: settlement.position_id,
          date: source.date,
          game: position.game_id,
          market: position.market,
          pick: position.display_selection || position.selection,
          price: settlement.issued_american_price ?? position.american_price,
          probability: settlement.issued_probability ?? position.issued_probability,
          tier: position.rating_tier || "—",
          result: ({ W: "WIN", L: "LOSS" })[settlement.result] || settlement.result,
          actual
        });
      }
    }
    const rows = Array.from(settled.values());
    const season = record(rows);
    const days = new Map();
    for (const row of rows) {
      if (!days.has(row.date)) days.set(row.date, []);
      days.get(row.date).push(row);
    }
    const sortedDays = Array.from(days).sort(([left], [right]) => right.localeCompare(left));
    const metrics = [["Record", season.label], ["Win Rate", season.rate], ["Graded", rows.length]];
    let body = `<div class="nfl-results-metrics">${metrics.map(([label, value]) => `<div><span>${label}</span><strong class="mono">${esc(value)}</strong></div>`).join("")}</div>`;
    body += `<p class="nfl-results-note">${issued.size} issued · ${rows.length} graded · ${issued.size - rows.length} pending. Results use the selections, FanDuel prices and APEX probabilities published before kickoff.</p>`;
    const tiers = ["WEAK", "MODERATE", "STRONG", "ELITE"].map(tier => {
      const selected = rows.filter(row => row.tier === tier);
      const counts = record(selected);
      return [tier, counts.label, counts.rate, selected.length];
    });
    body += section("PERFORMANCE BY RATING", table(["As-issued rating", "Record", "Win Rate", "Graded"], tiers));
    const daily = sortedDays.map(([date, selected]) => {
      const counts = record(selected);
      return [date, counts.label, counts.rate, selected.length];
    });
    body += section("DAILY ARCHIVE", table(["Slate date (ET)", "Record", "Win Rate", "Graded"], daily));
    for (const [date, selected] of sortedDays) {
      const details = selected.slice().sort((left, right) =>
        `${left.game}|${left.market}|${left.id}`.localeCompare(`${right.game}|${right.market}|${right.id}`)
      ).map(row => [row.pick, signed(row.price), row.probability == null ? "—" : `${(100 * row.probability).toFixed(1)}%`, row.tier, row.actual, row.result]);
      body += section(`SLATE DETAIL — ${date}`, table(["As-issued pick", "FanDuel", "APEX", "Rating", "Actual", "Result"], details));
    }
    if (!rows.length) body += '<p class="nfl-results-note">No graded picks yet.</p>';
    root.innerHTML = body;
    root.dataset.loaded = "true";
  }

  render().catch(error => {
    root.innerHTML = '<p class="nfl-results-note">Results are temporarily unavailable.</p>';
    console.error(error);
  });
})();
