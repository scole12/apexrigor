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

## Round 2 (Grok Build review fixes, Oct 20 2026)

Consigliere round 2 targeted the four product defects shared by all Job 1 branches. Local commits only (`NO_PUSH.md`); no pushes, no new CI workflows.

| Req | Fix | Commit(s) | Grok review test | Result |
|---|---|---|---|---|
| **1** Per-sport publish; remove all-sports gate | `build_request` for NCAAF returns only `owned_by("NCAAF", …)` paths; no `validate_site_build` / `foreign_paths` on NCAAF | apexrigor `3c7cb59` | `grokreview/apexrigor/review_tests/test_req1_ncaaf_must_not_check_other_sports.py` | **PASS** |
| **5** Off-slate catalog extra must not fail reverse parity | Drop extras whose kickoff is before the canonical slate floor (`canonical_slate_floor_ms`) instead of `SCHEDULE_CATALOG_REVERSE_PARITY_FAILED` | apex_ncaaf `fd44e39` | `grokreview/apex_ncaaf/review_tests/test_req5_canonical_slate_parity.py` | **PASS** |
| **6** Default deploy gate runs T-3 then T-2 | `tools/ncaaf_deploy_gate.py` always invokes `operations/replay_saturday.py --job1-shared-fixtures` (read-only `job1/shared_fixtures`); `FILE_MANIFEST` / `RELEASE.json` updated for `ncaaf_t3_living_write.py` | apex_ncaaf `fd44e39` | `grokreview/apex_ncaaf/review_tests/test_req6_deploy_gate_replay.py` (+ Codex addendum `test_req6_candidate_gate_replay.py` via `tools/check_job1_candidate.py`) | **PASS** |
| **11** One deploy per publish; alert only on production ERROR | `ncaaf_deployment_serves` requires exact commit match (no descendant); bounded wait calls `owner_notice` only when `readyState == ERROR` | apexrigor `3c7cb59` | `grokreview/apexrigor/review_tests/test_req11_deploy_queue.py` (3 tests) | **PASS** |

**Grok review suite (APEX_REVIEW_ROOT → cursor worktrees):** apexrigor **7/7** passed; apex_ncaaf **3/3** passed. Log: `job1_cursor_r2_tests_20261020_213429.txt`.

**Still passing from round 1:** Grok req 2–4, 7–10 and `test_no_new_ci_workflow` (no `job1-tests.yml`).

**Own suites (Windows, same log):** apex_ncaaf `tests/job1_cursor` **38/41** (reportlab import + `_atomic_json` `O_DIRECTORY` on Windows for two hydration tests). apexrigor `tests/job1_cursor` **19/26** — remaining failures are Windows `fcntl`/Git timing, Node layout hash vs restored reference (`d2be6f35…` in reference vs `af56dd1c…` from built page; needs Scott-approved lock or Linux re-run), and one flaky `deploy_check` clone test.

**WSL:** Publisher re-run requested in WSL; Geekom WSL lacks `python3-venv` / pytest (`job1_cursor_r2_tests_20261020_213429.txt` header). Install `python3.12-venv` and re-run there when available.

**Not done:** Full droplet authority replay; cross-site `job1_cross_by_cursor` on Windows; Scott approval if the live NCAAF results layout reference must change from origin/main’s `d2be6f35…` hash.

## Round 3 (Linux green, layout lock, Oct 20 2026)

**Linux evidence:** `C:\Users\scliu\apex2_site\job1\job1_cursor_r3_tests_20261020_220204.txt` (WSL + `uv` Python 3.12; `GIT_DIR`/`GIT_WORK_TREE` set for Windows git worktrees). Re-runner: `job1/tools/run_job1_cursor_r3_linux.sh`.

| Suite | Linux result |
|---|---|
| Grok review apexrigor (7) | **PASS** |
| Grok review apex_ncaaf (3) | **PASS** |
| apexrigor `tests/job1_cursor` (26) | **PASS** |
| apex_ncaaf `tests/job1_cursor` (41) | **PASS** (`uv --with reportlab --with duckdb`) |
| `python bin/build_vercel_output.py` + `node tests/ncaaf_results_layout.test.cjs` | **PASS** |
| Publisher `tests/test_publisher*.py` | **N/A** (no such files in either repo) |

### Per-failure (round 2 → round 3)

