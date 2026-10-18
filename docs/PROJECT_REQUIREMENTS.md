# apexrigor project requirements
Agent workflow is governed solely by AGENT_OPERATING_STANDARD.md.
- Work only in this project's declared scope; no cross-sport or APEX 1.0/2.0 code, data or credential contamination.
- Preserve source contracts, official results, issued positions, settlement rules and existing tests. Never fabricate data or substitute zeros for missing facts.
- Use the existing build/test/deployment commands after verifying they exist at the target commit. Preserve scheduled operations and delivery contracts.
- Report win-loss record and win percentage; no betting units or stake sizing. No moneyline modeling or output.
- Never print secrets or change Scott's access. No extra timers, schedulers or databases for this instruction migration.
- The public results and picks pages keep their approved presentation. Data, ratings and grading work never changes page layout, sections, tables or columns. A layout change needs Scott's explicit written request for that page; the approved NCAA results layout is `tests/fixtures/ncaaf_results_layout.reference.json` and its check in `tests/ncaaf_results_layout.test.cjs`, which agents do not edit or replace without that request.
