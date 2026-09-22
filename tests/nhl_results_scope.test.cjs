const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const source = fs.readFileSync(path.join(__dirname, "../nhl/results/render.js"), "utf8");

async function render(archive) {
  const root = {dataset:{}, innerHTML:""};
  const fetched = [];
  vm.runInNewContext(source, {
    document:{getElementById:()=>root},
    fetch:async url=>{
      fetched.push(url);
      assert.equal(url, "/data/nhl_results_archive.json", "NHL must not read another results authority");
      return {ok:true,json:async()=>archive};
    },
    console:{error:()=>{}}, Intl, Date, Map, Set
  });
  await new Promise(resolve=>setImmediate(resolve));
  assert.deepEqual(fetched, ["/data/nhl_results_archive.json"]);
  return root;
}
function position(id, market="TOTALS") {
  return {position_id:id,sport:"NHL",game_id:"NHL_TEST_"+id,
    market,line:market==="TOTALS"?6.5:1.5,is_underdog:market!=="TOTALS",
    selection:market==="TOTALS"?"OVER":"AWAY",tier:"MODERATE"};
}
function settlement(id,result) {
  return {position_id:id,game_id:"NHL_TEST_"+id,result,
    settlement_evidence:{source:"UNIT_TEST_OFFICIAL_RESULT"}};
}
(async()=>{
  let root=await render({sport:"NHL",status:"UNISSUED",issuances:[],grades:[]});
  assert.equal(root.dataset.status,"UNISSUED");
  assert.match(root.innerHTML,/data-apex-season-record="0-0"/);
  assert.match(root.innerHTML,/0 NHL POSITIONS TRACKED/);
  assert.match(root.innerHTML,/data-apex-season-win-rate="—"/);
  const card={sport:"NHL",status:"ISSUED",
    issuances:[{sport:"NHL",game_date:"2026-10-10",
      positions:[position("w"),position("l","DOG_PLUS_1_5"),position("p"),position("v"),position("pending")]}],
    grades:[{grade_id:"g1",sport:"NHL",settlements:[
      settlement("w","W"),settlement("l","L"),settlement("p","P"),settlement("v","V")]}]};
  root=await render(card);
  assert.equal(root.dataset.status,"ISSUED");
  assert.match(root.innerHTML,/data-apex-season-record="1-1-1P"/);
  assert.match(root.innerHTML,/data-apex-season-win-rate="50.0%"/);
  assert.match(root.innerHTML,/5 NHL POSITIONS TRACKED/);
  assert.match(root.innerHTML,/data-apex-totals-record="1-0-1P"/);
  assert.match(root.innerHTML,/data-apex-underdog-record="0-1"/);
  const corrected={sport:"NHL",status:"ISSUED",
    issuances:[{game_date:"2026-10-10",positions:[position("one")]}],
    grades:[{grade_id:"old",settlements:[settlement("one","W")]},
      {grade_id:"new",supersedes_grade_id:"old",settlements:[settlement("one","L")]}]};
  root=await render(corrected);
  assert.match(root.innerHTML,/data-apex-season-record="0-1"/);
  const wrongSport=JSON.parse(JSON.stringify(card));
  wrongSport.issuances[0].positions[0].sport="NFL";
  assert.equal((await render(wrongSport)).dataset.status,"UNAVAILABLE");
  const unverifiedDog=JSON.parse(JSON.stringify(card));
  unverifiedDog.issuances[0].positions[1].is_underdog=false;
  assert.equal((await render(unverifiedDog)).dataset.status,"UNAVAILABLE");
  console.log("PASS: NHL-only results; zero state; wins/losses/pushes/voids/pending; grade correction; sport and dog evidence rejection.");
})().catch(error=>{console.error(error);process.exitCode=1;});