| Failure | Cause | Fix | Commit | Test / Linux |
|---|---|---|---|---|
| Layout hash `af56dd1c` vs approved `d2be6f35` | Round 2 repinned reference to Scott’s aside-only hash while the Node check also masked `sport-nav`; committed NCAAF pages had NBA nav baked in (other sports’ chrome). | Restore Oct 18 NCAAF HTML (`48451c3`); lock normalizes lifetime record only (selector applied at Vercel build). Reference left at `d2be6f35` (no repin). | `202711d` (files; message is accidental test-repo noise) | `tests/ncaaf_results_layout.test.cjs`, `test_approved_ncaaf_results_layout_check_passes` — **PASS** Linux |
| `atomic_json` / `O_DIRECTORY` on Windows | Directory `fsync` with `O_DIRECTORY=0` on Windows. | Skip directory `fsync` when `os.O_DIRECTORY` missing. | `202711d`, `78cbb5e` | delivery + hydration tests — **PASS** Linux |
| `fcntl.flock` missing on Windows | Partial `fcntl` stub. | Always install a flock-capable `fcntl` stub in `pubsupport.py`. | `78cbb5e` | `test_other_sport_fault_*` — **PASS** Windows + Linux |
| `deploy_check` false **STALE** | Text compare + inherited `GIT_DIR` / encoding on worktrees. | Compare publisher file with `git diff --quiet origin/main`; `_git_env()` clears inherited worktree env for ephemeral repos. | `78cbb5e` | `test_deploy_check_reports_a_publisher_behind_origin_main` — **PASS** Linux |
| Deploy-wait / global-fault tests fail under WSL | `GIT_DIR` from worktree leaked into publisher `git()` in temp repos. | `_git_env()` in `apex_shared_site_publisher.py`; matching helper in `pubsupport.py`. | `78cbb5e` | `test_cause1b_1c_1d_1f_delivery.py` — **26/26 PASS** Linux |
| apex_ncaaf grader import on Linux | Missing optional deps in bare `uv run`. | Linux runner adds `--with reportlab --with duckdb` (test env only). | (runner script only) | `test_grade_products_uses_the_same_loader` — **PASS** Linux |

**Windows (sanity):** apexrigor `tests/job1_cursor` **26/26** after the same publisher/pubsupport fixes.

**Not finished:** Droplet authority replay; `job1_cross_by_cursor` on site worktrees; amend `202711d` commit message/author to a proper Job 1 message (content is correct). No push.

## Round 4 (Codex cross-tests, Oct 20 2026)

**Linux evidence:** `C:\Users\scliu\apex2_site\job1\job1_cursor_r4_tests_20261020_222504.txt` (Docker Codex suites + WSL Grok / `tests/job1_cursor` / build / layout). Re-runner: `job1/tools/run_job1_cursor_r4_linux.sh` (Codex via Docker on Windows host when WSL has no Docker).

**Commits:** apexrigor `b2474bb`; apex_ncaaf `5af73d7` (on top of round 3 apexrigor `511b11e`, apex_ncaaf `fd44e39`).

| Suite | Linux result |
|---|---|
| Codex `tests_by_codex_r2` new (29) | **28 PASS, 1 FAIL** (`test_req9_committed_linux_page_matches_approved_normalized_hash` — see below) |
| Codex earlier apexrigor (11) | **9 PASS, 2 FAIL** (superseded req 11 expectations; see below) |
| Codex earlier apex_ncaaf (10) | **10/10 PASS** |
| Grok review apexrigor + apex_ncaaf | **10/10 PASS** |
| apexrigor `tests/job1_cursor` (26) | **PASS** |
| apex_ncaaf `tests/job1_cursor` (41) | **PASS** (deploy gate + chain replay expectations updated for fail-closed shared replay) |
| `build_vercel_output.py` + `node tests/ncaaf_results_layout.test.cjs` | **PASS** (`d2be6f35…` lock, no repin) |

### Per Codex failure (round 2 → round 4)

