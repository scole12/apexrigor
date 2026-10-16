# APEX agent operating practice
Effective: 2026-10-16 (America/New_York)
Version: 2026-10-16.1
Owner: Scott Coleman
Canonical source: https://github.com/scole12/apex2-nba/blob/main/docs/AGENT_OPERATING_STANDARD.md

## Authority and scope
This is the sole current agent operating practice for APEX quantitative forecasting, sports PRISMA research, APEX 1.0, APEX 2.0 and their actively maintained cloud systems. All earlier agent operating practices, fixed role assignments, blanket tool bans, voting/debate loops and dated task orders are obsolete. Delete superseded active instructions; do not keep competing practice documents or fallback copies. Git history and research evidence are historical records, not operating instructions.
Direct current instructions from Scott and platform security requirements still apply. Sport specifications, data contracts and settlement rules remain requirements, not alternative agent workflows. Keep APEX 1.0 and APEX 2.0, and each sport's data, code, secrets and experiments isolated.

## 1. One accountable lead
Scott gives the outcome once. One lead owns the task list, delegation, reconciliation, acceptance evidence and final report. Scott is not a messenger between tools. The lead does not treat its own judgment as independent verification. Use existing queues and records; do not build extra orchestration without a demonstrated need.
Grokbot / Grok Bot is restricted to School Street Studios work and Scott's personal-life work. It has no lead, worker, reviewer, import or acceptance role in this scope. Do not route APEX source packets, credentials, findings or tasks through it.

## 2. One primary executor per task; named tool stack
The eligible stack is Codex CLI (GPT-6.1 Sol), Claude Code (Opus 5.5), Cursor CLI (Composer 2.5), and Grok Build CLI (Grok 4.7). Grok Build CLI is distinct from Grokbot. These identifiers are the owner's chosen baseline; verify installed availability and authentication before use, record exact requested/reported IDs and CLI versions, and do not silently substitute models.
Start with Codex as the operational default. Claude Code is a candidate for difficult implementation and synthesis once authenticated; Cursor for bounded checkable implementation; Grok Build for bounded document/codebase investigation or evidence-backed objections. These are provisional assignments, not universal rankings or validated screening performance.
Assign the tool that succeeds on the relevant local task. Benchmark rank alone does not establish reviewer strength, paper-screening accuracy or forecasting advantage. Use fresh bounded sessions and task packets; a reviewer does not see the writer's reasoning transcript.

## 3. Checkable assignments and bounded execution
Before execution, record a task ID, outcome, input snapshot/commit and hashes, executor, permitted files and shared dependencies, output path, budget, model/version/effort, acceptance checks and rollback where relevant.
Use short independently checkable stages. Record attempts, start/end time, exit status, usage where available, failures and exact check output. One initial attempt plus at most two retries; then unresolved with the missing evidence stated. A substantive revision starts a newly identified task, never hides earlier failures.
A malformed output, absent result, unverified quote, failed test or missing check stays unresolved. Exit code zero, valid JSON and an agent saying done are insufficient.
Start with one active job per tool; shared resource and account caps can require fewer. Honor actual rate-limit responses and measure useful completed output, errors, latency and usage before increasing concurrency. Do not add watchdogs or automatic restart loops as part of this practice.

## 4. Independent review and arbitration
Consequential code, published claims, research decisions and production changes receive independent verification appropriate to the task.
A reviewer allowed to propose an implementation replacement must be at least as capable as the writer on the relevant task. Establish that with relevant local evidence; when capability is weaker or unknown, the reviewer is advisory and read-only: it flags a specific defect and never rewrites accepted work. This is an adopted operating rule, not a universal theorem established by one study.
The primary executor applies substantiated minimal fixes. Every fix reruns the relevant tests; acceptance after integration reruns integration checks. Track fixes and regressions. Never weaken tests to manufacture a pass. A fresh session of the same model may review code; different providers may review documents. Neither arrangement proves error independence.
Start with one independent reviewer. Add a second when consequence, uncertainty or unresolved evidence warrants it; two is the default cap. Do not repeatedly pressure a reviewer in the same session to find more issues.
For research screening, independent readers receive the same frozen source and criteria, submit sealed first decisions and cannot see peer decisions or reference labels. Code reviewers receive requirements, code and diff, but not the writer's reasoning transcript.
Accept objections only against a source passage, reproducible failure or predeclared requirement. Verify agreements too. Do not accept by equal vendor voting, consensus or open-ended debate. If source checks and tests cannot resolve a consequential dispute, give Scott the competing positions, evidence and precise decision needed.

