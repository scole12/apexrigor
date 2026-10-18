// Approved NCAA results layout (owner, 2026-10-18). Changing this file or the reference requires Scott's explicit request.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const {createHash} = require("node:crypto");
const base = path.join(__dirname, "..");
const reference = JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures/ncaaf_results_layout.reference.json"), "utf8"));
const source = fs.readFileSync(path.join(base, "ncaaf/results/render.js"), "utf8");
for (const [file, expected] of [["render.js", reference.render_js_sha256], ["index.html", reference.index_html_sha256]]) {
  assert.equal(createHash("sha256").update(fs.readFileSync(path.join(base, "ncaaf/results", file))).digest("hex"), expected, `${file} must match the approved layout`);
}
const occurrences = (text, value) => text.split(value).length - 1;
for (const section of reference.required_sections) assert.equal(occurrences(source, section), 1, section);
for (const text of reference.forbidden_strings) assert.equal(occurrences(source, text), 0, text);
const record = (W, L) => ({W, L, PUSH:0, VOID:0, PENDING:0});
const tiers = ["WEAK", "MODERATE", "STRONG", "ELITE"];
const groups = () => Object.fromEntries(tiers.map((tier, i) => [tier, record(i + 1, 1)]));
const fixture = {
  season_record:record(2, 2), ats_record:record(1, 1), totals_record:record(1, 1),
  ats_by_tier:groups(), totals_by_tier:groups(), combined_by_tier:groups(),
  latest_graded_date:"2026-10-17",
  positions:tiers.map((tier, i) => ({
    game_id:`NCAAF_TEST_${i}`, matchup:`Away ${i} at Home ${i}`,
    slate_date:i < 2 ? "2026-10-16" : "2026-10-17",
    market:i % 2 ? "TOTALS" : "ATS", pick:`Test pick ${i}`,
    as_issued_tier:tier, result:i < 2 ? "W" : "L"
  }))
};
(async () => {
  const root = {innerHTML:""};
  const fetched = [];
  const errors = [];
  vm.runInNewContext(source, {
    document:{getElementById:id => {assert.equal(id, "results-root"); return root;}},
    fetch:async url => {
      fetched.push(url);
      assert.equal(url, "/data/ncaaf_results_cumulative.json");
      return {ok:true, json:async () => fixture};
    },
    console:{error:error => errors.push(error)}, Intl, Date, Map, Set
  });
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(errors, []);
  assert.deepEqual(fetched, ["/data/ncaaf_results_cumulative.json"]);
  const html = root.innerHTML;
  for (const title of ["ATS BY CONFIDENCE TIER", "TOTALS BY CONFIDENCE TIER", "COMBINED NCAAF BY CONFIDENCE TIER", ...reference.required_sections]) {
    assert.equal(occurrences(html, title), 1, title);
  }
  const tables = [...html.matchAll(/<table\b[^>]*>([\s\S]*?)<\/table>/g)].map(match => match[1]);
  assert.equal(tables.length, 6, "three tier tables, daily archive, two slate details");
  const headers = table => [...table.matchAll(/<th>(.*?)<\/th>/g)].map(match => match[1]);
  for (const table of tables.slice(0, 3)) {
    assert.deepEqual(headers(table), reference.tier_table_headers);
    const rows = [...table.matchAll(/<tr><td class="mono">(.*?)<\/td>/g)].map(match => match[1]);
    assert.deepEqual(rows, ["Weak", "Moderate", "Strong", "Elite"]);
  }
  assert.deepEqual(headers(tables[3]), ["Date", "Record", "Win Rate", "Summary"]);
  assert.equal(occurrences(tables[3], '<td class="mono">October '), 2);
  assert.equal(occurrences(html, "SLATE DETAIL —"), 2);
  for (const table of tables.slice(4)) assert.deepEqual(headers(table), reference.slate_detail_headers);
  for (let i = 0; i < 4; i++) assert.equal(occurrences(html, `Test pick ${i}`), 1);
  console.log("PASS: approved NCAA results hashes, sections, three cumulative tier tables, daily archive and four positions across two slate details.");
})().catch(error => {console.error(error); process.exitCode = 1;});