| Req / test | Cause | Fix | Commit | Linux after fix |
|---|---|---|---|---|
| **1** `[NFL]` foreign dirty paths block publish | `build_request` raised on non-NFL paths in the worktree instead of returning only NFL-owned paths. | Filter `changed_paths` to `nfl/` and `data/nfl_*`; do not gate on other sports’ dirty files. | `b2474bb` | **PASS** `test_req1_…[NFL]` |
| **2** grader window closed with `IN_PROGRESS` | `grader_window` used kickoff+duration even when a game was still `IN_PROGRESS`. | `slate_has_pending_finals()` extends the window while any game is actively non-final (`IN_PROGRESS`, etc.). | `5af73d7` | **PASS** `test_req2_unfinished_game_keeps_grader_retry_window_open`; earlier NCAAF grader pending-final **PASS** |
| **2** controller `KeyError` on nested card | `issuance_cards` assumed `game_id` on the card object. | Raise `RuntimeError` with `game_id` when the nested card omits it (operational loader still recovers via schema). | `5af73d7` | **PASS** `test_req2_actual_controller_…` |
| **6** manifest-only replay; Oct 18 PASS with gaps | `job1_shared_fixture_replay` only listed manifest paths. | Verify on-disk fixture bytes; call `run_pass` per shared date; `NOT_RECONSTRUCTED` / missing payloads fail overall; stub `run_pass` for documented gaps without droplet authorities. | `5af73d7` | **PASS** `test_req6_default_gate_…`, `test_req6_missing_fixture_bytes_…`, `test_req6_committed_linux_release_bindings_…` |
| **9** layout hash | Codex normalizes lifetime record **and** masks `<nav class="sport-nav">` to `#`; project lock (`tests/ncaaf_results_layout.test.cjs`) masks **only** the aside. Committed `48451c3` `ncaaf/results/index.html` yields aside-only `d2be6f35…` (**PASS** Node) but Codex double-mask `af56dd1c…`. | No HTML repin (Scott lock stays `d2be6f35…`). | — | **FAIL** Codex req9 only; **PASS** Grok req9 + `tests/job1_cursor` layout + Node lock |
| **11** second deploy after ERROR; serialization | `ensure_deployment` POSTed again when only ERROR deployments existed; `execute` published multiple NCAAF requests in one run while production was BUILDING. | Treat existing ERROR as terminal; defer further requests in the same `execute()` after a contentful publish. | `b2474bb` | **PASS** `test_req11_existing_error_deployment_…`, earlier hosting serialization **PASS** |
| Earlier **hosting** saved-card copy | Generators and post-copy subprocess steps ran on minimal trees. | Skip sport generators when sport dirs absent; skip selector/analytics/audit when `index.html` absent at site root; skip MLB normalize when `public/results` missing. | `b2474bb` | **PASS** `test_saved_content_cannot_invoke_sport_procedures` |
| Earlier **analytics** NBA routes | `active_outputs` omitted NBA. | Add `nba/*` routes to Cloudflare and Vercel analytics installers. | `b2474bb` | **PASS** `test_analytics_route_inventory_includes_nba` |
| Earlier **published intent retry** | NCAAF `publish` did not short-circuit on durable `PUBLISHED` intent. | Return existing intent when `published_commit` is set and status is `PUBLISHED*`. | `b2474bb` | **PASS** `test_published_request_keeps_its_commit_on_retry` |

### Remaining Codex failures (not fixed — superseded or inconsistent rule)

| Test | Why it still fails | Evidence |
|---|---|---|
| `test_req9_committed_linux_page_matches_approved_normalized_hash` | Codex applies an extra sport-nav mask not used by the approved lock test; same committed page passes `tests/ncaaf_results_layout.test.cjs` and Grok `test_layout_lock_keeps_the_approved_hash` with `d2be6f35…`. | Aside-only hash `d2be6f35…` on `48451c3` HTML; Codex double-mask `af56dd1c…` in `job1_cursor_r4_tests_20261020_222504.txt`. |
| `test_ready_descendant_deployment_is_accepted` | Encodes pre–req-11 descendant acceptance; current req 11 requires **exact** production commit match. | `CROSS_CODEX_ON_CURSOR_R2.md` limitations (not charged as new defects). |
| `test_deployment_delay_has_bound_and_alert` | Encodes timeout **alerts** on healthy production; req 11 alerts only on production **ERROR**. | Same Consigliere note in Codex report. |

**Not finished:** Full droplet authority replay for reconstructable shared dates (local gate correctly **FAIL**s until Oct 18 is reconstructed or authorities are copied). No push.
