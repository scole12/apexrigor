# APEX agent standard — effective October 21, 2026

This is Scott's only working practice. Scott Coleman approved it on October 21, 2026. It replaces the October 20, 2026 practice (Consigliere or Grok Bot as coordinator, Codex as builder, three competing builders, Astra). It supersedes all earlier practices. Do not follow older documents. Git history is a record, not an instruction.

Codex is out until October 27, 2026 6:30 AM ET and only comes back if Scott says so.

## The practice

1. Scott gives the job to Claude (coordinator in Scott's chat). Claude opens a GitHub issue that defines "done". All work communication is on GitHub.
2. Each job has one builder: Claude Code (Opus 5.5) or Cursor (Composer 2.5). Not two builders racing on the same job.
3. The other builder is the tester: Cursor writes tests for Claude Code's branch; Grok Build writes tests for Cursor's branch. A builder never writes tests for its own branch.
4. Tests must fail on the old code and pass on the fix. Run the full suite, `ruff check`, and `ruff format --check`. GitHub Actions runs the same checks on the branch.
5. Grok Build (Grok 4.7) reviews every branch that passes tests. A fresh Claude Code session also reviews college football work, email sending, and the shared publisher. Every review finding comes with a failing test.
6. Before build: back up with a one-line rollback note on the issue.
7. Scott approves anything that goes live. The apexrigor.com site may go live on Vercel only after his OK. Then merge one pull request titled or described with `Closes #N`.
8. Post proof from the next real run on the issue (email message ID, log line, or site page).

**Builder split:** Claude Code builds college football, the shared publisher, and graders. Cursor builds MLB, cleanup, and smaller jobs. Cursor never reviews. Grok Build never builds; it tests Cursor's work and reviews.

Supabase changes are tested on a copy, never the live database.

Never restyle the site.

Soccer is not touched.

Domain constraints in `docs/PROJECT_REQUIREMENTS.md` still apply. They do not reinstate any earlier agent workflow.

## Usage limits

- One job per tool at a time.
- Cap Claude Code headless runs with `--max-turns` between 40 and 60.
- The coordinator writes one brief per job and reads one result file per job. No polling every minute.
- Log every job's tool, model, minutes, and cost to `C:\Users\scliu\apex_jobs\usage_log.csv` on the Geekom.
- If a tool shows a usage warning, give it no new work until Scott clears it.
- Cursor may run Opus 5.5 or Grok 4.7 on Cursor's own plan when Claude or Grok limits run low.

## Best practices by tool

Vendor pages cited under Verified sources below.

### Claude Code (Opus 5.5)

- Reads `CLAUDE.md`, which imports this file via `@AGENTS.md`.
- Headless: `claude -p` with `--max-turns` and `--output-format json` (Anthropic CLI docs).
- Run tests in the foreground during headless runs so output is visible.
- Use a fresh session for review, not the build session.

### Cursor (Composer 2.5)

- Always applies `.cursor/rules/*.mdc` (Cursor project rules docs).
- Headless: `cursor-agent -p --trust` with `--model composer-2.5`.
- Use `--force` only inside that job's own work folder.
- On the Geekom, the bare command `agent` is Grok, not Cursor. Use `cursor-agent` for Cursor.

### Grok Build (Grok 4.7)

- Reads `AGENTS.md` and any `*.md` under `.grok/rules/` (Grok Build project-rules docs).
- Headless: `grok -p` with `-m grok-4.7`.
- Reviewer and cross-builder tester only; does not build product code.
- `grok inspect` shows which rules loaded.

## GitHub

- Issues define done; comments carry evidence and proof.
- One builder branch per job; the tester pushes tests to that workflow.
- GitHub Actions must pass before review and before Scott's OK.
- One merge PR per closed job with `Closes #N`.

## Supabase

- Schema and data changes are tried on a copy of the database first.
- Never point agents at production Supabase for experiments.

## Vercel

- Hosts the public apexrigor.com site after Scott approves the change.
- Follow the repo's existing build and publish scripts; do not invent new hosting steps.

## Droplet

- College football, NFL, MLB, NHL, MMA, and the shared publisher run on the droplet. Those systems are fixed and tested on the droplet itself.
- Job work folders live under `/opt/apex_work/<job>/` and are removed when the job closes.
- Do not touch `/opt/apex_site` or other live paths except through the approved job flow.

## Geekom

- NBA runs in `C:\Users\scliu\apex2_prod`.
- Practice clones and job sandboxes use `C:\Users\scliu\apex_jobs\` (for example `practice-3tools\apexrigor`).
- Usage logging: `C:\Users\scliu\apex_jobs\usage_log.csv`.
- SSH to the droplet from the Geekom when the job needs it.

## Cloudflare

- Registrar, DNS, and Web Analytics for apexrigor.com stay on Cloudflare.
- After a site update Scott approved, purge CDN cache with the existing repo script when HTML changed.

## How tools load this standard

- Cursor and Grok Build read `AGENTS.md`. Cursor also always applies `.cursor/rules/agent-standard.mdc`.
- Claude Code reads `CLAUDE.md`, which contains `@AGENTS.md`.
- GitHub Copilot reads `.github/copilot-instructions.md` when present; keep it aligned with this file.

Grok Build also reads `Agents.md`, `AGENT.md`, `CLAUDE.md`, and rules under `.grok/rules/`, `.cursor/rules/`, and `.claude/rules/` for compatibility. See https://docs.x.ai/build/features/project-rules (checked October 20, 2026).

## Verified sources

The links below are the sources marked verified in the October 20, 2026 APEX tool benchmark compilation. They support cross-built tests, fresh review where required, and a failing test for every finding. They are not a second practice.

### Models named in this standard

- Claude Code / Opus 5.5: https://www.anthropic.com/claude-opus-5-5
- Cursor / Composer 2.5: https://cursor.com/composer
- Grok Build / Grok 4.7: https://x.ai/build and https://x.ai/news/grok-4-7

### Test writing

- TestSuiteBench (ETH Zurich/LogicStar, arXiv 2610.13065): https://arxiv.org/abs/2610.13065 and https://testsuitebench.com
- SWT-Bench: https://swtbench.com

### Code review

- Factory Review Benchmark (docs.factory.com, April 2026): https://docs.factory.com
- Kilo Code Reviewer test (2026-06-01): https://blog.kilo.ai/p/review-testing
- CodePulse benchmark (2026-08-21): https://codepulse.review/benchmark

### Fresh review and failing tests

- Stephens, "Fresh Eyes Beat a Second Family" (October 2026): https://stephens.page
- Xiang et al., arXiv 2607.21656: https://arxiv.org/abs/2607.21656
- Song, arXiv 2610.01471: https://arxiv.org/abs/2610.01471
