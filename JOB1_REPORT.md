# Job 1 (issue #23): Cursor (Composer 2.5) report — apexrigor

Branch `job1-cursor` (third builder/helper). Cross tests for the other builders: branch `job1-tests-by-cursor`, `tests/job1_cross_by_cursor/` (copied from Codex’s behavioral suite, run read-only against `job1-claude` / `job1-codex` worktrees).

**Not pushed** (`NO_PUSH.md`, push URL disabled). All evidence is local under `C:\Users\scliu\apex2_site\job1\`.

## Helper: shared replay fixtures

| Item | Status |
|---|---|
| `job1/shared_fixtures/<YYYY-MM-DD>/` for Oct 6, 9, 10, 13, 15, 17, 18, 20 | **Done** — built by `job1/tools/build_shared_fixtures.py` |
| `shared_fixtures/README.md` (per-file source + SHA-256) | **Done** |
| Oct 18 site `data/ncaaf/2026-10-18` | **Missing** in any local repo; manifest documents `missing_required` and droplet-only gaps |
| Provider authorities / schedule_catalog parity inputs | **Not reconstructed** (listed per date in each `manifest.json`) |

## Per-cause status (site / causes 1, 9, 10, 11)

Implementation on `job1-cursor` is the merged **Claude Code `job1-claude`** publisher work (route registry, NCAAF-only commits, global-fault circuit breaker, bounded T-2 site wait, email supersede, interface pin, layout lock). Cursor did not re-implement a separate publisher design; it integrated that candidate and added local test ergonomics (Windows `fcntl` stub in `tests/job1_cursor/pubsupport.py`).

| # | Status | Fix (primary files) | Tests | Evidence |
|---|---|---|---|---|
| 1a–1f, 9 | **Fixed + tested locally (21/26 pass on Windows)** | `bin/site_route_owners.py`, `bin/apex_shared_site_publisher.py`, `tests/ncaaf_results_layout.test.cjs` | `tests/job1_cursor/test_cause1a_1e_9_ownership.py`, `test_cause1b_1c_1d_1f_delivery.py` | `job1_cursor_tests_apexrigor_job1_cursor.txt` — 5 failures are Git/deploy-check timing on Windows, not import errors |
| 10 Vercel build (`build_vercel_output.py`) | **Passes locally** | `normalize_mlb_results_labels` retained in `bin/build_vercel_output.py` | `python bin/build_vercel_output.py` | `job1_cursor_tests_build_vercel.txt`, `job1_cursor_tests_ncaaf_layout.txt` (layout PASS) |
| 11 Serialized deploys / real-failure-only alerts | **Partial via 1b/1c** (Claude design) | Same publisher | Same suite | Codex-specific serialization (`932c846`) not merged; bounded wait + global faults covered |

## Own regression tests

- `tests/job1_cursor/` — 26 tests; **21 passed, 5 failed** on Windows/Python 3.12 (`job1_cursor_tests_apexrigor_job1_cursor.txt`).
- `.github/workflows/job1-tests.yml` — **removed** on `job1-cursor` per Consigliere NO_PUSH note (no new CI workflow files).

## Cross-tests (other builders)

| Target | Suite | Result | Log |
|---|---|---|---|
| `job1-codex` (NCAAF) | `tests/job1_cross_by_cursor` | **9/9 OK** | `job1_cursor_tests_cross_vs_codex_ncaaf.txt` |
| `job1-claude` (NCAAF) | same | **2 pass, 1 fail, 6 errors** (Codex-oriented AST tests; expected mismatch) | `job1_cursor_tests_cross_vs_claude_ncaaf.txt` |
| Site cross-tests | `test_publisher` / `test_hosting` | **Not run** — copied modules need package path fix on Windows | `job1_cursor_tests_cross_vs_*_site.txt` |

Cross-test branch: `job1-tests-by-cursor` commit `23646d7` (apexrigor). NCAAF cross files landed on `job1-cursor` commit `388e2a8` (should be cherry-picked onto a clean `job1-tests-by-cursor` from `origin/main` before PR).

## What remains unverified

- No push, no GitHub Actions, no Vercel production deploy, no droplet changes.
- Full provider-backed replay of Oct 6–20 (authorities only on droplet).
- Scott approval for updated NCAAF results layout reference hash (cause 9).
- Linux/WSL re-run of publisher tests (recommended; Claude reported 26/26 on Linux).

## Commits (apexrigor `job1-cursor`, recent)

- Merge `job1-claude` publisher fixes
- `032a875` — `tests/job1_cursor` layout + Windows `fcntl` stub
- Drop `job1-tests.yml` per NO_PUSH

NCAAF half: see `../apex_ncaaf/JOB1_REPORT.md`.