## 5. One record, isolated edits, serial integration
Use one authoritative task/result record per project with one authorized import writer. Workers emit proposals to their own output paths; validated imports are idempotent. Keep official human adjudications distinct from model proposals.
Every parallel code job declares its files before starting, with no overlap. Tightly linked files, shared schemas and interfaces belong to one job or run sequentially. Each code writer has its own branch and worktree. Separate checkouts do not prevent semantic conflicts.
Merge one job at a time. Run checks on the combined state after each merge. Use least-privilege controls actually supported by the installed platform; prove write/read boundaries where required. Prompt rules or separate folders are not security boundaries.
Commit durable changes and validation to GitHub. Use the project's existing PR/CI and deployment route and respect configured branch protections. This instruction migration is owner-authorized. Future authorization follows the task's scope; do not repeatedly ask Scott for routine reversible work already authorized. Engine promotion and unresolved consequential choices require Scott's decision.
Production work needs actual behavior readback for the affected service/site/data, with available receipts when delivery is in scope. Do not send new emails just to verify a documentation change. Keep secrets out of outputs and commits. Never use an LLM as the authority for schedules, prices, results or settlement.
After each accepted stage, save goal, commit, changed files, checks and results, unresolved items and exact next step. A new session must continue from this checkpoint without reconstructing the chat.

## 6. Local measurement before expansion
Begin with one small complete real task. Compare executor-alone against executor-plus-review on representative held-out tasks. Measure missed defects, false objections, regressions, accepted results, elapsed time and usage.
Add tools, reviewers or parallelism only when measured gains justify them. Keep instruction files short and actionable, with non-obvious commands and boundaries. Review generated instructions before adopting them. No tool setup, access boundary or accuracy claim is proven merely because it is documented.

## 7. APEX research: three separate decisions
1. Eligibility: does the paper meet the frozen review criteria? Log source, criteria version, decision and source passage. For title/abstract screening, either reader's include/uncertain advances; invalid or missing decisions stay unresolved. Proposed exclusions remain subject to source checks and the predeclared human audit/adjudication protocol.
2. Evidential support: does the study support the exact claim? Record design, population, comparator, result, uncertainty, limitations and applicability. Separate peer-reviewed evidence, preprints, vendor claims and unverified leads. Do not promote a search snippet or another agent's summary to source verification.
3. Forecasting improvement: does implementing the claim improve the specified engine on protected data? Register all attempts in the sport's single testing authority. Use chronological evaluation, identical-timestamp market comparators, proper probability/distribution scores, dependence-aware uncertainty, multiplicity handling, negative controls and independent regeneration. Sealed prospective confirmation and Scott's approval precede engine promotion.
Passing one decision does not pass the next. Operational success, paper inclusion and theoretical novelty do not establish predictive edge.
Freeze the validation population, criteria, prompts/configuration, analysis, stopping rule and acceptance threshold before scoring. Keep development and confirmation sets separate; do not repeatedly inspect a sealed set. PRISMA counts must reconcile from the authoritative record; never count an unscreened record as screened.
Validate screening against independently established human reference labels. Report eligible denominators, exact uncertainty, misses including shared misses, workload, failures and per-subject limits. If retaining the prior 95% recall / one-sided 95% lower-bound target, 59 eligible papers with zero misses reaches that binomial threshold under its assumptions; adaptive sampling or repeated testing requires an appropriate design. Do not claim a universal sample-size guarantee.
Use fixed source-based adjudication and predeclared exclusion-pool audits. Official disputed decisions and human reference labels remain human-owned; the authorized controller imports approved records without fabricating judgments.

## 8. Migration and limits
The Oct 16 practice replaces agent-process instructions only. Preserve source evidence, append-only facts, experiment records, completed work and project-specific requirements. Do not rewrite historical results or reclassify decisions merely to fit new tool roles.
Remove active old role/loop documents and point tool entry files to this practice. A copy in another repository/environment must match this version exactly; use its hash to check drift. A change requires a reason and coordinated updates.
No production model, timer, grading logic, DNS, access credential or user access is changed by adopting this practice. Audit cloud-hosted agent instructions separately from infrastructure configuration. Only report environments actually inspected and updated.
Scientific basis: the six supplied Oct 16 evidence notes inform this practice; their numerical and vendor claims have not all been independently reverified here. Specific operational defaults are adopted engineering decisions, not proof that this exact stack is optimal.
