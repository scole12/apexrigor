#!/usr/bin/env python3
"""Build the APEX MMA scientific-boundary page."""

from _mma_public import close, head, hero, navigation, write


def main() -> int:
    html = head("APEX — About MMA", "The factual, scientific, and production boundaries of APEX MMA.", "/mma/about")
    html += "\n" + hero() + "\n" + navigation("ABOUT")
    html += """
  <main class="about-page"><div class="about-container">
    <header class="about-section about-intro"><h1 class="about-section-title">The MMA Operation</h1><p class="about-lede">APEX MMA separates source-backed facts, scientific testing, market observations, frozen inference, issuance, and grading.</p><p class="about-copy">No MMA pick is public until one coherent winner, method, and duration distribution survives a chronological scientific court and is sealed into a deterministic release.</p></header>
    <hr class="about-divider" aria-hidden="true">
    <section class="about-section about-module"><h2 class="about-section-title">Factual authority</h2><p class="about-copy">Fighter identity, bouts, results, weigh-ins, scorecards, rules, and provenance remain factual. Model-derived ratings, features, probabilities, and scores never enter that authority.</p></section>
    <section class="about-section about-module"><h2 class="about-section-title">Two outputs, one distribution</h2><p class="about-copy">The future Winner / Method and Duration / Time engines must be exact marginals of the same normalized terminal fight distribution. A sportsbook total is derived only when an authentic line exists.</p></section>
    <section class="about-section about-module"><h2 class="about-section-title">Current gate</h2><p class="about-copy">The technical pipeline is implemented, but the historical court remains blocked by the absence of a licensed, temporally defensible elemental round-stat universe. APEX reports that limitation instead of fitting on an inadequate commission tranche or inventing missing statistics.</p></section>
    <section class="about-section about-module"><h2 class="about-section-title">Operations</h2><p class="about-copy">T-3 hydrates readiness three hours before the earliest published bout. T-2 locks two hours before that bout and can run only a sealed release. The grader runs at 07:00 America/New_York and is a clean no-op without an issuance.</p></section>
  </div></main>""" + close()
    path = write("mma/about/index.html", html)
    print(f"MMA_ABOUT_PATH={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
