# APEX agent standard — effective October 20, 2026

This is the only prevailing agent operating practice. Scott Coleman approved it on October 20, 2026. It supersedes all earlier practices forever, including the October 16, 2026 operating standard, every older role assignment, tool ban, voting or debate loop, and dated task order. Do not follow those documents. Git history is a record, not an instruction.

## The practice

1. Scott gives the job to Consigliere (Grok Build coordinator). Consigliere opens a GitHub issue that defines "done". All work communication is on GitHub.
2. Claude Code (Opus 5.5) and Codex (GPT-6 Astra) each build on their own branch.
3. Each builder writes tests for the other's branch, never for its own.
4. GitHub Actions runs all tests on both branches. A failing branch is out.
5. Consigliere picks the passing branch. On a tie, pick the branch with more tests passing, then the branch with fewer lines changed.
6. Two independent reviews follow: a fresh Claude Code session, and Grok Build (Grok 4.7).
7. Every finding comes with a failing test.
8. Scott approves anything that goes live. A Vercel deploy of the site is allowed after his approval. Then merge.

Cursor (Composer 2.5) is a third builder and helper. Cursor never reviews.

Supabase changes are tested on a copy.

Never restyle the site.

Domain constraints in `docs/PROJECT_REQUIREMENTS.md` still apply. They do not reinstate any earlier agent workflow.

## How tools load this standard

This file is the auto-read project instruction for the tools that enter the repository:

- Codex, Cursor, GitHub Copilot, and Grok Build read `AGENTS.md`.
- Claude Code reads `CLAUDE.md`, which contains `@AGENTS.md`.
- Cursor also always applies `.cursor/rules/agent-standard.mdc`.

Grok Build's documented auto-read project instruction filename is `AGENTS.md`. In each directory it also reads `Agents.md`, `AGENT.md`, `CLAUDE.md`, `Claude.md`, and `CLAUDE.local.md`, plus `*.md` rules under `.grok/rules/` (and `.cursor/rules/` and `.claude/rules/` for compatibility). Checked on October 20, 2026 against the Grok Build project-rules page: https://docs.x.ai/build/features/project-rules. No separate Grok instruction filename is required, so none was added.

## Verified sources

The links below are the sources marked verified in the October 20, 2026 APEX tool benchmark compilation (pages or papers fetched and read, or vendor pages). They identify the named tools and the evidence behind cross-built tests, a fresh review, and a failing test for every finding. They are not a second practice.

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
- CodePulse benchmark (2026-08-21; compilation read this via a search snippet, and the board is run by a competitor): https://codepulse.review/benchmark

### Fresh review and failing tests

- Stephens, "Fresh Eyes Beat a Second Family" (October 2026; fresh-session review, and findings must come with a failing test): https://stephens.page
- Xiang et al., arXiv 2607.21656: https://arxiv.org/abs/2607.21656
- Song, arXiv 2610.01471: https://arxiv.org/abs/2610.01471

## Job 3 CI rule (Scott, Oct 20 2026)
- Build and test on the Geekom. GitHub is for communication only.
- Do not push work-in-progress branches. CI runs only on the final pull request into `main` (or by hand via workflow_dispatch).
- Before opening a pull request, post your full local test output to the GitHub issue as proof.
- Exactly one check is required on the final pull request. Scott approves before anything merges or goes live.
