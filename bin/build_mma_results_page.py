#!/usr/bin/env python3
"""Build the append-only APEX MMA results page."""

from _mma_public import close, head, hero, navigation, write


SCRIPT = r"""
<script>
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
fetch("/data/mma_results_summary.json",{cache:"no-store"}).then(r=>{if(!r.ok)throw new Error(`HTTP ${r.status}`);return r.json()}).then(d=>{
 document.getElementById("results-meta").textContent=`${d.status.replaceAll("_"," ")} · GRADER ${d.grader.schedule}`;
 document.getElementById("results").innerHTML=d.issued_event_count?"<div class=\"meta mono\">Issued event results are available.</div>":`<article class="game-module"><header class="game-header"><div class="game-num mono">0</div><div class="game-meta"><h2 class="game-matchup">No MMA event has been issued or graded</h2><p class="meta mono">${esc(d.release_state)}</p></div></header><div class="market-grid"><div class="market-panel"><div class="market-label">GRADER</div><div class="pick-headline">Clean no-op</div><div class="rationale-copy"><p>The grader runs at 07:00 America/New_York and writes nothing when no lawful issuance is eligible.</p></div></div></div></article>`;
}).catch(e=>{document.getElementById("results-meta").textContent="MMA RESULTS DATA UNAVAILABLE";document.getElementById("results").textContent=e.message});
</script>
"""


def main() -> int:
    html = head("APEX — MMA Results", "Append-only APEX MMA issuance and grading results.", "/mma/results")
    html += "\n" + hero() + "\n" + navigation("RESULTS")
    html += """
  <div class="section-head"><div class="title">MMA RESULTS</div><div class="meta mono" id="results-meta">LOADING GRADER STATE</div></div>
  <main class="picks-page"><div class="picks-board" id="results" aria-live="polite"></div></main>""" + SCRIPT + close()
    path = write("mma/results/index.html", html)
    print(f"MMA_RESULTS_PATH={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
