// Approved NCAA results layout (owner, 2026-10-18). Changing this file or the reference requires Scott's explicit request.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const os = require("node:os");
const {execFileSync} = require("node:child_process");
const {createHash} = require("node:crypto");
const base = path.join(__dirname, "..");
const reference = JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures/ncaaf_results_layout.reference.json"), "utf8"));
const source = fs.readFileSync(path.join(base, "ncaaf/results/render.js"), "utf8");
const normalizeIndex = html => html.replace(/(<aside class="apex-site-record"[\s\S]*?<\/aside>)/, aside => aside.replace(/<strong class="mono">[^<]*<\/strong>/g, '<strong class="mono">#</strong>'));
const checkLayout = directory => {
  const indexHtml = fs.readFileSync(path.join(directory, "index.html"), "utf8");
  assert.equal(createHash("sha256").update(fs.readFileSync(path.join(directory, "render.js"))).digest("hex"), reference.render_js_sha256, "render.js must match the approved layout");
  assert.equal(createHash("sha256").update(normalizeIndex(indexHtml)).digest("hex"), reference.index_html_normalized_sha256, "index.html must match the approved layout after lifetime-record normalization");
};
const resultsDirectory = path.join(base, "ncaaf/results");
checkLayout(resultsDirectory);
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), "ncaaf-results-layout-"));
try {
  const indexHtml = fs.readFileSync(path.join(resultsDirectory, "index.html"), "utf8");
  let replacements = 0;
  const changedIndex = indexHtml.replace(/(<aside class="apex-site-record"[\s\S]*?<\/aside>)/, aside => aside.replace(/<strong class="mono">[^<]*<\/strong>/g, () => `<strong class="mono">${replacements++ === 0 ? "9,999-9,999-99P" : "99.9%"}</strong>`));
  assert.equal(replacements, 2, "both lifetime-record values must be changed for the self-check");
  fs.copyFileSync(path.join(resultsDirectory, "render.js"), path.join(temporary, "render.js"));
  fs.writeFileSync(path.join(temporary, "index.html"), changedIndex);
  checkLayout(temporary);
  console.log("PASS: lifetime-record mutation 9,999-9,999-99P / 99.9% still passes layout checks.");
  // Actions uses a shallow checkout; obtain the fixed historical object if absent.
  const historicalCommit = "82a4653956291b30b0bbf72ca24239a8aa358481";
  try {
    execFileSync("git", ["cat-file", "-e", `${historicalCommit}^{commit}`], {cwd:base, stdio:"pipe"});
  } catch {
    execFileSync("git", ["fetch", "--depth=1", "origin", historicalCommit], {cwd:base, stdio:"pipe"});
  }
  for (const file of ["render.js", "index.html"]) {
    fs.writeFileSync(path.join(temporary, file), execFileSync("git", ["show", `${historicalCommit}:ncaaf/results/${file}`], {cwd:base}));
    // Keep the other file current so each historical regression is rejected independently.
    assert.throws(() => checkLayout(temporary), {code:"ERR_ASSERTION"}, `${file} from Oct 17 must fail`);
    fs.copyFileSync(path.join(resultsDirectory, file), path.join(temporary, file));
  }
  console.log("PASS: Oct 17 render.js and index.html each fail layout checks (assert.throws).");
} finally {
  fs.rmSync(temporary, {recursive:true, force:true});
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
